# =============================================================================
#  game.py  –  Panic Pilot | Haupt-Spielschleife (Phase 5.3)
# =============================================================================
#
#  Phase 5.3 Änderungen:
#    1. Props       – PropManager erzeugt/rendert dekorative Biom-Objekte
#    2. PvP-Start   – Modus 3: Autos starten nebeneinander (side_offset)
#    3. Pause       – P-Taste togglet _paused; Guard in update() + Overlay
#    4. Speed Scale – self.speed_scale skaliert dt bei apply_input()
# =============================================================================
from __future__ import annotations
import math
from typing import Optional
import pygame

from settings    import *
from camera      import Camera, ZOOM_MIN, ZOOM_MAX
from car         import Car, CAR_COLOR_HOST, CAR_COLOR_CLIENT
from car_state   import CarState
from input_state import InputState
from track       import Track
from walls       import WallSystem
from hud         import HUD
from entities    import FuelCanister
from particles   import ParticleSystem
from props       import PropManager

FOG_ALPHA  = 255
FOG_RADIUS = int(min(SCREEN_W, SCREEN_H) * 0.085)

PING_DURATION = 2.5
MAX_PINGS     = 8
PING_BLINK_HZ = 3.0

COUNTDOWN_STEPS         = [3, 2, 1]
COUNTDOWN_STEP_DURATION = 1.0
GO_DISPLAY_DURATION     = 1.2

# Geschwindigkeits-Skalierung: skaliert dt bei apply_input()
SPEED_SCALE_SLOW   = 0.70
SPEED_SCALE_NORMAL = 1.00
SPEED_SCALE_FAST   = 1.40


