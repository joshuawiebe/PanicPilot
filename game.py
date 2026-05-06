# =============================================================================
#  game.py  –  Panic Pilot | Main game loop (Phase 5.3)
# =============================================================================
#
#  Phase 5.3 changes:
#    1. Props       – PropManager creates/renders decorative biome objects
#    2. PvP start   – Mode 3: cars start side-by-side (side_offset)
#    3. Pause       – P key toggles _paused; guard in update() + overlay
#    4. Speed Scale – self.speed_scale scales dt in apply_input()
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
    PLAYER_HOST,
    PLAYER_CLIENT,
    BOOMERANG_SPEED,
)
from particles import ParticleSystem
from props import PropManager

try:
    import main as _main_mod
except Exception:
    _main_mod = None

# Phase 12: Audio (lazy import – works without sound_manager.py too)
try:
    import sound_manager as _sound_mod

    _SM = _sound_mod.get()
except Exception:
    _SM = None

FOG_ALPHA = 255
FOG_RADIUS = int(min(SCREEN_W, SCREEN_H) * 0.085)

PING_DURATION = 5.0
MAX_PINGS = 15
PING_BLINK_HZ = 3.0

COUNTDOWN_STEPS = [3, 2, 1]
COUNTDOWN_STEP_DURATION = 1.0
GO_DISPLAY_DURATION = 1.2

# Speed scaling: scales dt in apply_input()
SPEED_SCALE_SLOW = 0.70
SPEED_SCALE_NORMAL = 1.00
SPEED_SCALE_FAST = 1.40


