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

from settings import *
from camera import Camera, ZOOM_MIN, ZOOM_MAX
from car import Car, CAR_COLOR_HOST, CAR_COLOR_CLIENT
from car_state import CarState
from input_state import InputState
from track import Track
from walls import WallSystem
from hud import HUD
from entities import (
    FuelCanister,
    BoostPad,
    OilSlick,
    ItemBox,
    GreenBoomerang,
    RedBoomerang,
    EntityParticleSystem,
    PLAYER_HOST,
    PLAYER_CLIENT,
    BOOMERANG_SPEED,
)
from particles import ParticleSystem
from props import PropManager

# Phase 12: Audio (lazy import – läuft auch ohne sound_manager.py)
try:
    import sound_manager as _sound_mod

    _SM = _sound_mod.get()
except Exception:
    _SM = None

FOG_ALPHA = 255
FOG_RADIUS = int(min(SCREEN_W, SCREEN_H) * 0.085)

PING_DURATION = 2.5
MAX_PINGS = 8
PING_BLINK_HZ = 3.0

COUNTDOWN_STEPS = [3, 2, 1]
COUNTDOWN_STEP_DURATION = 1.0
GO_DISPLAY_DURATION = 1.2

# Geschwindigkeits-Skalierung: skaliert dt bei apply_input()
SPEED_SCALE_SLOW = 0.70
SPEED_SCALE_NORMAL = 1.00
SPEED_SCALE_FAST = 1.40


