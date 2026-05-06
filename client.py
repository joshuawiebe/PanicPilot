# =============================================================================
#  client.py  –  Panic Pilot | Client / Navigator (Phase 5.3)
# =============================================================================
#
#  Phase 5.3 changes:
#    - Pause sync:     _paused from packet → overlay + physics stop
#    - Adaptive camera Mode 3: identical zoom-out as host (_update_camera_pvp)
#    - Pickup sync:    apply_net_dict() instead of direct field writing
#    - Props:          PropManager created after map construction
#    - Theme bg_fill:  background color from theme
#    - Start pos:      side_offset (side-by-side, matching game.py)
# =============================================================================
from __future__ import annotations
import math, sys, time, logging
from typing import Optional
import pygame

from settings    import *
from camera      import Camera
from car         import Car, CAR_COLOR_HOST, CAR_COLOR_CLIENT
from input_state import InputState
from track       import Track
from walls       import WallSystem
from hud         import HUD
from entities    import (FuelCanister, BoostPad, OilSlick, ItemBox,
                           GreenBoomerang, RedBoomerang,
                           EntityParticleSystem, PLAYER_HOST, PLAYER_CLIENT)
from particles   import ParticleSystem
from props       import PropManager
from net         import ClientConnection

try:
    import main as _main_mod
except Exception:
    _main_mod = None

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

CLIENT_HOST_IP         = "127.0.0.1"
NET_PORT               = 54321
CONNECT_RETRY_INTERVAL = 2.0
CONNECT_TIMEOUT        = 5.0
LOCAL_PING_DURATION    = 5.0
PING_COOLDOWN          = 0.25   # Minimum seconds between pings
MAX_LOCAL_PINGS        = 15     # Cap on active local pings