class Game:
    """
    Base game loop.
    self.cars[0] = Host/Solo, self.cars[1] = Client (Mode 3)
    self._paused: bool        – P key
    self.speed_scale: float   – Speed scaling
    """

    def __init__(
        self,
        screen: "pygame.Surface | None" = None,
        locked_class0: str = "balanced",
        locked_class1: str = "balanced",
        host_room_name: str = "Host",
        client_room_name: str = "Client",
    ) -> None:

        if screen is None:
            pygame.init()
            import settings as _s
            if getattr(_s, "FULLSCREEN", False):
                try:
                    info = pygame.display.Info()
                    w, h = info.current_w, info.current_h
                except Exception:
                    w, h = 1920, 1080
                flags = pygame.FULLSCREEN
            else:
                w = getattr(_s, "DISPLAY_W", 1920)
                h = getattr(_s, "DISPLAY_H", 1080)
                flags = pygame.RESIZABLE
            self.screen = pygame.display.set_mode((w, h), flags)
        else:
            self.screen = screen
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.mode = 1
        self.pings: list[list] = []
        self._return_to_menu = False
        # Phase 12: Countdown step tracking for sound
        self._last_cdstep = -1
        self._return_to_lobby = False  # Phase 11: Lobby return
        self._lobby_initiator = ""  # "self" | "remote"
        self._paused = False
        self.speed_scale = SPEED_SCALE_NORMAL
        self._pause_btn_rects: dict = {}  # populated by draw_pause_overlay

        # Classes locked before race – no in-game switching
        self._locked_class0 = locked_class0
        self._locked_class1 = locked_class1

        self._host_room_name = host_room_name
        self._client_room_name = client_room_name

        self._warn_font = pygame.font.SysFont("Arial", 18, bold=True)
        self._countdown_font = pygame.font.SysFont("Arial", 160, bold=True)
        self._win_font = pygame.font.SysFont("Arial", 72, bold=True)
        self._sub_font = pygame.font.SysFont("Arial", 28, bold=True)
        self._pause_font = pygame.font.SysFont("Arial", 80, bold=True)

        self._flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._fog_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._overlay_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._overlay_surf.fill((0, 0, 0, 160))

        # Grain surface for Panic mode (cached, regenerated periodically)
        self._grain_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._grain_timer = 0.0
        self._grain_interval = 0.08
        self._regen_grain()

        self.camera = Camera()
        self._init_game_objects()

        # Screen shake state
        self._shake_amount = 0.0
        self._shake_decay = 8.0
        self._shake_offset = (0, 0)

        # Item pickup flash state
        self._item_flash_timer = 0.0
        self._item_flash_color = (255, 255, 255)

    def _regen_grain(self) -> None:
        import random as _r
        self._grain_surf.fill((0, 0, 0, 0))
        for _ in range(3000):
            gx = _r.randint(0, SCREEN_W - 1)
            gy = _r.randint(0, SCREEN_H - 1)
            ga = _r.randint(8, 30)
            self._grain_surf.set_at((gx, gy), (255, 255, 255, ga))

    # ─── Initialisierung ─────────────────────────────────────────────────────

    def _init_game_objects(self, track: Optional[Track] = None) -> None:
        self.track = track if track is not None else Track.generate()

        sx, sy, sa = self.track.start_x, self.track.start_y, self.track.start_angle
        rad = math.radians(sa)

        # PvP: Cars side-by-side instead of behind each other
        # Perpendicular vector to driving direction
        side_x = math.cos(rad)
        side_y = math.sin(rad)
        side_offset = 36

        # Classes from locked values (lobby selection)
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

        # Canisters with IDs (for network sync)
        # In mode 3 (PvP) activate pvp_mode so collected_by works correctly
        pvp = self.mode == MODE_PVP
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

        self.entity_particles = ParticleSystem()
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

    # ─── Events ───────────────────────────────────────────────────────────

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if _main_mod and _main_mod._handle_global_key(event):
                continue
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_pause_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_p):
                    if self.game_over or self.winner:
                        if event.key == pygame.K_ESCAPE:
                            self.running = False
                            self._return_to_lobby = True
                    else:
                        self._paused = not self._paused
                        if _SM:
                            _SM.play_pause()
                            if self._paused:
                                _SM.pause_fade(200)
                            else:
                                _SM.resume_fade(300)
                                _SM.engine_start()
                elif event.key == pygame.K_r:
                    if not self._paused:
                        self.reset()
                    return
                elif event.key == pygame.K_m and (self.game_over or self.winner):
                    self.running = False
                    self._return_to_menu = True
                # Pause menu shortcuts
                elif self._paused:
                    if event.key == pygame.K_s:
                        self._open_pause_settings()
                    elif event.key == pygame.K_l:
                        self._do_return_to_lobby()
                    elif event.key == pygame.K_q:
                        self.running = False
                else:
                    self._on_keydown(event)

    def _handle_pause_click(self, pos: tuple) -> None:
        """Processes mouse clicks on pause menu buttons."""
        if not self._paused:
            return
        action = None
        for key, rect in self._pause_btn_rects.items():
            if rect.collidepoint(pos):
                action = key
                break
        if action == "resume":
            self._paused = False
        elif action == "settings":
            self._open_pause_settings()
        elif action == "lobby":
            self._do_return_to_lobby()
        elif action == "quit":
            self.running = False

    def _do_return_to_lobby(self) -> None:
        """Sets lobby return flag and ends the race (Phase 11)."""
        self._return_to_lobby = True
        self._lobby_initiator = "self"
        self._paused = False
        self.running = False

    def _open_pause_settings(self) -> None:
        """Shows in-game settings panel while game is paused."""
        import settings as _s
        if _main_mod is None:
            return

        # Capture current screen as background
        background = self.screen.copy()

        username = getattr(_s, "USERNAME", "").strip() or "Player"
        settings_scene = _main_mod.InGameSettingsScene(
            self.screen,
            background,
            current_mode=self.mode,
            current_track_length=getattr(self, "_host_track_length", 20),
            net=None,  # Solo mode has no network
            is_host=True,
            username=username,
        )
        changes = settings_scene.run()

        # Apply changes
        if changes:
            if "mode" in changes:
                self.mode = changes["mode"]
                self.reset()
            if "track_length" in changes:
                if hasattr(self, "_host_track_length"):
                    self._host_track_length = changes["track_length"]
                self.reset()

        # Game stays paused when returning

    def _on_keydown(self, event) -> None:
        pass

    # ─── Update ───────────────────────────────────────────────────────────

    def update(
        self,
        dt: float,
        input_override: Optional[InputState] = None,
        input_car1: Optional[InputState] = None,
    ) -> None:
        # Pause guard: completely freeze when paused
        if self._paused:
            return

        # Decay screen shake
        if self._shake_amount > 0:
            self._shake_amount = max(0, self._shake_amount - self._shake_decay * dt)

        # Regenerate grain for Panic mode
        self._grain_timer += dt
        if self._grain_timer >= self._grain_interval and self.mode == MODE_PANIC:
            self._regen_grain()
            self._grain_timer = 0.0

        # Decay item pickup flash
        if self._item_flash_timer > 0:
            self._item_flash_timer -= dt

        self.pings = [p for p in self.pings if p[2] > 0]
        if len(self.pings) > MAX_PINGS:
            self.pings = self.pings[-MAX_PINGS:]
        for p in self.pings:
            p[2] -= dt

        # Ensure variable exists, regardless of what happens in __init__
        if not hasattr(self, "_last_cdstep"):
            self._last_cdstep = -1

        # Countdown
        if self._countdown > 0:
            self._countdown -= dt
            # ── Phase 12: Countdown beep at each step ────────────────────
            cdstep = int(self._countdown)
            if cdstep != self._last_cdstep:
                self._last_cdstep = cdstep
                if _SM and self._countdown > 0:
                    _SM.play_countdown_beep()
            if self._countdown <= 0:
                self._countdown = 0.0
                self._go_timer = GO_DISPLAY_DURATION
                self._race_started = True
                # ── GO sound + engine start ───────────────────────────────
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

        # Speed-Scale: scale dt in apply_input
        # Higher value → stronger acceleration + higher top speed
        scaled_dt = dt * self.speed_scale

        # ── Car 0 ─────────────────────────────────────────────────────────
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
        speed_delta = abs(_pre_speed0 - s0.speed)
            # ── Phase 12: Detect wall collision ──────────────────────────
        if _SM and speed_delta > 40:
            _SM.play_collision(min(1.0, abs(_pre_speed0) / 400.0))
            self._shake_amount = min(12, speed_delta / 30)

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

        # ── Car 1 (Mode 3) ──────────────────────────────────────────────
        if self.mode == MODE_PVP and input_car1 is not None:
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

        # ── Pickups: Canisters / Boost Pads / Oil slicks / Item boxes ──────
        for c in self.canisters:
            c.update(dt)
        for b in self.boosts:
            b.update(dt)
        for o in self.oils:
            o.update(dt)
        for ib in self.item_boxes:
            ib.update(dt)
        self._apply_pickups(self.cars[0], PLAYER_HOST, surf0, inp0.use_item)
        if self.mode == MODE_PVP:
            s1 = self.cars[1].state
            surf1_now = self.track.surface_at(s1.x, s1.y)
            use1 = input_car1.use_item if input_car1 is not None else False
            self._apply_pickups(self.cars[1], PLAYER_CLIENT, surf1_now, use1)
        if self._fuel_flash > 0:
            self._fuel_flash -= dt
        self.entity_particles.update(dt)

        # ── Boomerangs ────────────────────────────────────────────────────────
        # Target positions for RedBoomerang
        pos = [
            (c.state.x, c.state.y)
            for c in self.cars
            if self.mode == MODE_PVP or c is self.cars[0]
        ]
        for brang in self.boomerangs:
            if not brang.active:
                continue
            if isinstance(brang, GreenBoomerang):
                brang.update(dt, self.track)
            else:
                # Find next non-own car as target
                tx, ty = None, None
                for i, car in enumerate(self.cars):
                    pid = PLAYER_HOST if i == 0 else PLAYER_CLIENT
                    if pid != brang.owner_id:
                        tx, ty = car.state.x, car.state.y
                        break
                brang.update(dt, self.track, tx, ty)
            # Check collision with all cars
            for i, car in enumerate(self.cars):
                if self.mode != MODE_PVP and i == 1:
                    continue
                pid = PLAYER_HOST if i == 0 else PLAYER_CLIENT
                if brang.check_hit(car.state.x, car.state.y, pid):
                    car.spin_timer = OilSlick.SPIN_DURATION
                    self.entity_particles.emit_boost_sparks(car.state.x, car.state.y)
        # Remove inactive boomerangs (not more often than needed)
        if any(not b.active for b in self.boomerangs):
            self.boomerangs = [b for b in self.boomerangs if b.active]

        # ── Win Condition: Out of fuel ───────────────────────────────────
        if self.winner is None:
            if s0.fuel <= 0.0:
                self.winner = "client" if self.mode == MODE_PVP else None
                self.game_over = True
                if _SM:
                    _SM.engine_stop()
            elif self.mode == MODE_PVP:
                s1 = self.cars[1].state
                if s1.fuel <= 0.0:
                    self.winner = "host"
                    self.game_over = True
                    if _SM:
                        _SM.engine_stop()

        # ── Win Condition: Finish line ───────────────────────────────────
        if self.winner is None and not self.game_over:
            if self.track.crosses_finish(s0.x, s0.y, self.cars[0].get_radius()):
                self.winner = "host"
                self.game_over = True
                if _SM:
                    _SM.engine_stop()
                    _SM.play_win_fanfare()
            elif self.mode == MODE_PVP:
                s1 = self.cars[1].state
                if self.track.crosses_finish(s1.x, s1.y, self.cars[1].get_radius()):
                    self.winner = "client"
                    self.game_over = True
                    if _SM:
                        _SM.engine_stop()

        # ── Kamera ───────────────────────────────────────────────────────────
        if self.mode == MODE_PVP:
            self._update_camera_pvp(dt)
        else:
            speed_zoom = max(0.5, min(1.2, 1.2 - abs(s0.speed) / 2500))
            self.camera.update(s0.x, s0.y, dt, target_zoom=speed_zoom)

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

        # ── Phase 12: Engine sound live update ────────────────────────────
        if _SM:
            from settings import CAR_MAX_SPEED

            _SM.update_engine(s0.speed, CAR_MAX_SPEED, dt, surface=surf0)

        if self.mode == MODE_SPLIT:
            self.camera.zoom = 1.0

    # ─── Physics helpers ────────────────────────────────────────────────

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
        """Canisters, boost pads, oil slicks, item boxes, and item activation."""
        s = car.state
        # Canisters
        for c in self.canisters:
            if c.try_pickup(s.x, s.y, player_id=player_id):
                s.fuel = min(FUEL_MAX, s.fuel + FUEL_CANISTER_VALUE)
                self.particles.emit_pickup(c.x, c.y)
                if player_id == PLAYER_HOST:
                    self._fuel_flash = 0.5
                    self._item_flash_timer = 0.25
                    self._item_flash_color = (80, 255, 80)
                    if _SM:
                        _SM.play_pickup_fuel()
        # Boost pads
        for b in self.boosts:
            if b.try_trigger(s.x, s.y, player_id=player_id):
                car.boost_timer = BoostPad.BOOST_DURATION
                if s.speed < BoostPad.BOOST_SPEED * 0.5:
                    s.speed = BoostPad.BOOST_SPEED * 0.5
                self.entity_particles.emit_boost_sparks(b.x, b.y)
        # Oil slicks
        for o in self.oils:
            if o.try_trigger(s.x, s.y, player_id=player_id):
                car.spin_timer = OilSlick.SPIN_DURATION
        # Item boxes – only when inventory empty
        for ib in self.item_boxes:
            item = ib.try_pickup(s.x, s.y, player_id=player_id)
            if item and car.inventory is None:
                car.inventory = item
                self.entity_particles.emit_boost_sparks(ib.x, ib.y)
                if player_id == PLAYER_HOST:
                    self._item_flash_timer = 0.3
                    colors = {"oil": (50, 50, 50), "boomerang": (255, 200, 0), "boost": (255, 100, 0)}
                    self._item_flash_color = colors.get(item, (200, 200, 255))
                    if _SM:
                        _SM.play_pickup_item()
        # Use item (SPACE / use_item flag)
        if use_item and car.inventory is not None:
            self._use_item(car, player_id)
        # Surface dust
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
        """Activate item from inventory – all items handled centrally here."""
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
            # Drop 80px behind car (against driving direction)
            drop_dist = 80.0
            ox = s.x - sin_a * drop_dist
            oy = s.y + cos_a * drop_dist
            new_oil = OilSlick(ox, oy, slick_id=len(self.oils))
            new_oil.set_pvp_mode(self.mode == MODE_PVP)
            self.oils.append(new_oil)
            self.entity_particles.emit_boost_sparks(ox, oy)

        elif item == "green_boomerang":
            bid = len(self.boomerangs)
            # Spawn 40px in front of car
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
        """Switches the vehicle class (balanced → speedster → tank → …)."""
        idx = CLASS_ORDER.index(car.car_class) if car.car_class in CLASS_ORDER else 0
        new = CLASS_ORDER[(idx + 1) % len(CLASS_ORDER)]
        cs = CAR_CLASSES[new]
        col = cs["color_host"] if player_id == PLAYER_HOST else cs["color_client"]
        car._body_color = col
        car.set_class(new)

    def reset_for_mode(self, new_mode: int) -> None:
        """
        Mode change: update pvp_mode on all entities and
        clear collected_by so both players can collect all objects.
        Called when host switches between modes 1/2/3.
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

    # ─── Rendering ────────────────────────────────────────────────────────

    def draw_world(self, surface: pygame.Surface) -> None:
        zoom = self.camera.zoom
        off_x, off_y = self.camera.offset()
        # Apply screen shake
        if self._shake_amount > 0.5:
            import random as _rand
            sx = int(self._shake_amount * (_rand.random() - 0.5) * 2)
            sy = int(self._shake_amount * (_rand.random() - 0.5) * 2)
            off_x += sx
            off_y += sy
        bg_color = getattr(getattr(self.track, "theme", None), "bg_fill", GRASS_DARK)
        surface.fill(bg_color)
        self.track.draw(surface, off_x, off_y, zoom)
        self.walls.draw(surface, off_x, off_y, zoom)
        # Props: purely cosmetic, behind game objects
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
        if self._item_flash_timer > 0:
            alpha = int(150 * min(1.0, self._item_flash_timer / 0.3))
            self._flash_surf.fill((*self._item_flash_color, alpha))
            surface.blit(self._flash_surf, (0, 0))
        for car in self.cars:
            if self.mode != MODE_PVP and car is self.cars[1]:
                continue
            car.draw(surface, off_x, off_y, zoom)
        for brang in self.boomerangs:
            brang.draw(surface, off_x, off_y, zoom)

    def draw_fog(self, surface: pygame.Surface, car_screen_pos: tuple) -> None:
        cx, cy = int(car_screen_pos[0]), int(car_screen_pos[1])
        self._fog_surf.fill((0, 0, 0, FOG_ALPHA))
        pygame.draw.circle(self._fog_surf, (0, 0, 0, 0), (cx, cy), FOG_RADIUS)
        surface.blit(self._fog_surf, (0, 0))
        if self.mode == MODE_PANIC:
            surface.blit(self._grain_surf, (0, 0))

    def draw_ping_glow_through_fog(self, surface: pygame.Surface) -> None:
        """Draw ping glow effects that pierce through fog before fog is applied."""
        car_x = self.cars[0].state.x
        car_y = self.cars[0].state.y
        now_ms = pygame.time.get_ticks()

        for wx, wy, timer in self.pings:
            sx, sy = self.camera.w2s(wx, wy)
            frac = max(0.0, timer / PING_DURATION)

            # Glow radius that pierces through fog
            glow_radius = int(60 + 40 * frac)
            world_dist = math.hypot(wx - car_x, wy - car_y)
            dist_scale = min(1.0, world_dist / 800.0)
            glow_radius = int(glow_radius * (0.7 + 0.3 * dist_scale))

            # Color based on urgency
            if frac > 0.5:
                t = (frac - 0.5) * 2.0
                r = int(0 * t + 255 * (1 - t))
                g = int(220 * t + 165 * (1 - t))
                b = int(255 * t + 0 * (1 - t))
            else:
                t = frac * 2.0
                r = 255
                g = int(165 * t + 60 * (1 - t))
                b = 0

            # Pulsing glow effect
            pulse = 0.8 + 0.2 * math.sin(now_ms / 200.0)
            alpha = int(100 * frac * pulse)

            # Draw radial glow that will show through fog
            glow_surf = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
            center = glow_radius
            for radius in range(glow_radius, 0, -2):
                ring_alpha = int(alpha * (1.0 - radius / glow_radius))
                if ring_alpha > 0:
                    pygame.draw.circle(glow_surf, (r, g, b, ring_alpha), (center, center), radius)
            surface.blit(glow_surf, (int(sx) - glow_radius, int(sy) - glow_radius))

    def draw_pings(self, surface: pygame.Surface) -> None:
        """Draw navigator pings with ripple animation, color urgency shift, and distance cue."""
        now_ms = pygame.time.get_ticks()
        car_x = self.cars[0].state.x
        car_y = self.cars[0].state.y

        for wx, wy, timer in self.pings:
            sx, sy = self.camera.w2s(wx, wy)
            frac = max(0.0, timer / PING_DURATION)

            # Bright color shift: pure yellow/white → orange → red
            if frac > 0.5:
                t = (frac - 0.5) * 2.0
                r = 255
                g = int(255 * t + 165 * (1 - t))
                b = int(180 * t)
            else:
                t = frac * 2.0
                r = 255
                g = int(165 * t + 60 * (1 - t))
                b = 0
            base_color = (r, g, b)

            # Distance cue: scale max ripple radius by world-distance (clamped)
            world_dist = math.hypot(wx - car_x, wy - car_y)
            dist_scale = min(1.0, world_dist / 600.0)
            max_ripple_r = int(22 + 28 * dist_scale)

            # Pulsing effect
            pulse = 0.9 + 0.1 * math.sin(now_ms / 150.0)

            # Ripple rings: 3 rings with phase offset
            alpha_base = int(max(80, 240 * frac))
            for ring in range(3):
                phase_offset = ring * 400
                ring_t = ((now_ms + phase_offset) % 1200) / 1200.0
                ring_r = int(10 + (max_ripple_r - 10) * ring_t)
                ring_alpha = int(alpha_base * (1.0 - ring_t) * 0.9 * pulse)
                if ring_r < 2 or ring_alpha < 5:
                    continue
                size = ring_r * 2 + 6
                mid = ring_r + 3
                tmp = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.circle(tmp, (*base_color, ring_alpha), (mid, mid), ring_r, 3)
                surface.blit(tmp, (int(sx) - mid, int(sy) - mid))

            # Static center dot + cross-arms (bright and highly visible)
            core_alpha = int(max(120, 255 * frac * pulse))
            core_size = 40
            core_mid = 20
            core = pygame.Surface((core_size, core_size), pygame.SRCALPHA)
            pygame.draw.circle(core, (*base_color, core_alpha), (core_mid, core_mid), 7, 3)
            for dx, dy in [(14, 0), (-14, 0), (0, 14), (0, -14)]:
                pygame.draw.line(core, (*base_color, core_alpha),
                                 (core_mid, core_mid),
                                 (core_mid + dx, core_mid + dy), 3)
            pygame.draw.circle(core, (255, 255, 240, core_alpha), (core_mid, core_mid), 5)
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

            # Direction from center to ping
            dx = sx - SCREEN_W // 2
            dy = sy - SCREEN_H // 2
            length = math.hypot(dx, dy)
            if length < 1:
                continue

            # Draw arrow pointing from edge toward the ping
            angle = math.degrees(math.atan2(dy, dx)) - 90
            arrow_surf = pygame.Surface((20, 16), pygame.SRCALPHA)
            pygame.draw.polygon(arrow_surf, (*color, alpha), [
                (10, 0),
                (0, 16),
                (20, 16),
            ])
            rotated = pygame.transform.rotate(arrow_surf, angle)
            surface.blit(rotated, (int(cx) - rotated.get_width() // 2, int(cy) - rotated.get_height() // 2))

    def draw_hud(self, surface: pygame.Surface) -> None:
        s = self.cars[0].state
        self.hud.draw(
            surface,
            s.speed,
            s.fuel,
            self.elapsed_time,
            inventory=self.cars[0].inventory,
            car_class=self.cars[0].car_class,
            game_over=self.game_over,
        )
        if not self.game_over and self._race_started and self._countdown <= 0:
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
        surface.blit(self._overlay_surf, (0, 0))
        cy = SCREEN_H // 2 - 80
        if self.mode == MODE_PVP:
            if self.winner == "host":
                txt, color = f"{self._host_room_name.upper()} WINS!", CAR_COLOR_HOST
            elif self.winner == "client":
                txt, color = f"{self._client_room_name.upper()} WINS!", CAR_COLOR_CLIENT
            else:
                txt, color = "OUT OF FUEL!", ORANGE
        else:
            txt, color = ("FINISH!", YELLOW) if self.winner else ("OUT OF FUEL!", ORANGE)
        lbl = self._win_font.render(txt, True, color)
        surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, cy))
        cy += lbl.get_height() + 10
        mins = int(self.elapsed_time) // 60
        secs = int(self.elapsed_time) % 60
        cs = int((self.elapsed_time % 1) * 100)
        t_lbl = self._sub_font.render(
            f"Time: {mins:02d}:{secs:02d}.{cs:02d}", True, WHITE
        )
        surface.blit(t_lbl, ((SCREEN_W - t_lbl.get_width()) // 2, cy))
        cy += t_lbl.get_height() + 28
        r_lbl = self._sub_font.render("[R]  Restart", True, CYAN)
        m_lbl = self._sub_font.render("[M]  Main Menu", True, YELLOW)
        surface.blit(r_lbl, ((SCREEN_W - r_lbl.get_width()) // 2, cy))
        surface.blit(
            m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, cy + r_lbl.get_height() + 12)
        )

    def draw_pause_overlay(self, surface: pygame.Surface) -> None:
        """Enhanced pause overlay with lobby/quit buttons (Phase 11)."""
        surface.blit(self._overlay_surf, (0, 0))

        cx = SCREEN_W // 2
        bw, bh, gap = 300, 52, 14
        labels = [
            ("resume", "[P/ESC]  Resume", (40, 90, 40)),
            ("settings", "[S]      Settings", (40, 60, 120)),
            ("lobby", "[L]      Back to Lobby", (40, 60, 120)),
            ("quit", "[Q]      Quit Game", (90, 30, 30)),
        ]
        total_h = len(labels) * (bh + gap) - gap
        y0 = SCREEN_H // 2 - total_h // 2 + 30

        # Title
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
        if self.mode == MODE_PANIC:
            csx, csy = self.camera.w2s(self.cars[0].state.x, self.cars[0].state.y)
            self.draw_ping_glow_through_fog(self.screen)
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
