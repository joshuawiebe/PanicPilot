# =============================================================================
#  host.py  –  Panic Pilot | Host (Phase 5.3)
# =============================================================================
#
#  Phase 5.3 Änderungen:
#    - speed_scale Parameter: Spieltempo für beide Spieler identisch
#    - paused im Paket: Client friert bei Pause ebenfalls ein
#    - collected_by im Paket: Pickup-Sync via FuelCanister.to_net_dict()
#    - S-Taste auf End-Screen: _return_to_settings Signal an main.py
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
    Erweitert Game um Netzwerk-Logik.
    Modus 3: empfängt Input des Clients als Auto-B-Input, simuliert beide Autos.
    """

    def __init__(self, mode: int = 1, track_length: int = 20,
                 speed_scale: float = SPEED_SCALE_NORMAL,
                 net: "HostConnection | None" = None,
                 car_class_host: str = "balanced",
                 car_class_client: str = "balanced") -> None:
        self._host_mode         = mode
        self._host_track_length = track_length
        self._host_speed_scale  = speed_scale
        self._generated_track   = Track.generate(length=track_length)

        # Netz: entweder extern (Lobby) oder neu erstellen
        if net is not None:
            self._net      = net
            self._owns_net = False
        else:
            self._net      = HostConnection(NET_PORT)
            self._net.start()
            self._owns_net = True

        # Klassen sind durch die Lobby-Auswahl gelockt
        super().__init__(locked_class0=car_class_host,
                         locked_class1=car_class_client)
        self.mode        = mode
        self.speed_scale = speed_scale

        self._last_client_inp    = InputState()
        self._pending_map_send   = False
        self._return_to_settings = False

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
        elif event.key == pygame.K_s and (self.game_over or self.winner):
            self.running               = False
            self._return_to_settings   = True

    # ─── Update ──────────────────────────────────────────────────────────────

    def update(self, dt: float, input_override=None, input_car1=None) -> None:
        # Phase 11: Client will zurück zur Lobby?
        if self._net.client_wants_lobby():
            self._return_to_lobby  = True
            self._lobby_initiator  = "remote"
            self.running           = False
            return

        # Phase 11.1: request_lobby_state während des Spiels ignorieren
        # (wird in HostLobby behandelt; hier nur leeren damit Flag nicht hängt)
        self._net.client_requests_state()

        # Map-Handshake: einmalig nach neuem Client oder Reset
        if self._net.got_new_client() or self._pending_map_send:
            if self._net.is_connected():
                map_data = {**self.track.to_dict(), "game_mode": self.mode}
                self._net.send_map(map_data)
            self._pending_map_send = False

        # Countdown einfrieren bis Client verbunden
        if not self._net.is_connected() and self._countdown > 0:
            self.cars[0].state.speed = 0.0
            if self.mode == 3:
                self.cars[1].state.speed = 0.0
            self._net.send_state(self._build_packet())
            return

        # Client-Input abholen
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

        # Input je Modus
        keys = pygame.key.get_pressed()
        if self.mode == 1:
            merged_inp = InputState.merge(InputState.host_keys(keys),
                                          self._last_client_inp)
            car1_inp   = None
        elif self.mode == 2:
            merged_inp = InputState.from_keys(keys)
            car1_inp   = None
        else:
            merged_inp = InputState.from_keys(keys)
            car1_inp   = self._last_client_inp

        super().update(dt, input_override=merged_inp, input_car1=car1_inp)
        self._net.send_state(self._build_packet())

    # ─── Paket ───────────────────────────────────────────────────────────────

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
            # ── Phase 5.3: paused + collected_by Sync ────────────────────────
            "paused":     self._paused,
            "canisters":  [c.to_net_dict()  for c in self.canisters],
            "boosts":     [b.to_net_dict()  for b in self.boosts],
            "oils":       [o.to_net_dict()  for o in self.oils],
            "item_boxes": [ib.to_net_dict() for ib in self.item_boxes],
            "boomerangs": [b.to_net_dict()  for b  in self.boomerangs],
            "car0_class": self.cars[0].car_class,
            "car1_class": self.cars[1].car_class,
            # Inventar-Sync: Client zeigt eigenes Item korrekt an
            "car0_inv":   self.cars[0].inventory or "",
            "car1_inv":   (self.cars[1].inventory or "") if self.mode == 3 else "",
        }
        # Auto B (Modus 3)
        if self.mode == 3:
            s1 = self.cars[1].state
            pkt["car1"] = {
                "x": s1.x, "y": s1.y,
                "angle": s1.angle,
                "speed": s1.speed,
                "fuel":  s1.fuel,
            }
        return pkt

    # ─── draw ────────────────────────────────────────────────────────────────

    def draw(self) -> None:
        s = self.cars[0].state
        self.draw_world(self.screen)
        if self.mode == 2:
            csx, csy = self.camera.w2s(s.x, s.y)
            self.draw_fog(self.screen, (csx, csy))
        self.draw_pings(self.screen)
        self.draw_hud(self.screen)
        self.draw_countdown(self.screen)
        if self.game_over or self.winner:
            self.draw_winner(self.screen)
        # Pause-Overlay (Host zeichnet es auch – Client erhält _paused via Paket)
        if self._paused:
            self.draw_pause_overlay(self.screen)
        self._draw_status_overlay()
        pygame.display.flip()

    def _draw_status_overlay(self) -> None:
        # Verbindungsstatus oben rechts
        txt, color = (("NAVIGATOR VERBUNDEN", GREEN) if self._net.is_connected()
                      else ("Warte auf Navigator …", ORANGE))
        lbl = self._status_font.render(txt, True, color)
        self.screen.blit(lbl, (SCREEN_W - lbl.get_width() - 12, 12))

        # Modus oben Mitte
        modes  = {1: "SPLIT CONTROL", 2: "⦿ PANIC PILOT", 3: "⚡ PvP RACING"}
        colors = {1: GRAY, 2: CYAN, 3: YELLOW}
        m_lbl = self._mode_font.render(
            modes.get(self.mode, ""), True, colors.get(self.mode, WHITE))
        self.screen.blit(m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, 10))

        # Tasten-Hint unten links – unterschiedlich je Zustand
        if self.game_over or self.winner:
            hint_txt = "[R]=Restart  [M]=Menu  [S]=Settings"
            hint_color = CYAN
        else:
            hint_txt  = "A/D=Lenken  M=Modus  P=Pause  R=Reset"
            hint_color = GRAY
        hint = self._status_font.render(hint_txt, True, hint_color)
        self.screen.blit(hint, (12, SCREEN_H - 38))

    def run(self) -> None:
        try:
            super().run()
        finally:
            # Phase 11: Nur senden wenn Host selbst die Lobby initiiert hat
            if (getattr(self, "_return_to_lobby", False)
                    and getattr(self, "_lobby_initiator", "") != "remote"):
                self._net.send_back_to_lobby()
            # Phase 11.2: Flags nullen damit nächster Start sauber ist
            if self._net.is_connected():
                self._net.reset_lobby_flags()
            if self._owns_net:
                self._net.shutdown()


if __name__ == "__main__":
    HostGame().run()