class ClientGame:
    def __init__(self, host_ip: str,
                 screen: "pygame.Surface | None" = None,
                 net: "ClientConnection | None" = None,
                 car_class_host: str = "balanced",
                 car_class_client: str = "balanced",
                 host_room_name: str = "Host",
                 client_room_name: str = "Client") -> None:
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
        self.clock   = pygame.time.Clock()
        self.running = True

        # Classes at startup from lobby
        self._car_class_host   = car_class_host
        self._car_class_client = car_class_client
        self._host_room_name   = host_room_name
        self._client_room_name = client_room_name

        self.track:     Optional[Track]       = None
        self.car:       Optional[Car]         = None   # Auto A (Host)
        self.car_b:     Optional[Car]         = None   # Auto B (Client, Modus 3)
        self.props:     Optional[PropManager] = None   # Decorative props
        self.hud:       Optional[HUD]         = None
        self.walls     = WallSystem(screen_edge=False)
        self.particles = ParticleSystem()
        self.canisters: list[FuelCanister] = []
        self.boosts:    list[BoostPad]     = []
        self.oils:      list[OilSlick]     = []
        self.item_boxes: list[ItemBox]     = []
        self.boomerangs: list              = []   # GreenBoomerang | RedBoomerang
        self.entity_particles = EntityParticleSystem()
        self._client_inventory: str | None = None   # Inventory from host packet
        self.camera    = Camera()

        self._flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self._fog_surf   = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

        self._elapsed    = 0.0
        self._game_over  = False
        self._winner: Optional[str] = None
        self._fuel_flash = 0.0
        self._mode       = 1
        self._countdown  = 3.0
        self._go_timer   = 0.0
        self._paused     = False

        self._pending_ping:       Optional[tuple] = None
        self._pending_use_item:   bool            = False
        self._pending_cycle_class: bool           = False   # C one-shot
        self._local_pings:        list[list]      = []
        self._last_ping_time:     float           = 0.0
        self._return_to_menu  = False
        self._return_to_lobby  = False   # Phase 11
        self._lobby_initiator  = ""      # "self" | "remote"
        self._pause_btn_rects: dict = {}
        self._lobby_ready_sent = False   # Phase 11.3: ready_for_map already sent?
        
        self._pending_mode_request: int | None = None
        self._mode_request_timer:   float      = 0.0
        self._mode_switch_accepted: bool       = False

        # Phase 12.2: Latency tracking for ping visualization
        self._frame_times: list[float] = []
        self._estimated_latency_ms: int = 0
        self._last_latency_update = 0.0

        # Fonts
        self._status_font    = pygame.font.SysFont("Arial", 15, bold=True)
        self._big_font       = pygame.font.SysFont("Arial", 72, bold=True)
        self._mid_font       = pygame.font.SysFont("Arial", 22, bold=True)
        self._mode_font      = pygame.font.SysFont("Arial", 22, bold=True)
        self._warn_font      = pygame.font.SysFont("Arial", 18, bold=True)
        self._countdown_font = pygame.font.SysFont("Arial", 160, bold=True)
        self._pause_font     = pygame.font.SysFont("Arial", 80, bold=True)
        self._sub_font       = pygame.font.SysFont("Arial", 28, bold=True)

        if net is not None:
            self._net      = net
            self._owns_net = False
        else:
            self._net      = ClientConnection(host_ip, NET_PORT)
            self._owns_net = True
        self._host_ip = host_ip
        self._update_caption()

    def _update_caption(self) -> None:
        modes = {1: "HELPER", 2: "NAVIGATOR", 3: "PvP AUTO B"}
        pygame.display.set_caption(
            f"Panic Pilot – CLIENT [{modes.get(self._mode,'?')}] | Host: {self._host_ip}")

    # ── Build map ───────────────────────────────────────────────────────

    def _build_from_map(self, map_data: dict) -> None:
        self.track = Track.from_dict(map_data)

        # Bug fix Phase 9: game_mode in map packet → set pvp_mode correctly
        game_mode = int(map_data.get("game_mode", self._mode))
        pvp = (game_mode == 3)

        sx = self.track.start_x
        sy = self.track.start_y
        sa = self.track.start_angle
        rad = math.radians(sa)

        side_x      = math.cos(rad)
        side_y      = math.sin(rad)
        side_offset = 36

        # Classes from lobby selection
        cls0 = self._car_class_host
        cls1 = self._car_class_client
        cs0  = CAR_CLASSES.get(cls0, CAR_CLASSES["balanced"])
        cs1  = CAR_CLASSES.get(cls1, CAR_CLASSES["balanced"])

        self.car   = Car(sx - side_x * side_offset, sy - side_y * side_offset,
                         sa, initial_fuel=FUEL_MAX,
                         body_color=cs0["color_host"],   car_class=cls0)
        self.car_b = Car(sx + side_x * side_offset, sy + side_y * side_offset,
                         sa, initial_fuel=FUEL_MAX,
                         body_color=cs1["color_client"], car_class=cls1)

        def _make_entity(cls_fn, lst, pvp_flag):
            for obj in lst:
                obj.set_pvp_mode(pvp_flag)
            return lst

        self.canisters = _make_entity(None, [
            FuelCanister(x, y, canister_id=i)
            for i, (x, y) in enumerate(self.track.canister_positions())
        ], pvp)
        self.boosts = _make_entity(None, [
            BoostPad(x, y, angle, pad_id=i)
            for i, (x, y, angle) in enumerate(self.track.boost_positions())
        ], pvp)
        self.oils = _make_entity(None, [
            OilSlick(x, y, slick_id=i)
            for i, (x, y) in enumerate(self.track.oil_positions())
        ], pvp)
        self.item_boxes = _make_entity(None, [
            ItemBox(x, y, box_id=i)
            for i, (x, y) in enumerate(self.track.box_positions())
        ], pvp)
        self.entity_particles = EntityParticleSystem()
        self._client_inventory = None
        self.boomerangs = []
        self.hud = HUD()
        self.camera.snap(sx, sy)

        # Phase 5.3: Generate props (deterministic, same seed as host)
        prop_seed = hash(tuple(t.tile_type for t in self.track.tiles)) % 99999
        self.props = PropManager.generate(
            self.track, theme=self.track.theme, seed=prop_seed)

    # ── Connection loop ─────────────────────────────────────────────────

    def _connect_loop(self) -> bool:
        """
        Phase 11.3:
        If already connected (from lobby):
          - ready_for_map was already sent in the lobby loop
            (self._lobby_ready_sent=True) → do NOT send again.
          - Just wait for map data (max MAP_WAIT_TIMEOUT s).
          - On timeout → False.
        Otherwise (standalone): connect + send ready_for_map + wait.
        """
        MAP_WAIT_TIMEOUT = 5.0

        # === PHASE 1: Establish connection (if not already connected from lobby) ===
        if not self._net.is_connected():
            # Standalone mode: attempt to connect with retries
            attempt = 0
            while self.running:
                attempt += 1
                self._draw_waiting_screen(f"Connecting ... (Attempt {attempt})")
                if not self._net.connect(timeout=CONNECT_TIMEOUT):
                    self._drain_events(CONNECT_RETRY_INTERVAL)
                    continue
                print("DEBUG: Standalone connect successful, waiting for handshake")
                break
            
            if not self._net.is_connected():
                self._draw_waiting_screen("Timed out – returning to lobby …")
                pygame.time.wait(1800)
                return False

        # === PHASE 2: Wait for map data (connection established) ===
        if not self._lobby_ready_sent:
            # Standalone lobby or safety fallback
            print("DEBUG: Client sending ready_for_map in _connect_loop (fallback)")
            self._net.send_ready_for_map()
        else:
            print("DEBUG: Client waiting for map (ready_for_map already sent)")
        
        deadline = time.time() + MAP_WAIT_TIMEOUT
        while self.running and time.time() < deadline:
            self._draw_waiting_screen("Waiting for track data …")
            m = self._net.get_map()
            if m:
                print("DEBUG: Client received map – building track …")
                self._build_from_map(m)
                return True
            self._drain_events(0.08)
        
        print("DEBUG: Client map timeout after", MAP_WAIT_TIMEOUT, "s")
        self._draw_waiting_screen("Timed out – returning to lobby …")
        pygame.time.wait(1800)
        return False

    def _drain_events(self, seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline and self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
            pygame.time.wait(80)

            # ── Main loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        if not self._connect_loop():
            # Phase 11.2: Timeout or connection error → return to lobby
            self._return_to_lobby = True
            return

        send_timer = 0.0

        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            
            # Phase 12.2: Track frame times for latency estimation
            self._frame_times.append(dt * 1000)  # Convert to ms
            if len(self._frame_times) > 60:  # Keep last 60 frames
                self._frame_times.pop(0)
            
                # Update latency every 0.5 seconds (estimate from frame variance)
            self._last_latency_update += dt
            if self._last_latency_update >= 0.5:
                if len(self._frame_times) > 10:
                    avg_frame_ms = sum(self._frame_times) / len(self._frame_times)
                    variance = sum((f - avg_frame_ms) ** 2 for f in self._frame_times) / len(self._frame_times)
                    # Estimate latency from frame time jitter (rough approximation)
                    # Higher jitter suggests network latency
                    self._estimated_latency_ms = int(min(500, max(20, variance / 2)))
                self._last_latency_update = 0.0

            # ── Events ────────────────────────────────────────────────────────
            for event in pygame.event.get():
                if _main_mod and _main_mod._handle_global_key(event):
                    continue
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._paused:
                        self._handle_pause_click(event.pos)
                    elif self._mode == 2:
                        now = time.time()
                        if now - self._last_ping_time >= PING_COOLDOWN:
                            if len(self._local_pings) < MAX_LOCAL_PINGS:
                                wx, wy = self.camera.s2w(float(event.pos[0]), float(event.pos[1]))
                                self._pending_ping = (wx, wy)
                                self._local_pings.append([wx, wy, LOCAL_PING_DURATION])
                                self._last_ping_time = now
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_p):
                        if self._game_over or self._winner:
                            if event.key == pygame.K_ESCAPE:
                                self.running = False
                                self._return_to_lobby = True
                        else:
                            self._paused = not self._paused
                    elif event.key == pygame.K_m and (self._game_over or self._winner):
                        self.running         = False
                        self._return_to_menu = True
                    elif event.key == pygame.K_y and self._pending_mode_request is not None:
                        self._net.send_mode_change_confirm()
                        if not self._game_over and not self._winner:
                            self._mode_switch_accepted = True
                        self._pending_mode_request = None
                    elif event.key == pygame.K_n and self._pending_mode_request is not None:
                        self._net.send_mode_change_deny()
                        self._pending_mode_request = None
                    elif self._paused and event.key == pygame.K_s:
                        self._open_pause_settings()
                    elif self._paused and event.key == pygame.K_l:
                        self._do_return_to_lobby()
                    elif self._paused and event.key == pygame.K_q:
                        self.running = False
                    elif event.key == pygame.K_o and self._mode == 2:
                        self.camera.handle_zoom(-1)
                    elif event.key == pygame.K_p and self._mode == 2:
                        self.camera.handle_zoom(+1)
                    elif event.key == pygame.K_SPACE:
                        self._pending_use_item = True
                elif event.type == pygame.MOUSEWHEEL and self._mode == 2:
                    self.camera.handle_zoom(event.y)

            if not self._net.is_connected():
                self._draw_disconnected_screen()
                pygame.display.flip()
                pygame.time.wait(60)
                continue

            # Phase 11: Host wants to return to lobby?
            if self._net.host_wants_lobby():
                self._do_return_to_lobby()
                break

            # Mode change request from host (post-race OR mid-game)
            requested_mode = self._net.get_mode_change_request()
            if requested_mode is not None:
                self._pending_mode_request = requested_mode
                self._mode_request_timer   = 10.0  # 10 second timeout to respond

            # Map-Update (nach Reset)
            m = self._net.get_map()
            if m:
                self._build_from_map(m)

            # Send input (even when paused – server decides)
            send_timer += dt
            if send_timer >= 1.0 / FPS:
                send_timer = 0.0
                keys = pygame.key.get_pressed()
                if self._mode == 3:
                    inp = InputState.from_keys(keys)
                elif self._mode == 1:
                    inp = InputState.client_keys(keys,
                                                 use_item=self._pending_use_item)
                else:
                    inp = InputState.client_keys(keys,
                                                 ping_pos=self._pending_ping,
                                                 use_item=self._pending_use_item)
                    self._pending_ping = None
                self._pending_use_item    = False
                self._net.send_input(inp.to_dict())

            # Receive state
            packet = self._net.get_state()
            if packet:
                self._apply_state(packet)

            # ── Phase 5.3: Pause guard ───────────────────────────────────────
            # When paused: freeze camera + particles, only draw
            if not self._paused:
                # Camera
                if self.car:
                    if self._mode == 3 and self.car_b:
                        # Phase 5.3: Adaptive camera identical to host
                        self._update_camera_pvp(dt)
                    elif self._mode == 2:
                        # Navigator: free zoom, follows car A
                        self.camera.update(self.car.state.x, self.car.state.y, dt)
                    else:
                        self.camera.zoom = 1.0
                        self.camera.update(self.car.state.x, self.car.state.y, dt)

                # Particles (car A – host)
                if self.car:
                    s   = self.car.state
                    rad = math.radians(s.angle)
                    self.particles.emit_exhaust(
                        s.x - math.sin(rad) * 18,
                        s.y + math.cos(rad) * 18,
                        s.angle, s.speed)
                self.particles.update(dt)
                self.entity_particles.update(dt)
                if self._fuel_flash > 0:
                    self._fuel_flash -= dt

                self._local_pings = [p for p in self._local_pings if p[2] > 0]
                for p in self._local_pings:
                    p[2] -= dt

                # Mode change request timeout
                if self._pending_mode_request is not None:
                    self._mode_request_timer -= dt
                    if self._mode_request_timer <= 0:
                        # Auto-deny on timeout
                        self._net.send_mode_change_deny()
                        self._pending_mode_request = None

                # Handle mid-game mode switch - reset state when host switches
                if self._mode_switch_accepted:
                    if packet.get("game_over") and not self._game_over:
                        # Host triggered reset for mode change
                        self._game_over = True
                        self._winner = "mode_change"
                        self._mode_switch_accepted = False

            self._draw()

        # Phase 11: Client initiated lobby → inform host
        if self._return_to_lobby and getattr(self, "_lobby_initiator", "") != "remote":
            try: self._net.send_back_to_lobby()
            except Exception: pass
        # Phase 11.2: Zero out flags so next start round is clean
        if self._net.is_connected():
            self._net.reset_lobby_flags()
        if self._owns_net:
            self._net.shutdown()

    # ── Adaptive camera PvP (Phase 5.3) ───────────────────────────────────

    def _update_camera_pvp(self, dt: float) -> None:
        """
        Identical zoom logic as Host._update_camera_pvp in game.py.
        Follows car B (own car), zooms out when distance to car A is large.
        """
        if self.car is None or self.car_b is None:
            return
        s_a = self.car.state    # Auto A (Host)
        s_b = self.car_b.state  # Auto B (Client = eigenes Auto)
        dist        = math.hypot(s_a.x - s_b.x, s_a.y - s_b.y)
        target_zoom = max(0.35, min(1.0, 600.0 / max(dist, 600.0)))
        self.camera.zoom += (target_zoom - self.camera.zoom) * 0.05
        # Camera follows own car (B)
        self.camera.update(s_b.x, s_b.y, dt)

    # ── Apply state ──────────────────────────────────────────────────────

    def _apply_state(self, packet: dict) -> None:
        if self.car is None:
            return
        s = self.car.state
        s.x     = float(packet.get("x",     s.x))
        s.y     = float(packet.get("y",     s.y))
        s.angle = float(packet.get("angle", s.angle))
        s.speed = float(packet.get("speed", s.speed))
        s.fuel  = float(packet.get("fuel",  s.fuel))

        self._elapsed   = float(packet.get("elapsed",   self._elapsed))
        self._game_over = bool(packet.get("game_over",  self._game_over))
        self._winner    = packet.get("winner",   self._winner)
        self._countdown = float(packet.get("countdown", self._countdown))
        self._go_timer  = float(packet.get("go_timer",  self._go_timer))

                    # ── Phase 5.3: Pause sync ───────────────────────────────────────
        self._paused = bool(packet.get("paused", False))

        hf = float(packet.get("fuel_flash", 0.0))
        if hf > self._fuel_flash:
            self._fuel_flash = hf

        new_mode = int(packet.get("mode", self._mode))
        if new_mode != self._mode:
            self._mode = new_mode
                # Bug fix: update pvp_mode on all entities
            pvp = (new_mode == 3)
            for obj in (*self.canisters, *self.boosts, *self.oils, *self.item_boxes):
                obj.set_pvp_mode(pvp)
                obj.collected_by.clear()
            self._update_caption()
            # Mid-game mode change: rebuild track if map data changed
            if self._mode_switch_accepted:
                self._mode_switch_accepted = False
                self._game_over = False
                self._winner = None
                self._countdown = 3.0
                self._go_timer = 0.0

        # Car B (Mode 3)
        if "car1" in packet and self.car_b:
            c1 = packet["car1"]
            self.car_b.state.x     = float(c1.get("x",     self.car_b.state.x))
            self.car_b.state.y     = float(c1.get("y",     self.car_b.state.y))
            self.car_b.state.angle = float(c1.get("angle", self.car_b.state.angle))
            self.car_b.state.speed = float(c1.get("speed", self.car_b.state.speed))
            self.car_b.state.fuel  = float(c1.get("fuel",  self.car_b.state.fuel))

        # Pickup sync: collected_by for all three entity types
        for i, cd in enumerate(packet.get("canisters", [])):
            if i < len(self.canisters):
                self.canisters[i].apply_net_dict(cd)
        for i, bd in enumerate(packet.get("boosts", [])):
            if i < len(self.boosts):
                self.boosts[i].apply_net_dict(bd)
        for i, od in enumerate(packet.get("oils", [])):
            if i < len(self.oils):
                self.oils[i].apply_net_dict(od)
            else:
                # Dynamically placed oil slick from host – create new
                new_oil = OilSlick(0.0, 0.0, slick_id=i)
                new_oil.apply_net_dict(od)
                self.oils.append(new_oil)
        for i, xd in enumerate(packet.get("item_boxes", [])):
            if i < len(self.item_boxes):
                self.item_boxes[i].apply_net_dict(xd)

        # Boomerang sync – host-authoritative
        net_brangs = packet.get("boomerangs", [])
        # Create missing entries
        while len(self.boomerangs) < len(net_brangs):
            d   = net_brangs[len(self.boomerangs)]
            cls = GreenBoomerang if d.get("kind") == "green" else RedBoomerang
            b   = cls(float(d["x"]), float(d["y"]),
                      float(d["angle"]), int(d["owner"]),
                      brang_id=int(d["id"]))
            self.boomerangs.append(b)
        for i, d in enumerate(net_brangs):
            if i < len(self.boomerangs):
                self.boomerangs[i].apply_net_dict(d)
        # Remove inactive
        self.boomerangs = [b for b in self.boomerangs if b.active]
        # Inventory sync: host is authoritative
        inv_key = "car1_inv" if self._mode == 3 else "car0_inv"
        raw_inv = packet.get(inv_key, "")
        self._client_inventory = raw_inv if raw_inv else None

        # Vehicle class sync (Phase 9)
        c0_cls = packet.get("car0_class", "balanced")
        c1_cls = packet.get("car1_class", "balanced")
        if self.car and c0_cls != self.car.car_class:
            cs = CAR_CLASSES.get(c0_cls, CAR_CLASSES["balanced"])
            self.car._body_color = cs["color_host"]
            self.car.set_class(c0_cls)
        if self.car_b and c1_cls != self.car_b.car_class:
            cs = CAR_CLASSES.get(c1_cls, CAR_CLASSES["balanced"])
            self.car_b._body_color = cs["color_client"]
            self.car_b.set_class(c1_cls)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        if self.car is None or self.track is None:
            self._draw_waiting_screen("Waiting for map data …")
            return

        zoom         = self.camera.zoom
        off_x, off_y = self.camera.offset()

        # Theme background color
        bg_color = getattr(getattr(self.track, "theme", None), "bg_fill", GRASS_DARK)
        self.screen.fill(bg_color)

        self.track.draw(self.screen, off_x, off_y, zoom)
        self.walls.draw(self.screen, off_x, off_y, zoom)

        # Props (decorative, Phase 5.3)
        if self.props:
            self.props.draw(self.screen, off_x, off_y, zoom)

        self.particles.draw(self.screen, off_x, off_y, zoom)
        self.entity_particles.draw(self.screen, off_x, off_y, zoom)
        for o in self.oils:
            o.draw(self.screen, off_x, off_y, zoom, player_id=PLAYER_CLIENT)
        for b in self.boosts:
            b.draw(self.screen, off_x, off_y, zoom, player_id=PLAYER_CLIENT)
        for ib in self.item_boxes:
            ib.draw(self.screen, off_x, off_y, zoom, player_id=PLAYER_CLIENT)
        for c in self.canisters:
            c.draw(self.screen, off_x, off_y, zoom, player_id=PLAYER_CLIENT)

        if self._fuel_flash > 0:
            alpha = int(120 * min(1.0, self._fuel_flash / 0.5))
            self._flash_surf.fill((255, 200, 0, alpha))
            self.screen.blit(self._flash_surf, (0, 0))

        self.car.draw(self.screen, off_x, off_y, zoom)
        if self._mode == 3 and self.car_b:
            self.car_b.draw(self.screen, off_x, off_y, zoom)
        for brang in self.boomerangs:
            brang.draw(self.screen, off_x, off_y, zoom)

        # Local pings (navigator)
        now_ms = pygame.time.get_ticks()
        for wx, wy, timer in self._local_pings:
            sx, sy = self.camera.w2s(wx, wy)
            frac   = max(0.0, timer / LOCAL_PING_DURATION)
            pulse  = 0.9 + 0.1 * math.sin(now_ms / 150.0)
            alpha  = int(220 * frac * pulse)
            r      = int(max(3, 10 + 8 * frac))
            tmp    = pygame.Surface((r*2+20, r*2+20), pygame.SRCALPHA)
            mid    = r + 10
            pygame.draw.circle(tmp, (255, 255, 80, alpha), (mid, mid), r, 2)
            pygame.draw.circle(tmp, (255, 255, 80, alpha), (mid, mid), 3)
            self.screen.blit(tmp, (sx - mid, sy - mid))

        # HUD
        if self.hud:
            fuel  = (self.car_b.state.fuel  if self._mode == 3 and self.car_b
                     else self.car.state.fuel)
            speed = (self.car_b.state.speed if self._mode == 3 and self.car_b
                     else self.car.state.speed)
            inv_car = self.car_b if self._mode == 3 and self.car_b else self.car
            self.hud.draw(self.screen, speed, fuel, self._elapsed,
                          inventory=self._client_inventory,
                          car_class=inv_car.car_class if inv_car else "balanced",
                          latency=self._estimated_latency_ms,
                          game_mode=self._mode,
                          game_over=self._game_over)

        # Off-track warning
        if not self._game_over and not self._paused:
            if self.track.surface_at(self.car.state.x, self.car.state.y) == "grass":
                lbl = self._warn_font.render("OFF TRACK", True, YELLOW)
                self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H - 40))

        self._draw_countdown_overlay()

        if self._game_over or self._winner:
            self._draw_winner_overlay()

        # Mode change request dialog (post-race or mid-game)
        if self._pending_mode_request is not None:
            self._draw_mode_change_dialog()

        # Mid-game mode switch countdown
        if self._mode_switch_accepted and not self._game_over:
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            self.screen.blit(overlay, (0, 0))
            modes = {1: "Split Control", 2: "Panic Pilot", 3: "PvP Racing"}
            mode_name = modes.get(self._mode, "?")
            cd_font = pygame.font.SysFont("Arial", 48, bold=True)
            cd_txt = cd_font.render(f"Switching to {mode_name}…", True, CYAN)
            self.screen.blit(cd_txt, ((SCREEN_W - cd_txt.get_width()) // 2, SCREEN_H // 2 - 30))

        # ── Phase 5.3: Pause overlay ──────────────────────────────────────
        if self._paused:
            self._draw_pause_overlay()

        self._draw_status_overlay()
        pygame.display.flip()

    # ── Phase 11: Pause helpers ───────────────────────────────────────────────

    def _do_return_to_lobby(self) -> None:
        self._return_to_lobby = True
        self._lobby_initiator = "self"
        self._paused          = False
        self.running          = False

    def _open_pause_settings(self) -> None:
        """Shows settings panel while game is paused."""
        import main as _main_mod
        settings_scene = _main_mod.SettingsScene(self.screen)
        settings_scene.run()
        # Game stays paused when returning

    def _handle_pause_click(self, pos: tuple) -> None:
        for key, rect in self._pause_btn_rects.items():
            if rect.collidepoint(pos):
                if key == "resume": self._paused = False
                elif key == "settings": self._open_pause_settings()
                elif key == "lobby": self._do_return_to_lobby()
                elif key == "quit":  self.running = False
                return

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _draw_mode_change_dialog(self) -> None:
        """Banner asking navigator to accept/deny a host mode change request."""
        if self._pending_mode_request is None:
            return
        modes = {1: "Split Control", 2: "Panic Pilot", 3: "PvP Racing"}
        mode_name = modes.get(self._pending_mode_request, "?")
        secs_left = max(0, int(self._mode_request_timer) + 1)

        panel_w, panel_h = 520, 100
        px = (SCREEN_W - panel_w) // 2
        py = SCREEN_H // 2 + 60
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((20, 20, 40, 220))
        pygame.draw.rect(panel, ORANGE, (0, 0, panel_w, panel_h), 2, border_radius=8)
        self.screen.blit(panel, (px, py))

        f_big = pygame.font.SysFont("Arial", 22, bold=True)
        f_sm  = pygame.font.SysFont("Arial", 16)
        if self._game_over or self._winner:
            sub_txt = f"[Y] Accept   [N] Decline   (auto-decline in {secs_left}s)"
        else:
            sub_txt = f"[Y] Accept (restarts race)   [N] Decline   ({secs_left}s)"
        title = f_big.render(f"Host wants to switch to {mode_name}", True, ORANGE)
        sub   = f_sm.render(sub_txt, True, WHITE)
        self.screen.blit(title, (px + (panel_w - title.get_width()) // 2, py + 16))
        self.screen.blit(sub,   (px + (panel_w - sub.get_width())   // 2, py + 54))

    def _draw_pause_overlay(self) -> None:
        """Enhanced pause overlay with lobby/quit buttons (Phase 11)."""
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        cx  = SCREEN_W // 2
        bw, bh, gap = 300, 52, 14
        labels = [
            ("resume", "[P/ESC]  Resume",        (40, 90, 40)),
            ("settings", "[S]      Settings",      (40, 60, 120)),
            ("lobby",  "[L]      Back to Lobby",  (40, 60, 120)),
            ("quit",   "[Q]      Quit Game",       (90, 30, 30)),
        ]
        total_h = len(labels) * (bh + gap) - gap
        y0 = SCREEN_H // 2 - total_h // 2 + 30

        lbl = self._pause_font.render("PAUSE", True, CYAN)
        shd = self._pause_font.render("PAUSE", True, BLACK)
        tx  = cx - lbl.get_width() // 2
        ty  = y0 - lbl.get_height() - 16
        self.screen.blit(shd, (tx + 3, ty + 3))
        self.screen.blit(lbl, (tx, ty))

        mouse = pygame.mouse.get_pos()
        self._pause_btn_rects = {}
        for key, text, col in labels:
            rect = pygame.Rect(cx - bw // 2, y0, bw, bh)
            self._pause_btn_rects[key] = rect
            hovered = rect.collidepoint(mouse)
            bg = tuple(min(255, c + 30) for c in col) if hovered else col
            pygame.draw.rect(self.screen, (0, 0, 0),
                             rect.move(3, 4), border_radius=8)
            pygame.draw.rect(self.screen, bg, rect, border_radius=8)
            pygame.draw.rect(self.screen, (150, 180, 220), rect, 1, border_radius=8)
            btn_lbl = self._sub_font.render(text, True,
                                            WHITE if hovered else (200, 210, 230))
            self.screen.blit(btn_lbl,
                             (rect.centerx - btn_lbl.get_width()  // 2,
                              rect.centery - btn_lbl.get_height() // 2))
            y0 += bh + gap

    def _draw_countdown_overlay(self) -> None:
        if self._countdown > 0:
            from game import COUNTDOWN_STEPS, COUNTDOWN_STEP_DURATION
            step_idx = min(int(self._countdown / COUNTDOWN_STEP_DURATION),
                           len(COUNTDOWN_STEPS) - 1)
            num   = COUNTDOWN_STEPS[-(step_idx + 1)]
            color = [RED, ORANGE, YELLOW][min(step_idx, 2)]
            lbl   = self._countdown_font.render(str(num), True, color)
            sx    = (SCREEN_W - lbl.get_width()) // 2
            sy    = (SCREEN_H - lbl.get_height()) // 2
            shd   = self._countdown_font.render(str(num), True, BLACK)
            self.screen.blit(shd, (sx + 4, sy + 4))
            self.screen.blit(lbl, (sx, sy))
        elif self._go_timer > 0:
            lbl = self._countdown_font.render("GO!", True, GREEN)
            self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2,
                                    (SCREEN_H - lbl.get_height()) // 2))

    def _draw_winner_overlay(self) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 175))
        self.screen.blit(overlay, (0, 0))
        cy = SCREEN_H // 2 - 80
        if self._mode == 3:
            if self._winner == "host":
                txt, color = f"{self._host_room_name.upper()} WINS!", (210, 45, 45)
            elif self._winner == "client":
                txt, color = f"{self._client_room_name.upper()} WINS!", (30, 100, 210)
            else:
                txt, color = "OUT OF FUEL!", ORANGE
        else:
            txt, color = (("FINISH!", YELLOW) if self._winner else ("OUT OF FUEL!", ORANGE))
        lbl = self._big_font.render(txt, True, color)
        self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, cy))
        cy += lbl.get_height() + 10
        mins  = int(self._elapsed) // 60
        secs  = int(self._elapsed) % 60
        cs    = int((self._elapsed % 1) * 100)
        t_lbl = self._mid_font.render(
            f"Time: {mins:02d}:{secs:02d}.{cs:02d}", True, WHITE)
        self.screen.blit(t_lbl, ((SCREEN_W - t_lbl.get_width()) // 2, cy))
        cy += t_lbl.get_height() + 24
        m_lbl = self._mid_font.render("[M]  Main Menu", True, YELLOW)
        self.screen.blit(m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, cy))

    def _draw_status_overlay(self) -> None:
        status = self._status_font.render("CONNECTED", True, GREEN)
        self.screen.blit(status, (SCREEN_W - status.get_width() - 12, 12))
        modes  = {1: "SPLIT CONTROL", 2: "NAVIGATOR", 3: "AUTO B (PvP)"}
        colors = {1: GRAY, 2: CYAN, 3: YELLOW}
        m = self._mode_font.render(
            modes.get(self._mode, ""), True, colors.get(self._mode, WHITE))
        self.screen.blit(m, ((SCREEN_W - m.get_width()) // 2, 10))
        hints = {1: "W/S = Throttle / Brake",
                 2: "W/S = Throttle | Click = Ping | O/P = Zoom",
                 3: "W/A/S/D = Own Car"}
        h = self._status_font.render(hints.get(self._mode, ""), True, CYAN)
        self.screen.blit(h, (12, SCREEN_H - 38))

    def _draw_waiting_screen(self, msg: str) -> None:
        self.screen.fill(HUD_BG)
        t = pygame.font.SysFont("Arial", 48, bold=True).render(
            "Panic Pilot", True, YELLOW)
        self.screen.blit(t, ((SCREEN_W - t.get_width()) // 2, 180))
        m = self._mid_font.render(msg, True, WHITE)
        self.screen.blit(m, ((SCREEN_W - m.get_width()) // 2, 290))
        h = self._status_font.render("ESC = Cancel", True, GRAY)
        self.screen.blit(h, ((SCREEN_W - h.get_width()) // 2, 340))
        pygame.display.flip()

    def _draw_disconnected_screen(self) -> None:
        self.screen.fill(HUD_BG)
        lbl = self._big_font.render("Connection lost", True, RED)
        self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H // 2 - 40))
        h = self._mid_font.render("ESC = Quit", True, GRAY)
        self.screen.blit(h, ((SCREEN_W - h.get_width()) // 2, SCREEN_H // 2 + 30))


if __name__ == "__main__":
    host_ip = sys.argv[1] if len(sys.argv) > 1 else CLIENT_HOST_IP
    ClientGame(host_ip).run()