class Game:
    """
    Basis-Spielschleife.
    self.cars[0] = Host/Solo, self.cars[1] = Client (Modus 3)
    self._paused: bool        – P-Taste
    self.speed_scale: float   – Geschwindigkeits-Skalierung
    """

    def __init__(
        self,
        screen: "pygame.Surface | None" = None,
        locked_class0: str = "balanced",
        locked_class1: str = "balanced",
    ) -> None:

        if screen is None:
            pygame.init()
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        else:
            self.screen = screen
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.mode = 1
        self.pings: list[list] = []
        self._return_to_menu = False
        # Phase 12: Countdown-Schritt-Tracking für Sound
        self._last_cdstep = -1
        self._return_to_lobby = False  # Phase 11: Lobby-Return
        self._lobby_initiator = ""  # "self" | "remote"
        self._paused = False
        self.speed_scale = SPEED_SCALE_NORMAL
        self._pause_btn_rects: dict = {}  # populated by draw_pause_overlay

        # Klassen sind vor dem Rennen gelockt – kein In-Game-Wechsel
        self._locked_class0 = locked_class0
        self._locked_class1 = locked_class1

        self._warn_font = pygame.font.SysFont("Arial", 18, bold=True)
        self._countdown_font = pygame.font.SysFont("Arial", 160, bold=True)
        self._win_font = pygame.font.SysFont("Arial", 72, bold=True)
        self._sub_font = pygame.font.SysFont("Arial", 28, bold=True)
        self._pause_font = pygame.font.SysFont("Arial", 80, bold=True)

        self._flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._fog_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

        self.camera = Camera()
        self._init_game_objects()

    # ─── Initialisierung ─────────────────────────────────────────────────────

    def _init_game_objects(self, track: Optional[Track] = None) -> None:
        self.track = track if track is not None else Track.generate()

        sx, sy, sa = self.track.start_x, self.track.start_y, self.track.start_angle
        rad = math.radians(sa)

        # PvP: Autos nebeneinander statt hintereinander
        # Senkrecht-Vektor zur Fahrtrichtung
        side_x = math.cos(rad)
        side_y = math.sin(rad)
        side_offset = 36

        # Klassen aus den gesperrten Werten (Lobby-Auswahl)
        prev_class0 = getattr(self, "_locked_class0", "balanced")
        prev_class1 = getattr(self, "_locked_class1", "balanced")

        cs0 = CAR_CLASSES.get(prev_class0, CAR_CLASSES["balanced"])
        cs1 = CAR_CLASSES.get(prev_class1, CAR_CLASSES["balanced"])

        self.cars: list[Car] = [
            Car(
                sx - side_x * side_offset,
                sy - side_y * side_offset,
                sa,
                initial_fuel=FUEL_MAX,
                body_color=cs0["color_host"],
                car_class=prev_class0,
            ),
            Car(
                sx + side_x * side_offset,
                sy + side_y * side_offset,
                sa,
                initial_fuel=FUEL_MAX,
                body_color=cs1["color_client"],
                car_class=prev_class1,
            ),
        ]
        self.car = self.cars[0]

        self.camera.snap(sx, sy)
        self.hud = HUD()
        self.particles = ParticleSystem()
        self.walls = WallSystem(screen_edge=False)

        from walls import RectWall

        for wx, wy, ww, wh in self.track.build_boundary_walls():
            self.walls.add(RectWall(wx, wy, ww, wh, visible=False))
        for wx, wy, ww, wh in self.track.build_anticheat_walls():
            self.walls.add(RectWall(wx, wy, ww, wh, visible=False))

        # Dekorative Props (Phase 5.3)
        prop_seed = hash(tuple(t.tile_type for t in self.track.tiles)) % 99999
        self.props = PropManager.generate(
            self.track, theme=self.track.theme, seed=prop_seed
        )

        # Kanister mit IDs (für Netzwerk-Sync)
        # Im Modus 3 (PvP) pvp_mode aktivieren damit collected_by korrekt arbeitet
        pvp = self.mode == 3
        self.canisters: list[FuelCanister] = []
        for i, (cx, cy) in enumerate(self.track.canister_positions()):
            c = FuelCanister(cx, cy, canister_id=i)
            c.set_pvp_mode(pvp)
            self.canisters.append(c)

        self.boosts: list[BoostPad] = []
        for i, (bx, by, ba) in enumerate(self.track.boost_positions()):
            b = BoostPad(bx, by, ba, pad_id=i)
            b.set_pvp_mode(pvp)
            self.boosts.append(b)

        self.oils: list[OilSlick] = []
        for i, (ox, oy) in enumerate(self.track.oil_positions()):
            o = OilSlick(ox, oy, slick_id=i)
            o.set_pvp_mode(pvp)
            self.oils.append(o)

        self.item_boxes: list[ItemBox] = []
        for i, (bx, by) in enumerate(self.track.box_positions()):
            ib = ItemBox(bx, by, box_id=i)
            ib.set_pvp_mode(pvp)
            self.item_boxes.append(ib)

        self.entity_particles = EntityParticleSystem()
        self.boomerangs: list = []  # GreenBoomerang | RedBoomerang

        self.elapsed_time = 0.0
        self.game_over = False
        self.winner: Optional[str] = None
        self._fuel_flash = 0.0
        self._off_track_accum = 0.0
        self._countdown = float(len(COUNTDOWN_STEPS)) * COUNTDOWN_STEP_DURATION
        self._go_timer = 0.0
        self._race_started = False

    def reset(self, track: Optional[Track] = None) -> None:
        self.pings.clear()
        self._paused = False
        self._init_game_objects(track=track)

    # ─── Events ──────────────────────────────────────────────────────────────

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_pause_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_p):
                    if self.game_over or self.winner:
                        # End-screen: ESC = Menü
                        if event.key == pygame.K_ESCAPE:
                            self.running = False
                    else:
                        # Toggle enhanced pause
                        self._paused = not self._paused
                        if _SM:
                            _SM.play_pause()
                            if self._paused:
                                _SM.engine_stop()
                            else:
                                _SM.engine_start()
                elif event.key == pygame.K_r:
                    if not self._paused:
                        self.reset()
                    return
                elif event.key == pygame.K_m and (self.game_over or self.winner):
                    self.running = False
                    self._return_to_menu = True
                # Pause-Menü Shortcuts
                elif self._paused:
                    if event.key == pygame.K_l:
                        self._do_return_to_lobby()
                    elif event.key == pygame.K_q:
                        self.running = False
                else:
                    self._on_keydown(event)

    def _handle_pause_click(self, pos: tuple) -> None:
        """Verarbeitet Mausklicks auf die Pause-Menü-Buttons."""
        if not self._paused:
            return
        action = None
        for key, rect in self._pause_btn_rects.items():
            if rect.collidepoint(pos):
                action = key
                break
        if action == "resume":
            self._paused = False
        elif action == "lobby":
            self._do_return_to_lobby()
        elif action == "quit":
            self.running = False

    def _do_return_to_lobby(self) -> None:
        """Setzt Lobby-Return-Flag und beendet das Rennen (Phase 11)."""
        self._return_to_lobby = True
        self._lobby_initiator = "self"
        self._paused = False
        self.running = False

    def _on_keydown(self, event) -> None:
        pass

    # ─── Update ──────────────────────────────────────────────────────────────

    def update(
        self,
        dt: float,
        input_override: Optional[InputState] = None,
        input_car1: Optional[InputState] = None,
    ) -> None:
        # Pause-Guard: bei Pause komplett einfrieren
        if self._paused:
            return

        self.pings = [p for p in self.pings if p[2] > 0]
        for p in self.pings:
            p[2] -= dt

        # Sicherstellen, dass die Variable existiert, egal was in __init__ passiert
        if not hasattr(self, "_last_cdstep"):
            self._last_cdstep = -1

        # Countdown
        if self._countdown > 0:
            self._countdown -= dt
            # ── Phase 12: Countdown-Beep bei jedem Schritt ───────────────────
            cdstep = int(self._countdown)
            if cdstep != self._last_cdstep:
                self._last_cdstep = cdstep
                if _SM and self._countdown > 0:
                    _SM.play_countdown_beep()
            if self._countdown <= 0:
                self._countdown = 0.0
                self._go_timer = GO_DISPLAY_DURATION
                self._race_started = True
                # ── GO-Sound + Motor starten ──────────────────────────────────
                if _SM:
                    _SM.play_countdown_go()
                    _SM.engine_start()
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
        s0 = self.cars[0].state
        inp0 = (
            input_override
            if input_override is not None
            else InputState.from_keys(pygame.key.get_pressed())
        )
        surf0 = self.track.surface_at(s0.x, s0.y)
        grip0 = self._get_grip(surf0, self.cars[0])
        self.cars[0].apply_input(inp0, scaled_dt, grip_factor=grip0)
        self.cars[0].update(dt, surface=surf0, grip_factor=grip0)
        _pre_speed0 = s0.speed
        s0.x, s0.y, s0.speed = self.walls.resolve_all(
            s0.x, s0.y, s0.speed, self.cars[0].get_radius()
        )
        # ── Phase 12: Wand-Kollision erkennen ────────────────────────────────
        if _SM and abs(_pre_speed0 - s0.speed) > 40:
            _SM.play_collision(min(1.0, abs(_pre_speed0) / 400.0))

        if abs(s0.speed) > 5.0:
            drain0 = (
                FUEL_DRAIN_RATE
                * CAR_CLASSES.get(self.cars[0].car_class, CAR_CLASSES["balanced"])[
                    "fuel_mul"
                ]
            )
            s0.fuel -= drain0 * dt
            s0.fuel = max(0.0, s0.fuel)
        if s0.fuel <= 0.0:
            self.game_over = True

        # ── Auto 1 (Modus 3) ─────────────────────────────────────────────────
        if self.mode == 3 and input_car1 is not None:
            s1 = self.cars[1].state
            surf1 = self.track.surface_at(s1.x, s1.y)
            grip1 = self._get_grip(surf1, self.cars[1])
            self.cars[1].apply_input(input_car1, scaled_dt, grip_factor=grip1)
            self.cars[1].update(dt, surface=surf1, grip_factor=grip1)
            s1.x, s1.y, s1.speed = self.walls.resolve_all(
                s1.x, s1.y, s1.speed, self.cars[1].get_radius()
            )
            if abs(s1.speed) > 5.0:
                drain1 = (
                    FUEL_DRAIN_RATE
                    * CAR_CLASSES.get(self.cars[1].car_class, CAR_CLASSES["balanced"])[
                        "fuel_mul"
                    ]
                )
                s1.fuel -= drain1 * dt
                s1.fuel = max(0.0, s1.fuel)
            self._resolve_car_collision()

        # ── Pickups: Kanister / Boost-Pads / Ölflecken / ItemBoxen ─────────
        for c in self.canisters:
            c.update(dt)
        for b in self.boosts:
            b.update(dt)
        for o in self.oils:
            o.update(dt)
        for ib in self.item_boxes:
            ib.update(dt)
        self._apply_pickups(self.cars[0], PLAYER_HOST, surf0, inp0.use_item)
        if self.mode == 3:
            s1 = self.cars[1].state
            surf1_now = self.track.surface_at(s1.x, s1.y)
            use1 = input_car1.use_item if input_car1 is not None else False
            self._apply_pickups(self.cars[1], PLAYER_CLIENT, surf1_now, use1)
        if self._fuel_flash > 0:
            self._fuel_flash -= dt
        self.entity_particles.update(dt)

        # ── Boomerangs ────────────────────────────────────────────────────────
        # Target-Positionen für RedBoomerang
        pos = [
            (c.state.x, c.state.y)
            for c in self.cars
            if self.mode == 3 or c is self.cars[0]
        ]
        for brang in self.boomerangs:
            if not brang.active:
                continue
            if isinstance(brang, GreenBoomerang):
                brang.update(dt, self.track)
            else:
                # Finde nächstes nicht-eigenes Auto als Ziel
                tx, ty = None, None
                for i, car in enumerate(self.cars):
                    pid = PLAYER_HOST if i == 0 else PLAYER_CLIENT
                    if pid != brang.owner_id:
                        tx, ty = car.state.x, car.state.y
                        break
                brang.update(dt, self.track, tx, ty)
            # Kollision mit allen Autos prüfen
            for i, car in enumerate(self.cars):
                if self.mode != 3 and i == 1:
                    continue
                pid = PLAYER_HOST if i == 0 else PLAYER_CLIENT
                if brang.check_hit(car.state.x, car.state.y, pid):
                    car.spin_timer = OilSlick.SPIN_DURATION
                    self.entity_particles.emit_boost_sparks(car.state.x, car.state.y)
        # Inaktive Boomerangs entfernen (nicht öfter als nötig)
        if any(not b.active for b in self.boomerangs):
            self.boomerangs = [b for b in self.boomerangs if b.active]

        # ── Win Condition: Kein Sprit ─────────────────────────────────────────
        if self.winner is None:
            if s0.fuel <= 0.0:
                self.winner = "client" if self.mode == 3 else None
                self.game_over = True
                if _SM:
                    _SM.engine_stop()
            elif self.mode == 3:
                s1 = self.cars[1].state
                if s1.fuel <= 0.0:
                    self.winner = "host"
                    self.game_over = True
                    if _SM:
                        _SM.engine_stop()

        # ── Win Condition: Ziellinie ──────────────────────────────────────────
        if self.winner is None and not self.game_over:
            if self.track.crosses_finish(s0.x, s0.y, self.cars[0].get_radius()):
                self.winner = "host"
                self.game_over = True
                if _SM:
                    _SM.engine_stop()
                    _SM.play_win_fanfare()
            elif self.mode == 3:
                s1 = self.cars[1].state
                if self.track.crosses_finish(s1.x, s1.y, self.cars[1].get_radius()):
                    self.winner = "client"
                    self.game_over = True
                    if _SM:
                        _SM.engine_stop()

        # ── Kamera ───────────────────────────────────────────────────────────
        if self.mode == 3:
            self._update_camera_pvp(dt)
        else:
            self.camera.update(s0.x, s0.y, dt)

        # ── Partikel ─────────────────────────────────────────────────────────
        rad = math.radians(s0.angle)
        self.particles.emit_exhaust(
            s0.x - math.sin(rad) * 18, s0.y + math.cos(rad) * 18, s0.angle, s0.speed
        )
        if surf0 in ("grass", "curb") and abs(s0.speed) > 15:
            self._off_track_accum += dt
            if self._off_track_accum > 0.05:
                self.particles.emit_off_track(s0.x, s0.y)
                self._off_track_accum = 0.0
        else:
            self._off_track_accum = 0.0

        self.particles.update(dt)
        self.elapsed_time += dt

        # ── Phase 12: Motor-Sound live aktualisieren ──────────────────────────
        if _SM:
            from settings import CAR_MAX_SPEED

            _SM.update_engine(s0.speed, CAR_MAX_SPEED, dt)

        if self.mode == 1:
            self.camera.zoom = 1.0

    # ─── Physik-Helfer ───────────────────────────────────────────────────────

    def _get_grip(self, surface: str, car: "Car" = None) -> float:
        """Grip per surface + theme + car class (Phase 9)."""
        theme = getattr(self.track, "theme", None)
        grip_mod = (
            CAR_CLASSES.get(
                getattr(car, "car_class", "balanced"), CAR_CLASSES["balanced"]
            )["grip_mod"]
            if car
            else 1.0
        )
        if theme is None:
            return 1.0 * grip_mod
        name = getattr(theme, "name", "")
        if surface == "asphalt":
            raw = float(getattr(theme, "road_grip", 1.0))
            base = max(0.78 if name == "ice" else 0.2, raw)
        elif surface == "grass":
            base = max(0.1, 1.0 - float(getattr(theme, "grass_slip", 0.0)))
        elif surface == "curb":
            g = float(getattr(theme, "road_grip", 1.0))
            s = float(getattr(theme, "grass_slip", 0.0))
            base = max(0.15, (g + (1.0 - s)) * 0.5)
        else:
            base = 1.0
        return base * grip_mod

    def _apply_pickups(
        self,
        car: "Car",
        player_id: int,
        surface: str = "asphalt",
        use_item: bool = False,
    ) -> None:
        """Kanister, Boost-Pads, Ölflecken, ItemBoxen und Item-Aktivierung."""
        s = car.state
        # Kanister
        for c in self.canisters:
            if c.try_pickup(s.x, s.y, player_id=player_id):
                s.fuel = min(FUEL_MAX, s.fuel + FUEL_CANISTER_VALUE)
                self.particles.emit_pickup(c.x, c.y)
                if player_id == PLAYER_HOST:
                    self._fuel_flash = 0.5
                    if _SM:
                        _SM.play_pickup_fuel()
        # Boost-Pads
        for b in self.boosts:
            if b.try_trigger(s.x, s.y, player_id=player_id):
                car.boost_timer = BoostPad.BOOST_DURATION
                if s.speed < BoostPad.BOOST_SPEED * 0.5:
                    s.speed = BoostPad.BOOST_SPEED * 0.5
                self.entity_particles.emit_boost_sparks(b.x, b.y)
        # Ölflecken
        for o in self.oils:
            if o.try_trigger(s.x, s.y, player_id=player_id):
                car.spin_timer = OilSlick.SPIN_DURATION
        # ItemBoxen – nur wenn Inventar leer
        for ib in self.item_boxes:
            item = ib.try_pickup(s.x, s.y, player_id=player_id)
            if item and car.inventory is None:
                car.inventory = item
                self.entity_particles.emit_boost_sparks(ib.x, ib.y)
                if player_id == PLAYER_HOST and _SM:
                    _SM.play_pickup_item()
        # Item benutzen (SPACE / use_item Flag)
        if use_item and car.inventory is not None:
            self._use_item(car, player_id)
        # Oberflächen-Staub
        theme_name = getattr(getattr(self.track, "theme", None), "name", "standard")
        emit_dust = surface == "grass" or theme_name in ("ice", "desert")
        if emit_dust and abs(s.speed) > 25:
            dust_type = (
                "ice"
                if theme_name == "ice"
                else "desert" if theme_name == "desert" else "grass"
            )
            self.entity_particles.emit_dust(s.x, s.y, s.angle, s.speed, dust_type)

    def _use_item(self, car: "Car", player_id: int) -> None:
        """Item aus dem Inventar aktivieren – alle Items zentral hier."""
        s = car.state
        item = car.inventory
        rad = math.radians(s.angle)
        sin_a, cos_a = math.sin(rad), math.cos(rad)

        if item == "pocket_boost":
            car.boost_timer = BoostPad.BOOST_DURATION
            if s.speed < BoostPad.BOOST_SPEED * 0.5:
                s.speed = BoostPad.BOOST_SPEED * 0.5
            self.entity_particles.emit_boost_sparks(s.x, s.y)

        elif item == "oil_drop":
            # 80px hinter dem Auto ablegen (entgegen Fahrtrichtung)
            drop_dist = 80.0
            ox = s.x - sin_a * drop_dist
            oy = s.y + cos_a * drop_dist
            new_oil = OilSlick(ox, oy, slick_id=len(self.oils))
            new_oil.set_pvp_mode(self.mode == 3)
            self.oils.append(new_oil)
            self.entity_particles.emit_boost_sparks(ox, oy)

        elif item == "green_boomerang":
            bid = len(self.boomerangs)
            # 40px vor dem Auto spawnen
            bx = s.x + sin_a * 40
            by = s.y - cos_a * 40
            self.boomerangs.append(
                GreenBoomerang(bx, by, s.angle, player_id, brang_id=bid)
            )
            self.entity_particles.emit_boost_sparks(bx, by)
            if _SM:
                _SM.play_boomerang()

        elif item == "red_boomerang":
            bid = len(self.boomerangs)
            bx = s.x + sin_a * 40
            by = s.y - cos_a * 40
            self.boomerangs.append(
                RedBoomerang(bx, by, s.angle, player_id, brang_id=bid)
            )
            self.entity_particles.emit_boost_sparks(bx, by)
            if _SM:
                _SM.play_boomerang()

        car.inventory = None

    def _cycle_car_class(self, car: "Car", player_id: int) -> None:
        """Wechselt die Fahrzeugklasse (balanced → speedster → tank → …)."""
        idx = CLASS_ORDER.index(car.car_class) if car.car_class in CLASS_ORDER else 0
        new = CLASS_ORDER[(idx + 1) % len(CLASS_ORDER)]
        cs = CAR_CLASSES[new]
        col = cs["color_host"] if player_id == PLAYER_HOST else cs["color_client"]
        car._body_color = col
        car.set_class(new)

    def reset_for_mode(self, new_mode: int) -> None:
        """
        Modus-Wechsel: pvp_mode auf allen Entitäten aktualisieren und
        collected_by leeren, damit beide Spieler alle Objekte einsammeln können.
        Wird aufgerufen wenn Host zwischen Modus 1/2/3 wechselt.
        """
        pvp = new_mode == 3
        for obj in (*self.canisters, *self.boosts, *self.oils, *self.item_boxes):
            obj.set_pvp_mode(pvp)
            obj.collected_by.clear()
        self.boomerangs.clear()
        for car in self.cars:
            car.inventory = None

    def _resolve_car_collision(self) -> None:
        s0, s1 = self.cars[0].state, self.cars[1].state
        r = self.cars[0].get_radius()
        dist = math.hypot(s0.x - s1.x, s0.y - s1.y)
        if dist < r * 2 and dist > 0.1:
            nx = (s0.x - s1.x) / dist
            ny = (s0.y - s1.y) / dist
            overlap = r * 2 - dist
            s0.x += nx * overlap * 0.5
            s0.y += ny * overlap * 0.5
            s1.x -= nx * overlap * 0.5
            s1.y -= ny * overlap * 0.5
            v0, v1 = s0.speed, s1.speed
            s0.speed = v1 * 0.6
            s1.speed = v0 * 0.6

    def _update_camera_pvp(self, dt: float) -> None:
        s0, s1 = self.cars[0].state, self.cars[1].state
        dist = math.hypot(s0.x - s1.x, s0.y - s1.y)
        target_zoom = max(0.35, min(1.0, 600.0 / max(dist, 600.0)))
        self.camera.zoom += (target_zoom - self.camera.zoom) * 0.05
        self.camera.update(s0.x, s0.y, dt)

    # ─── Rendering ───────────────────────────────────────────────────────────

    def draw_world(self, surface: pygame.Surface) -> None:
        zoom = self.camera.zoom
        off_x, off_y = self.camera.offset()
        bg_color = getattr(getattr(self.track, "theme", None), "bg_fill", GRASS_DARK)
        surface.fill(bg_color)
        self.track.draw(surface, off_x, off_y, zoom)
        self.walls.draw(surface, off_x, off_y, zoom)
        # Props: rein kosmetisch, hinter Spielobjekten
        self.props.draw(surface, off_x, off_y, zoom)
        self.particles.draw(surface, off_x, off_y, zoom)
        self.entity_particles.draw(surface, off_x, off_y, zoom)
        for o in self.oils:
            o.draw(surface, off_x, off_y, zoom, player_id=PLAYER_HOST)
        for b in self.boosts:
            b.draw(surface, off_x, off_y, zoom, player_id=PLAYER_HOST)
        for ib in self.item_boxes:
            ib.draw(surface, off_x, off_y, zoom, player_id=PLAYER_HOST)
        for c in self.canisters:
            c.draw(surface, off_x, off_y, zoom, player_id=PLAYER_HOST)
        if self._fuel_flash > 0:
            alpha = int(120 * min(1.0, self._fuel_flash / 0.5))
            self._flash_surf.fill((255, 200, 0, alpha))
            surface.blit(self._flash_surf, (0, 0))
        for car in self.cars:
            if self.mode != 3 and car is self.cars[1]:
                continue
            car.draw(surface, off_x, off_y, zoom)
        for brang in self.boomerangs:
            brang.draw(surface, off_x, off_y, zoom)

    def draw_fog(self, surface: pygame.Surface, car_screen_pos: tuple) -> None:
        cx, cy = int(car_screen_pos[0]), int(car_screen_pos[1])
        self._fog_surf.fill((0, 0, 0, FOG_ALPHA))
        pygame.draw.circle(self._fog_surf, (0, 0, 0, 0), (cx, cy), FOG_RADIUS)
        surface.blit(self._fog_surf, (0, 0))

    def draw_pings(self, surface: pygame.Surface) -> None:
        """Draw navigator pings with ripple animation, color urgency shift, and distance cue."""
        now_ms = pygame.time.get_ticks()
        car_x = self.cars[0].state.x
        car_y = self.cars[0].state.y

        for wx, wy, timer in self.pings:
            sx, sy = self.camera.w2s(wx, wy)
            frac = max(0.0, timer / PING_DURATION)  # 1.0 → 0.0 as ping ages

            # Color shift: cyan → orange → red based on age
            if frac > 0.5:
                t = (frac - 0.5) * 2.0  # 1.0 at fresh, 0.0 at half-life
                r = int(0 * t + 255 * (1 - t))
                g = int(220 * t + 165 * (1 - t))
                b = int(255 * t + 0 * (1 - t))
            else:
                t = frac * 2.0  # 1.0 at half-life, 0.0 at expiry
                r = int(255 * 1.0)
                g = int(165 * t + 60 * (1 - t))
                b = 0
            base_color = (r, g, b)

            # Distance cue: scale max ripple radius by world-distance (clamped)
            world_dist = math.hypot(wx - car_x, wy - car_y)
            dist_scale = min(1.0, world_dist / 600.0)
            max_ripple_r = int(18 + 22 * dist_scale)

            # Ripple rings: 3 rings with phase offset
            alpha_base = int(max(40, 200 * frac))
            for ring in range(3):
                phase_offset = ring * 400  # ms offset per ring
                ring_t = ((now_ms + phase_offset) % 1200) / 1200.0  # 0→1 over 1.2s
                ring_r = int(8 + (max_ripple_r - 8) * ring_t)
                ring_alpha = int(alpha_base * (1.0 - ring_t) * 0.8)
                if ring_r < 2 or ring_alpha < 5:
                    continue
                size = ring_r * 2 + 4
                mid = ring_r + 2
                tmp = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.circle(tmp, (*base_color, ring_alpha), (mid, mid), ring_r, 2)
                surface.blit(tmp, (int(sx) - mid, int(sy) - mid))

            # Static center dot + cross-arms (always visible)
            core_alpha = int(max(80, 220 * frac))
            core_size = 32
            core_mid = 16
            core = pygame.Surface((core_size, core_size), pygame.SRCALPHA)
            pygame.draw.circle(core, (*base_color, core_alpha), (core_mid, core_mid), 5, 2)
            for dx, dy in [(10, 0), (-10, 0), (0, 10), (0, -10)]:
                pygame.draw.line(core, (*base_color, core_alpha),
                                 (core_mid, core_mid),
                                 (core_mid + dx, core_mid + dy), 2)
            pygame.draw.circle(core, (255, 255, 160, core_alpha), (core_mid, core_mid), 3)
            surface.blit(core, (int(sx) - core_mid, int(sy) - core_mid))

        # Draw off-screen arrows for pings not visible in current viewport
        self.draw_ping_arrows(surface)

    def draw_ping_arrows(self, surface: pygame.Surface) -> None:
        """Draw edge arrows pointing toward pings that are off-screen."""
        margin = 28
        for wx, wy, timer in self.pings:
            sx, sy = self.camera.w2s(wx, wy)
            # Skip pings already visible on screen
            if margin <= sx <= SCREEN_W - margin and margin <= sy <= SCREEN_H - margin:
                continue

            frac = max(0.0, timer / PING_DURATION)
            alpha = int(max(80, 220 * frac))
            # Color shift same as draw_pings
            if frac > 0.5:
                t = (frac - 0.5) * 2.0
                color = (int(255 * (1 - t)), int(220 * t + 165 * (1 - t)), int(255 * t))
            else:
                color = (255, int(165 * frac * 2 + 60 * (1 - frac * 2)), 0)

            # Clamp to screen edge with margin
            cx = max(margin, min(SCREEN_W - margin, sx))
            cy = max(margin, min(SCREEN_H - margin, sy))

            # Draw arrow pointing from edge toward the ping
            dx = sx - SCREEN_W // 2
            dy = sy - SCREEN_H // 2
            length = math.hypot(dx, dy)
            if length < 1:
                continue
            nx, ny = dx / length, dy / length

            # Arrow tip at clamped position
            tip = (int(cx), int(cy))
            # Arrow body
            back_x = int(cx - nx * 14)
            back_y = int(cy - ny * 14)
            perp_x = int(-ny * 7)
            perp_y = int(nx * 7)

            arrow_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            pygame.draw.polygon(arrow_surf, (*color, alpha), [
                tip,
                (back_x + perp_x, back_y + perp_y),
                (back_x - perp_x, back_y - perp_y),
            ])
            surface.blit(arrow_surf, (0, 0))

    def draw_hud(self, surface: pygame.Surface) -> None:
        s = self.cars[0].state
        self.hud.draw(
            surface,
            s.speed,
            s.fuel,
            self.elapsed_time,
            inventory=self.cars[0].inventory,
            car_class=self.cars[0].car_class,
        )
        if not self.game_over and self._race_started:
            if self.track.surface_at(s.x, s.y) == "grass":
                lbl = self._warn_font.render("OFF TRACK", True, YELLOW)
                surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H - 40))

    def draw_countdown(self, surface: pygame.Surface) -> None:
        if self._countdown > 0:
            step_idx = min(
                int(self._countdown / COUNTDOWN_STEP_DURATION), len(COUNTDOWN_STEPS) - 1
            )
            num = COUNTDOWN_STEPS[-(step_idx + 1)]
            color = [RED, ORANGE, YELLOW][min(step_idx, 2)]
            lbl = self._countdown_font.render(str(num), True, color)
            sx = (SCREEN_W - lbl.get_width()) // 2
            sy = (SCREEN_H - lbl.get_height()) // 2
            shd = self._countdown_font.render(str(num), True, BLACK)
            surface.blit(shd, (sx + 4, sy + 4))
            surface.blit(lbl, (sx, sy))
        elif self._go_timer > 0:
            lbl = self._countdown_font.render("GO!", True, GREEN)
            sx = (SCREEN_W - lbl.get_width()) // 2
            sy = (SCREEN_H - lbl.get_height()) // 2
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
        mins = int(self.elapsed_time) // 60
        secs = int(self.elapsed_time) % 60
        cs = int((self.elapsed_time % 1) * 100)
        t_lbl = self._sub_font.render(
            f"Zeit: {mins:02d}:{secs:02d}.{cs:02d}", True, WHITE
        )
        surface.blit(t_lbl, ((SCREEN_W - t_lbl.get_width()) // 2, cy))
        cy += t_lbl.get_height() + 28
        r_lbl = self._sub_font.render("[R]  Neustart", True, CYAN)
        m_lbl = self._sub_font.render("[M]  Main Menu", True, YELLOW)
        surface.blit(r_lbl, ((SCREEN_W - r_lbl.get_width()) // 2, cy))
        surface.blit(
            m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, cy + r_lbl.get_height() + 12)
        )

    def draw_pause_overlay(self, surface: pygame.Surface) -> None:
        """Erweitertes Pause-Overlay mit Lobby/Quit-Buttons (Phase 11)."""
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        cx = SCREEN_W // 2
        bw, bh, gap = 300, 52, 14
        labels = [
            ("resume", "[P/ESC]  Resume", (40, 90, 40)),
            ("lobby", "[L]      Back to Lobby", (40, 60, 120)),
            ("quit", "[Q]      Quit Game", (90, 30, 30)),
        ]
        total_h = len(labels) * (bh + gap) - gap
        y0 = SCREEN_H // 2 - total_h // 2 + 30

        # Titel
        lbl = self._pause_font.render("PAUSE", True, CYAN)
        shd = self._pause_font.render("PAUSE", True, BLACK)
        tx = cx - lbl.get_width() // 2
        ty = y0 - lbl.get_height() - 16
        surface.blit(shd, (tx + 3, ty + 3))
        surface.blit(lbl, (tx, ty))

        mouse = pygame.mouse.get_pos()
        self._pause_btn_rects = {}
        for key, text, col in labels:
            rect = pygame.Rect(cx - bw // 2, y0, bw, bh)
            self._pause_btn_rects[key] = rect
            hovered = rect.collidepoint(mouse)
            bg = tuple(min(255, c + 30) for c in col) if hovered else col
            # Shadow
            pygame.draw.rect(surface, (0, 0, 0, 120), rect.move(3, 4), border_radius=8)
            pygame.draw.rect(surface, bg, rect, border_radius=8)
            pygame.draw.rect(surface, (150, 180, 220), rect, 1, border_radius=8)
            btn_lbl = self._sub_font.render(
                text, True, WHITE if hovered else (200, 210, 230)
            )
            surface.blit(
                btn_lbl,
                (
                    rect.centerx - btn_lbl.get_width() // 2,
                    rect.centery - btn_lbl.get_height() // 2,
                ),
            )
            y0 += bh + gap

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
