# =============================================================================
#  host.py  –  Panic Pilot | Host (Phase 5.3)
# =============================================================================
#
#  Phase 5.3 changes:
#    - speed_scale parameter: game tempo identical for both players
#    - paused in packet: client also freezes when paused
#    - collected_by in packet: pickup sync via FuelCanister.to_net_dict()
#    - S key on end-screen: _return_to_settings signal to main.py
# =============================================================================
from __future__ import annotations
import socket
import logging
import pygame

from settings    import *
from game        import Game, PING_DURATION, MAX_PINGS, SPEED_SCALE_NORMAL
from input_state import InputState
from track       import Track
from net         import HostConnection

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

NET_PORT = 54321


def get_own_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


class HostGame(Game):
    """
    Extends Game with network logic.
    Mode 3: receives client input as car-B input, simulates both cars.
    """

    def __init__(self, mode: int = 1, track_length: int = 20,
                 speed_scale: float = SPEED_SCALE_NORMAL,
                 net: "HostConnection | None" = None,
                 car_class_host: str = "balanced",
                 car_class_client: str = "balanced",
                 screen: "pygame.Surface | None" = None,
                 host_room_name: str = "Host",
                 client_room_name: str = "Client") -> None:
        self._host_mode         = mode
        self._host_track_length = track_length
        self._host_speed_scale  = speed_scale
        self._generated_track   = Track.generate(length=track_length)
        self._host_room_name    = host_room_name
        self._client_room_name  = client_room_name

        # Network: either external (lobby) or create new
        if net is not None:
            self._net      = net
            self._owns_net = False
        else:
            self._net      = HostConnection(NET_PORT)
            self._net.start()
            self._owns_net = True

        # Classes locked by lobby selection
        super().__init__(screen=screen, locked_class0=car_class_host,
                         locked_class1=car_class_client)
        self.mode        = mode
        self.speed_scale = speed_scale

        # Ensure fog surface is fully black from the start for mode 2
        if self.mode == MODE_PANIC:
            self._fog_surf.fill((0, 0, 0, FOG_ALPHA))

        self._last_client_inp    = InputState()
        self._pending_map_send   = False
        self._return_to_settings = False
        self._mode_switch_pending: int | None = None  # requested new mode, awaiting confirm
        self._mode_change_countdown = 0.0
        self._track_length_switch_pending: int | None = None
        self._track_length_change_countdown = 0.0

        self._status_font = pygame.font.SysFont("Arial", 15, bold=True)
        self._mode_font   = pygame.font.SysFont("Arial", 22, bold=True)
        self._update_caption()

    def _init_game_objects(self, track=None) -> None:
        use = track or getattr(self, "_generated_track", None)
        super()._init_game_objects(track=use)
        pvp = (getattr(self, "_host_mode", 1) == 3)
        for c in self.canisters:   c.set_pvp_mode(pvp)
        for b in self.boosts:      b.set_pvp_mode(pvp)
        for o in self.oils:        o.set_pvp_mode(pvp)
        for ib in self.item_boxes: ib.set_pvp_mode(pvp)

    def reset(self, track=None) -> None:
        length = getattr(self, "_host_track_length", 20)
        self._generated_track  = Track.generate(length=length)
        self._pending_map_send = True
        super().reset(track=self._generated_track)
        if hasattr(self, "_net") and self._net.is_connected():
            self._net.send_map(self.track.to_dict())
            self._pending_map_send = False

    def _update_caption(self) -> None:
        own_ip   = get_own_ip()
        modes    = {1: "SPLIT CTRL", 2: "PANIC PILOT", 3: "PvP RACING"}
        mode_str = modes.get(self.mode, "?")
        pygame.display.set_caption(
            f"Panic Pilot – HOST [{mode_str}] | A/D M R P | IP: {own_ip}:{NET_PORT}"
        )

    def _on_keydown(self, event) -> None:
        if event.key == pygame.K_m:
            if self.game_over or self.winner:
                self.running         = False
                self._return_to_menu = True
            else:
                self.mode = (self.mode % 3) + 1
                self.reset_for_mode(self.mode)
                self._pending_map_send = True
                self._update_caption()
        elif event.key == pygame.K_n:
            # Request mode switch (post-race OR mid-game)
            new_mode = (self.mode % 3) + 1
            if self._net.is_connected():
                self._mode_switch_pending = new_mode
                self._net.send_mode_change_request(new_mode)
            else:
                # No navigator connected: switch immediately
                self.mode = new_mode
                self._update_caption()
        elif event.key == pygame.K_s and (self.game_over or self.winner):
            self.running               = False
            self._return_to_settings   = True

    def _open_pause_settings(self) -> None:
        """Shows in-game settings panel while game is paused."""
        import settings as _s
        if _main_mod is None:
            return

        # Capture current screen as background
        background = self.screen.copy()

        username = getattr(_s, "USERNAME", "").strip() or "Host"
        settings_scene = _main_mod.InGameSettingsScene(
            self.screen,
            background,
            current_mode=self.mode,
            current_track_length=self._host_track_length,
            net=self._net,
            is_host=True,
            username=username,
        )
        changes = settings_scene.run()

        # Apply changes
        if changes:
            if "mode" in changes:
                self._mode_switch_pending = changes["mode"]
                self._mode_change_countdown = 3.0
            if "track_length" in changes:
                self._track_length_switch_pending = changes["track_length"]
                self._track_length_change_countdown = 3.0

        # Game stays paused when returning

    # ─── Update ───────────────────────────────────────────────────────────────

    def update(self, dt: float, input_override=None, input_car1=None) -> None:
        # Phase 11: Client wants to return to lobby?
        if self._net.client_wants_lobby():
            self._return_to_lobby  = True
            self._lobby_initiator  = "remote"
            self.running           = False
            return

        # Mid-game disconnect: after countdown, return to lobby when client drops
        if not self._net.is_connected() and self._countdown <= 0 and not self.game_over and not self.winner:
            if not getattr(self, "_disconnect_timer", None):
                self._disconnect_timer = 3.0
            self._disconnect_timer -= dt
            if self._disconnect_timer <= 0:
                self._return_to_lobby = True
                self._lobby_initiator = "remote"
                self.running = False
                return
        else:
            self._disconnect_timer = None

        # Phase 11.1: ignore request_lobby_state during game
        # (handled in HostLobby; just clear here so flag doesn't stick)
        self._net.client_requests_state()

        # Mode switch: check for navigator confirm/deny
        if self._mode_switch_pending is not None:
            if self._net.client_confirmed_mode_change():
                new_mode = self._mode_switch_pending
                self._mode_switch_pending = None
                self._mode_change_countdown = 3.0
            elif self._net.client_denied_mode_change():
                self._mode_switch_pending = None

        # Mode change countdown - execute switch when timer expires
        if self._mode_change_countdown > 0:
            self._mode_change_countdown -= dt
            if self._mode_change_countdown <= 0:
                self.mode = self._mode_switch_pending if self._mode_switch_pending else self.mode
                self._mode_switch_pending = None
                self.reset()
                self._pending_map_send = True
                self._countdown = 3.0
                self._go_timer = 0.0
                self._race_started = False
                self.game_over = False
                self.winner = None
                self._update_caption()

        # Track length switch: check for navigator confirm/deny
        if self._track_length_switch_pending is not None:
            if self._net.client_confirmed_track_length_change():
                new_length = self._track_length_switch_pending
                self._track_length_switch_pending = None
                self._track_length_change_countdown = 3.0
            elif self._net.client_denied_track_length_change():
                self._track_length_switch_pending = None

        # Track length change countdown - execute switch when timer expires
        if self._track_length_change_countdown > 0:
            self._track_length_change_countdown -= dt
            if self._track_length_change_countdown <= 0:
                if self._track_length_switch_pending:
                    self._host_track_length = self._track_length_switch_pending
                self._track_length_switch_pending = None
                self.reset()
                self._pending_map_send = True
                self._countdown = 3.0
                self._go_timer = 0.0
                self._race_started = False
                self.game_over = False
                self.winner = None

        # Map handshake: one-time after new client or reset
        if self._net.got_new_client() or self._pending_map_send:
            if self._net.is_connected():
                map_data = {**self.track.to_dict(), "game_mode": self.mode}
                self._net.send_map(map_data)
            self._pending_map_send = False

        # Freeze countdown until client connects
        if not self._net.is_connected() and self._countdown > 0:
            self.cars[0].state.speed = 0.0
            if self.mode == MODE_PVP:
                self.cars[1].state.speed = 0.0
            self._net.send_state(self._build_packet())
            return

        # Fetch client input
        raw = self._net.get_client_input()
        if raw is not None:
            client_inp = InputState.from_dict(raw)
            if client_inp.ping_pos is not None:
                if len(self.pings) >= MAX_PINGS:
                    self.pings.pop(0)
                self.pings.append([
                    client_inp.ping_pos[0],
                    client_inp.ping_pos[1],
                    PING_DURATION,
                ])
            self._last_client_inp = InputState(
                throttle    = client_inp.throttle,
                brake       = client_inp.brake,
                steer_left  = client_inp.steer_left,
                steer_right = client_inp.steer_right,
                ping_pos    = None,
                use_item    = client_inp.use_item,
            )

        # Input per mode
        keys = pygame.key.get_pressed()
        if self.mode == MODE_SPLIT:
            merged_inp = InputState.merge(InputState.host_keys(keys),
                                          self._last_client_inp)
            car1_inp   = None
        elif self.mode == MODE_PANIC:
            merged_inp = InputState.from_keys(keys)
            car1_inp   = None
        else:
            merged_inp = InputState.from_keys(keys)
            car1_inp   = self._last_client_inp

        super().update(dt, input_override=merged_inp, input_car1=car1_inp)
        self._net.send_state(self._build_packet())

    # ─── Packet ───────────────────────────────────────────────────────────────

    def _build_packet(self) -> dict:
        s0  = self.cars[0].state
        pkt = {
            "x":          s0.x,
            "y":          s0.y,
            "angle":      s0.angle,
            "speed":      s0.speed,
            "fuel":       s0.fuel,
            "elapsed":    self.elapsed_time,
            "game_over":  self.game_over,
            "winner":     self.winner,
            "fuel_flash": self._fuel_flash,
            "mode":       self.mode,
            "countdown":  self._countdown,
            "go_timer":   self._go_timer,
            # ── Phase 5.3: paused + collected_by sync ───────────────────────
            "paused":     self._paused,
            "canisters":  [c.to_net_dict()  for c in self.canisters],
            "boosts":     [b.to_net_dict()  for b in self.boosts],
            "oils":       [o.to_net_dict()  for o in self.oils],
            "item_boxes": [ib.to_net_dict() for ib in self.item_boxes],
            "boomerangs": [b.to_net_dict()  for b  in self.boomerangs],
            "car0_class": self.cars[0].car_class,
            "car1_class": self.cars[1].car_class,
            # Inventory sync: client shows own item correctly
            "car0_inv":   self.cars[0].inventory or "",
            "car1_inv":   (self.cars[1].inventory or "") if self.mode == MODE_PVP else "",
        }
        # Car B (Mode 3)
        if self.mode == MODE_PVP:
            s1 = self.cars[1].state
            pkt["car1"] = {
                "x": s1.x, "y": s1.y,
                "angle": s1.angle,
                "speed": s1.speed,
                "fuel":  s1.fuel,
            }
        return pkt

    # ─── Draw ────────────────────────────────────────────────────────────────

    def draw(self) -> None:
        self.screen = pygame.display.get_surface() or self.screen
        s = self.cars[0].state
        self.draw_world(self.screen)
        if self.mode == MODE_PANIC:
            csx, csy = self.camera.w2s(s.x, s.y)
            self.draw_ping_glow_through_fog(self.screen)
            self.draw_fog(self.screen, (csx, csy))
        self.draw_pings(self.screen)
        self.draw_hud(self.screen)
        self.draw_countdown(self.screen)
        if self.game_over or self.winner:
            self.draw_winner(self.screen)
        # Pause overlay (host draws it too – client receives _paused via packet)
        if self._paused:
            self.draw_pause_overlay(self.screen)
        # Disconnect countdown overlay
        if getattr(self, "_disconnect_timer", None) is not None:
            self._draw_disconnect_overlay()
        self._draw_status_overlay()
        pygame.display.flip()

    def _draw_disconnect_overlay(self) -> None:
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        f = pygame.font.SysFont("Arial", 36, bold=True)
        lbl = f.render("Connection lost – returning to lobby …", True, ORANGE)
        self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2,
                                (SCREEN_H - lbl.get_height()) // 2))

    def _draw_status_overlay(self) -> None:
        # Connection status top-right
        txt, color = (("NAVIGATOR CONNECTED", GREEN) if self._net.is_connected()
                      else ("Waiting for navigator …", ORANGE))
        lbl = self._status_font.render(txt, True, color)
        self.screen.blit(lbl, (SCREEN_W - lbl.get_width() - 12, 12))

        # Mode top center
        modes  = {1: "SPLIT CONTROL", 2: "PANIC PILOT", 3: "PvP RACING"}
        colors = {1: GRAY, 2: CYAN, 3: YELLOW}
        m_lbl = self._mode_font.render(
            modes.get(self.mode, ""), True, colors.get(self.mode, WHITE))
        self.screen.blit(m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, 10))

        # Key hints bottom left – different per state
        if self.game_over or self.winner:
            hint_txt = "[R]=Restart  [N]=Switch Mode  [M]=Menu  [S]=Settings"
            hint_color = CYAN
        else:
            hint_txt  = "A/D=Steer  N=Switch Mode  P=Pause  R=Reset"
            hint_color = GRAY
        hint = self._status_font.render(hint_txt, True, hint_color)
        self.screen.blit(hint, (12, SCREEN_H - 38))

        # Pending mode change notification
        if self._mode_switch_pending is not None:
            modes = {1: "Split Control", 2: "Panic Pilot", 3: "PvP Racing"}
            pending_txt = f"Requesting switch to {modes.get(self._mode_switch_pending, '?')} … (waiting for navigator)"
            plbl = self._status_font.render(pending_txt, True, ORANGE)
            self.screen.blit(plbl, (12, SCREEN_H - 58))

        # Mode change countdown
        if self._mode_change_countdown > 0:
            modes = {1: "Split Control", 2: "Panic Pilot", 3: "PvP Racing"}
            secs = int(self._mode_change_countdown) + 1
            cd_txt = f"Switching to {modes.get(self.mode, '?')} in {secs}…"
            cdlbl = pygame.font.SysFont("Arial", 28, bold=True).render(cd_txt, True, CYAN)
            self.screen.blit(cdlbl, ((SCREEN_W - cdlbl.get_width()) // 2, SCREEN_H // 2 - 100))

    def run(self) -> None:
        try:
            super().run()
        finally:
            # Phase 11: Only send if host itself initiated the lobby
            if (getattr(self, "_return_to_lobby", False)
                    and getattr(self, "_lobby_initiator", "") != "remote"):
                self._net.send_back_to_lobby()
            # Phase 11.2: Zero out flags so next start is clean
            if self._net.is_connected():
                self._net.reset_lobby_flags()
            if self._owns_net:
                self._net.shutdown()


if __name__ == "__main__":
    HostGame().run()