class Game:
    """
    Basis-Spielschleife.
    self.cars[0] = Host/Solo, self.cars[1] = Client (Modus 3)
    self._paused: bool        – P-Taste
    self.speed_scale: float   – Geschwindigkeits-Skalierung
    """

    def __init__(self) -> None:
        pygame.init()
        self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(TITLE)
        self.clock   = pygame.time.Clock()
        self.running = True

        self.mode             = 1
        self.pings: list[list]= []
        self._return_to_menu  = False
        self._paused          = False
        self.speed_scale      = SPEED_SCALE_NORMAL

        self._warn_font      = pygame.font.SysFont("Arial", 18, bold=True)
        self._countdown_font = pygame.font.SysFont("Arial", 160, bold=True)
        self._win_font       = pygame.font.SysFont("Arial", 72, bold=True)
        self._sub_font       = pygame.font.SysFont("Arial", 28, bold=True)
        self._pause_font     = pygame.font.SysFont("Arial", 80, bold=True)

        self._flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._fog_surf   = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

        self.camera = Camera()
        self._init_game_objects()

    # ─── Initialisierung ─────────────────────────────────────────────────────

    def _init_game_objects(self, track: Optional[Track] = None) -> None:
        self.track = track if track is not None else Track.generate()

        sx, sy, sa = self.track.start_x, self.track.start_y, self.track.start_angle
        rad = math.radians(sa)

        # PvP: Autos nebeneinander statt hintereinander
        # Senkrecht-Vektor zur Fahrtrichtung
        side_x      = math.cos(rad)
        side_y      = math.sin(rad)
        side_offset = 36   # px seitlicher Versatz von Mittellinie

        self.cars: list[Car] = [
            Car(sx - side_x * side_offset, sy - side_y * side_offset,
                sa, initial_fuel=FUEL_MAX, body_color=CAR_COLOR_HOST),
            Car(sx + side_x * side_offset, sy + side_y * side_offset,
                sa, initial_fuel=FUEL_MAX, body_color=CAR_COLOR_CLIENT),
        ]
        self.car = self.cars[0]

        self.camera.snap(sx, sy)
        self.hud       = HUD()
        self.particles = ParticleSystem()
        self.walls     = WallSystem(screen_edge=False)

        from walls import RectWall
        for wx, wy, ww, wh in self.track.build_boundary_walls():
            self.walls.add(RectWall(wx, wy, ww, wh, visible=False))
        for wx, wy, ww, wh in self.track.build_anticheat_walls():
            self.walls.add(RectWall(wx, wy, ww, wh, visible=False))

        # Dekorative Props (Phase 5.3)
        prop_seed = hash(tuple(t.tile_type for t in self.track.tiles)) % 99999
        self.props = PropManager.generate(
            self.track, theme=self.track.theme, seed=prop_seed)

        # Kanister mit IDs (für Netzwerk-Sync)
        self.canisters = [FuelCanister(x, y, canister_id=i)
                          for i, (x, y) in enumerate(self.track.canister_positions())]

        self.elapsed_time     = 0.0
        self.game_over        = False
        self.winner: Optional[str] = None
        self._fuel_flash      = 0.0
        self._off_track_accum = 0.0
        self._countdown       = float(len(COUNTDOWN_STEPS)) * COUNTDOWN_STEP_DURATION
        self._go_timer        = 0.0
        self._race_started    = False

    def reset(self, track: Optional[Track] = None) -> None:
        self.pings.clear()
        self._paused = False
        self._init_game_objects(track=track)

    # ─── Events ──────────────────────────────────────────────────────────────

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    if not self._paused:
                        self.reset()
                    return
                elif event.key == pygame.K_p:
                    # Pause nur während laufendem Rennen
                    if not (self.game_over or self.winner):
                        self._paused = not self._paused
                elif event.key == pygame.K_m and (self.game_over or self.winner):
                    self.running = False
                    self._return_to_menu = True
                else:
                    self._on_keydown(event)

    def _on_keydown(self, event) -> None:
        pass

    # ─── Update ──────────────────────────────────────────────────────────────

    def update(self, dt: float, input_override: Optional[InputState] = None,
               input_car1: Optional[InputState] = None) -> None:
        # Pause-Guard: bei Pause komplett einfrieren
        if self._paused:
            return

        self.pings = [p for p in self.pings if p[2] > 0]
        for p in self.pings: p[2] -= dt

        # Countdown
        if self._countdown > 0:
            self._countdown -= dt
            if self._countdown <= 0:
                self._countdown    = 0.0
                self._go_timer     = GO_DISPLAY_DURATION
                self._race_started = True
            self.camera.update(self.cars[0].state.x, self.cars[0].state.y, dt)
            return

        if self._go_timer > 0:
            self._go_timer -= dt

        if self.game_over or self.winner is not None:
            for car in self.cars:
                car.state.speed *= max(0.0, 1.0 - 4.0 * dt)
                if abs(car.state.speed) < 1.0:
                    car.state.speed = 0.0
            self.camera.update(self.cars[0].state.x, self.cars[0].state.y, dt)
            return

        # Speed-Scale: dt bei apply_input skalieren
        # Höherer Wert → stärkere Beschleunigung + höhere Endgeschwindigkeit
        scaled_dt = dt * self.speed_scale

        # ── Auto 0 ────────────────────────────────────────────────────────────
        s0   = self.cars[0].state
        inp0 = (input_override if input_override is not None
                else InputState.from_keys(pygame.key.get_pressed()))
        self.cars[0].apply_input(inp0, scaled_dt)
        surf0 = self.track.surface_at(s0.x, s0.y)
        self.cars[0].update(dt, surface=surf0)
        s0.x, s0.y, s0.speed = self.walls.resolve_all(
            s0.x, s0.y, s0.speed, self.cars[0].get_radius())

        if abs(s0.speed) > 5.0:
            s0.fuel -= FUEL_DRAIN_RATE * dt
            s0.fuel  = max(0.0, s0.fuel)
        if s0.fuel <= 0.0:
            self.game_over = True

        # ── Auto 1 (Modus 3) ─────────────────────────────────────────────────
        if self.mode == 3 and input_car1 is not None:
            s1 = self.cars[1].state
            self.cars[1].apply_input(input_car1, scaled_dt)
            surf1 = self.track.surface_at(s1.x, s1.y)
            self.cars[1].update(dt, surface=surf1)
            s1.x, s1.y, s1.speed = self.walls.resolve_all(
                s1.x, s1.y, s1.speed, self.cars[1].get_radius())
            if abs(s1.speed) > 5.0:
                s1.fuel -= FUEL_DRAIN_RATE * dt
                s1.fuel  = max(0.0, s1.fuel)
            self._resolve_car_collision()

        # ── Kanister ─────────────────────────────────────────────────────────
        for c in self.canisters:
            c.update(dt)
            if c.try_pickup(s0.x, s0.y):
                s0.fuel = min(FUEL_MAX, s0.fuel + FUEL_CANISTER_VALUE)
                self.particles.emit_pickup(c.x, c.y)
                self._fuel_flash = 0.5
            elif self.mode == 3:
                s1 = self.cars[1].state
                if c.try_pickup(s1.x, s1.y):
                    s1.fuel = min(FUEL_MAX, s1.fuel + FUEL_CANISTER_VALUE)
                    self.particles.emit_pickup(c.x, c.y)
        if self._fuel_flash > 0:
            self._fuel_flash -= dt

        # ── Win Condition: Kein Sprit ─────────────────────────────────────────
        if self.winner is None:
            if s0.fuel <= 0.0:
                self.winner    = "client" if self.mode == 3 else None
                self.game_over = True
            elif self.mode == 3:
                s1 = self.cars[1].state
                if s1.fuel <= 0.0:
                    self.winner    = "host"
                    self.game_over = True

        # ── Win Condition: Ziellinie ──────────────────────────────────────────
        if self.winner is None and not self.game_over:
            if self.track.crosses_finish(s0.x, s0.y, self.cars[0].get_radius()):
                self.winner    = "host"
                self.game_over = True
            elif self.mode == 3:
                s1 = self.cars[1].state
                if self.track.crosses_finish(s1.x, s1.y, self.cars[1].get_radius()):
                    self.winner    = "client"
                    self.game_over = True

        # ── Kamera ───────────────────────────────────────────────────────────
        if self.mode == 3:
            self._update_camera_pvp(dt)
        else:
            self.camera.update(s0.x, s0.y, dt)

        # ── Partikel ─────────────────────────────────────────────────────────
        rad = math.radians(s0.angle)
        self.particles.emit_exhaust(
            s0.x - math.sin(rad) * 18, s0.y + math.cos(rad) * 18,
            s0.angle, s0.speed)
        if surf0 in ("grass", "curb") and abs(s0.speed) > 15:
            self._off_track_accum += dt
            if self._off_track_accum > 0.05:
                self.particles.emit_off_track(s0.x, s0.y)
                self._off_track_accum = 0.0
        else:
            self._off_track_accum = 0.0

        self.particles.update(dt)
        self.elapsed_time += dt

        if self.mode == 1:
            self.camera.zoom = 1.0

    # ─── Physik-Helfer ───────────────────────────────────────────────────────

    def _resolve_car_collision(self) -> None:
        s0, s1 = self.cars[0].state, self.cars[1].state
        r    = self.cars[0].get_radius()
        dist = math.hypot(s0.x - s1.x, s0.y - s1.y)
        if dist < r * 2 and dist > 0.1:
            nx = (s0.x - s1.x) / dist
            ny = (s0.y - s1.y) / dist
            overlap = r * 2 - dist
            s0.x += nx * overlap * 0.5; s0.y += ny * overlap * 0.5
            s1.x -= nx * overlap * 0.5; s1.y -= ny * overlap * 0.5
            v0, v1   = s0.speed, s1.speed
            s0.speed = v1 * 0.6
            s1.speed = v0 * 0.6

    def _update_camera_pvp(self, dt: float) -> None:
        s0, s1 = self.cars[0].state, self.cars[1].state
        dist        = math.hypot(s0.x - s1.x, s0.y - s1.y)
        target_zoom = max(0.35, min(1.0, 600.0 / max(dist, 600.0)))
        self.camera.zoom += (target_zoom - self.camera.zoom) * 0.05
        self.camera.update(s0.x, s0.y, dt)

    # ─── Rendering ───────────────────────────────────────────────────────────

    def draw_world(self, surface: pygame.Surface) -> None:
        zoom         = self.camera.zoom
        off_x, off_y = self.camera.offset()
        bg_color = getattr(getattr(self.track, "theme", None), "bg_fill", GRASS_DARK)
        surface.fill(bg_color)
        self.track.draw(surface, off_x, off_y, zoom)
        self.walls.draw(surface, off_x, off_y, zoom)
        # Props: rein kosmetisch, hinter Spielobjekten
        self.props.draw(surface, off_x, off_y, zoom)
        self.particles.draw(surface, off_x, off_y, zoom)
        for c in self.canisters:
            c.draw(surface, off_x, off_y, zoom)
        if self._fuel_flash > 0:
            alpha = int(120 * min(1.0, self._fuel_flash / 0.5))
            self._flash_surf.fill((255, 200, 0, alpha))
            surface.blit(self._flash_surf, (0, 0))
        for car in self.cars:
            if self.mode != 3 and car is self.cars[1]:
                continue
            car.draw(surface, off_x, off_y, zoom)

    def draw_fog(self, surface: pygame.Surface, car_screen_pos: tuple) -> None:
        cx, cy = int(car_screen_pos[0]), int(car_screen_pos[1])
        self._fog_surf.fill((0, 0, 0, FOG_ALPHA))
        pygame.draw.circle(self._fog_surf, (0, 0, 0, 0), (cx, cy), FOG_RADIUS)
        surface.blit(self._fog_surf, (0, 0))

    def draw_pings(self, surface: pygame.Surface) -> None:
        for wx, wy, timer in self.pings:
            sx, sy = self.camera.w2s(wx, wy)
            frac   = max(0.0, timer / PING_DURATION)
            if int(timer * PING_BLINK_HZ * 2) % 2 != 0:
                continue
            alpha  = int(max(60, 255 * frac))
            radius = int(max(4, 14 + 6 * frac))
            size   = radius * 2 + 24; mid = size // 2
            tmp    = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(tmp, (0, 220, 255, alpha), (mid, mid), radius, 2)
            arm = radius + 7
            for dx, dy in [(arm,0),(-arm,0),(0,arm),(0,-arm)]:
                pygame.draw.line(tmp, (0,220,255,alpha), (mid,mid),
                                 (mid+dx//2, mid+dy//2), 2)
            pygame.draw.circle(tmp, (255, 255, 100, alpha), (mid, mid), 4)
            surface.blit(tmp, (sx - mid, sy - mid))

    def draw_hud(self, surface: pygame.Surface) -> None:
        s = self.cars[0].state
        self.hud.draw(surface, s.speed, s.fuel, self.elapsed_time)
        if not self.game_over and self._race_started:
            if self.track.surface_at(s.x, s.y) == "grass":
                lbl = self._warn_font.render("NEBEN DER STRECKE", True, YELLOW)
                surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H - 40))

    def draw_countdown(self, surface: pygame.Surface) -> None:
        if self._countdown > 0:
            step_idx = min(int(self._countdown / COUNTDOWN_STEP_DURATION),
                           len(COUNTDOWN_STEPS) - 1)
            num   = COUNTDOWN_STEPS[-(step_idx + 1)]
            color = [RED, ORANGE, YELLOW][min(step_idx, 2)]
            lbl   = self._countdown_font.render(str(num), True, color)
            sx    = (SCREEN_W - lbl.get_width()) // 2
            sy    = (SCREEN_H - lbl.get_height()) // 2
            shd   = self._countdown_font.render(str(num), True, BLACK)
            surface.blit(shd, (sx + 4, sy + 4))
            surface.blit(lbl, (sx, sy))
        elif self._go_timer > 0:
            lbl = self._countdown_font.render("GO!", True, GREEN)
            sx  = (SCREEN_W - lbl.get_width()) // 2
            sy  = (SCREEN_H - lbl.get_height()) // 2
            shd = self._countdown_font.render("GO!", True, BLACK)
            surface.blit(shd, (sx + 4, sy + 4))
            surface.blit(lbl, (sx, sy))

    def draw_winner(self, surface: pygame.Surface) -> None:
        if self.winner is None and not self.game_over:
            return
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 175))
        surface.blit(overlay, (0, 0))
        cy = SCREEN_H // 2 - 80
        if self.mode == 3:
            if self.winner == "host":
                txt, color = "HOST GEWINNT!", CAR_COLOR_HOST
            elif self.winner == "client":
                txt, color = "CLIENT GEWINNT!", CAR_COLOR_CLIENT
            else:
                txt, color = "KEIN SPRIT!", ORANGE
        else:
            txt, color = ("ZIEL!", YELLOW) if self.winner else ("KEIN SPRIT!", ORANGE)
        lbl = self._win_font.render(txt, True, color)
        surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, cy))
        cy += lbl.get_height() + 10
        mins  = int(self.elapsed_time) // 60
        secs  = int(self.elapsed_time) % 60
        cs    = int((self.elapsed_time % 1) * 100)
        t_lbl = self._sub_font.render(f"Zeit: {mins:02d}:{secs:02d}.{cs:02d}", True, WHITE)
        surface.blit(t_lbl, ((SCREEN_W - t_lbl.get_width()) // 2, cy))
        cy += t_lbl.get_height() + 28
        r_lbl = self._sub_font.render("[R]  Neustart", True, CYAN)
        m_lbl = self._sub_font.render("[M]  Hauptmenü", True, YELLOW)
        surface.blit(r_lbl, ((SCREEN_W - r_lbl.get_width()) // 2, cy))
        surface.blit(m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2,
                              cy + r_lbl.get_height() + 12))

    def draw_pause_overlay(self, surface: pygame.Surface) -> None:
        """Pause-Overlay: halbtransparent + PAUSE-Text + Steuerungs-Hinweis."""
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        surface.blit(overlay, (0, 0))
        lbl = self._pause_font.render("PAUSE", True, CYAN)
        shd = self._pause_font.render("PAUSE", True, BLACK)
        sx  = (SCREEN_W - lbl.get_width()) // 2
        sy  = SCREEN_H // 2 - lbl.get_height() // 2 - 20
        surface.blit(shd, (sx + 3, sy + 3))
        surface.blit(lbl, (sx, sy))
        hint = self._sub_font.render(
            "[P] Weiter  |  [R] Neustart  |  [ESC] Beenden", True, WHITE)
        surface.blit(hint, ((SCREEN_W - hint.get_width()) // 2,
                             sy + lbl.get_height() + 20))

    def draw(self) -> None:
        self.draw_world(self.screen)
        if self.mode == 2:
            csx, csy = self.camera.w2s(self.cars[0].state.x, self.cars[0].state.y)
            self.draw_fog(self.screen, (csx, csy))
            self.draw_pings(self.screen)
        self.draw_hud(self.screen)
        self.draw_countdown(self.screen)
        if self.game_over or self.winner is not None:
            self.draw_winner(self.screen)
        if self._paused:
            self.draw_pause_overlay(self.screen)
        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()
