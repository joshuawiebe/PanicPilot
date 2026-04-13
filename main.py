# =============================================================================
#  main.py  –  Panic Pilot | Zentraler Launcher (Phase 5)
# =============================================================================
#
#  Menü-Struktur:
#    [HOST STARTEN]  → wählt Streckenlänge + Modus, startet HostGame
#    [CLIENT VERBINDEN] → IP-Eingabe, startet ClientGame
#    [BEENDEN]
#
#  Steuerung im Menü:
#    Maus-Klick auf Buttons
#    Im IP-Feld: Tastatur-Eingabe
# =============================================================================
from __future__ import annotations
import sys
import pygame

from settings import *


# Lazy imports – nur laden wenn tatsächlich gebraucht
def _start_host(mode: int, length: int, speed_scale: float = 1.0) -> tuple[bool, bool]:
    """
    Startet das Spiel als Host.
    Gibt (return_to_menu, return_to_settings) zurück.
    """
    from host import HostGame

    game = HostGame(mode=mode, track_length=length, speed_scale=speed_scale)
    game.run()
    return (
        getattr(game, "_return_to_menu", False),
        getattr(game, "_return_to_settings", False),
    )


def _start_solo(length: int, speed_scale: float = 1.0) -> bool:
    """Startet lokales Solo-Spiel (kein Netzwerk). Gibt return_to_menu zurück."""
    from game import Game, SPEED_SCALE_NORMAL
    from track import Track

    pygame.init()
    # Solo: Game direkt instanzieren, Mode 1, keine Netzwerklogik
    track = Track.generate(length=length)
    game = Game.__new__(Game)
    # Minimal-Init ohne pygame.init() (bereits aufgerufen)
    game.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption(f"Panic Pilot – SOLO | R=Reset  P=Pause  ESC=Beenden")
    game.clock = pygame.time.Clock()
    game.running = True
    game.mode = 1
    game.pings = []
    game._return_to_menu = False
    game._paused = False
    game.speed_scale = speed_scale
    game._warn_font = pygame.font.SysFont("Arial", 18, bold=True)
    game._countdown_font = pygame.font.SysFont("Arial", 160, bold=True)
    game._win_font = pygame.font.SysFont("Arial", 72, bold=True)
    game._sub_font = pygame.font.SysFont("Arial", 28, bold=True)
    game._pause_font = pygame.font.SysFont("Arial", 80, bold=True)
    game._flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    game._fog_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    game.camera = __import__("camera").Camera()
    game._init_game_objects(track=track)
    game.run()
    return getattr(game, "_return_to_menu", False)


def _start_client(host_ip: str) -> bool:
    """Gibt True zurück wenn Spiel mit 'M' beendet wurde."""
    from client import ClientGame

    game = ClientGame(host_ip)
    game.run()
    return getattr(game, "_return_to_menu", False)


# ── UI-Konstanten ─────────────────────────────────────────────────────────────
MENU_BG = HUD_BG
BTN_W, BTN_H = 340, 56
BTN_GAP = 18
BTN_RADIUS = 10

# Farben
C_BTN_IDLE = (25, 40, 70)
C_BTN_HOVER = (40, 70, 130)
C_BTN_ACTIVE = (60, 120, 200)
C_BTN_BORDER = (80, 130, 220)
C_TEXT = (220, 230, 255)
C_LABEL = (150, 170, 210)
C_INPUT_BG = (18, 28, 50)
C_INPUT_BORD = (80, 130, 220)


class Button:
    def __init__(
        self, cx: int, cy: int, label: str, w: int = BTN_W, h: int = BTN_H
    ) -> None:
        self.rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        self.label = label
        self._font = pygame.font.SysFont("Arial", 22, bold=True)

    def draw(self, surface: pygame.Surface, mouse_pos: tuple) -> None:
        hovered = self.rect.collidepoint(mouse_pos)
        color = C_BTN_HOVER if hovered else C_BTN_IDLE
        pygame.draw.rect(surface, color, self.rect, border_radius=BTN_RADIUS)
        pygame.draw.rect(surface, C_BTN_BORDER, self.rect, 2, border_radius=BTN_RADIUS)
        lbl = self._font.render(self.label, True, C_TEXT)
        surface.blit(
            lbl,
            (
                self.rect.centerx - lbl.get_width() // 2,
                self.rect.centery - lbl.get_height() // 2,
            ),
        )

    def is_clicked(self, event: pygame.event.Event) -> bool:
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class Slider:
    """Horizontaler Schieberegler für Streckenlänge."""

    def __init__(
        self, cx: int, cy: int, label: str, vmin: int, vmax: int, value: int
    ) -> None:
        self.cx = cx
        self.cy = cy
        self.label = label
        self.vmin = vmin
        self.vmax = vmax
        self.value = value
        self.width = 280
        self._track = pygame.Rect(cx - self.width // 2, cy - 4, self.width, 8)
        self._dragging = False
        self._font = pygame.font.SysFont("Arial", 18)
        self._lbl_f = pygame.font.SysFont("Arial", 15)

    def _handle_x(self) -> int:
        t = (self.value - self.vmin) / (self.vmax - self.vmin)
        return self._track.left + int(t * self._track.width)

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, (40, 55, 90), self._track, border_radius=4)
        hx = self._handle_x()
        filled = pygame.Rect(
            self._track.left, self._track.top, hx - self._track.left, 8
        )
        pygame.draw.rect(surface, C_BTN_ACTIVE, filled, border_radius=4)
        pygame.draw.circle(surface, C_BTN_BORDER, (hx, self.cy), 12)
        pygame.draw.circle(surface, C_TEXT, (hx, self.cy), 8)
        lbl = self._lbl_f.render(self.label, True, C_LABEL)
        surface.blit(lbl, (self.cx - self.width // 2, self.cy - 26))
        val_lbl = self._font.render(str(self.value), True, C_TEXT)
        surface.blit(
            val_lbl,
            (self.cx + self.width // 2 + 14, self.cy - val_lbl.get_height() // 2),
        )

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hx = self._handle_x()
            if math.hypot(event.pos[0] - hx, event.pos[1] - self.cy) < 18:
                self._dragging = True
        elif event.type == pygame.MOUSEBUTTONUP:
            self._dragging = False
        elif event.type == pygame.MOUSEMOTION and self._dragging:
            t = (event.pos[0] - self._track.left) / self._track.width
            t = max(0.0, min(1.0, t))
            self.value = self.vmin + int(t * (self.vmax - self.vmin))


import math  # für Slider.handle_event


class TextInput:
    def __init__(self, cx: int, cy: int, placeholder: str = "") -> None:
        self.rect = pygame.Rect(cx - 170, cy - 24, 340, 48)
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self._font = pygame.font.SysFont("Courier", 20, bold=True)
        self._ph_font = pygame.font.SysFont("Arial", 18)

    def draw(self, surface: pygame.Surface) -> None:
        border = C_BTN_ACTIVE if self.active else C_INPUT_BORD
        pygame.draw.rect(surface, C_INPUT_BG, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=8)
        if self.text:
            lbl = self._font.render(self.text, True, C_TEXT)
        else:
            lbl = self._ph_font.render(self.placeholder, True, C_LABEL)
        surface.blit(lbl, (self.rect.x + 12, self.rect.centery - lbl.get_height() // 2))
        # Cursor
        if self.active and pygame.time.get_ticks() % 1000 < 500:
            x = self.rect.x + 12 + (self._font.size(self.text)[0] if self.text else 0)
            pygame.draw.line(
                surface, C_TEXT, (x, self.rect.y + 8), (x, self.rect.bottom - 8), 2
            )

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.active = False
            elif len(self.text) < 15:
                ch = event.unicode
                if ch in "0123456789.":
                    self.text += ch


# ── Menü-Klassen ──────────────────────────────────────────────────────────────


class Menu:
    """Haupt-Menü."""

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.running = True
        self.choice = None  # "host" | "client" | "quit"
        self._title_font = pygame.font.SysFont("Arial", 72, bold=True)
        self._sub_font = pygame.font.SysFont("Arial", 20)
        cx = SCREEN_W // 2
        y0 = SCREEN_H // 2 - 55
        self._btn_host = Button(cx, y0, "  HOST STARTEN  ")
        self._btn_solo = Button(cx, y0 + BTN_H + BTN_GAP, "  SOLO SPIELEN  ")
        self._btn_client = Button(
            cx, y0 + 2 * (BTN_H + BTN_GAP), "  CLIENT VERBINDEN  "
        )
        self._btn_quit = Button(
            cx, y0 + 3 * (BTN_H + BTN_GAP), "  BEENDEN  ", w=200, h=46
        )

    def run(self) -> str:
        clock = pygame.time.Clock()
        while self.running:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if self._btn_host.is_clicked(event):
                    return "host"
                if self._btn_solo.is_clicked(event):
                    return "solo"
                if self._btn_client.is_clicked(event):
                    return "client"
                if self._btn_quit.is_clicked(event):
                    return "quit"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return "quit"

            self.screen.fill(MENU_BG)
            self._draw_bg()
            # Titel
            t = self._title_font.render("PANIC PILOT", True, YELLOW)
            self.screen.blit(t, ((SCREEN_W - t.get_width()) // 2, 120))
            sub = self._sub_font.render("Asymmetrisches Koop-Rennspiel", True, C_LABEL)
            self.screen.blit(sub, ((SCREEN_W - sub.get_width()) // 2, 210))
            self._btn_host.draw(self.screen, mouse)
            self._btn_solo.draw(self.screen, mouse)
            self._btn_client.draw(self.screen, mouse)
            self._btn_quit.draw(self.screen, mouse)
            pygame.display.flip()
            clock.tick(60)
        return "quit"

    def _draw_bg(self) -> None:
        """Dekorative Linien im Hintergrund."""
        for i in range(0, SCREEN_W, 120):
            pygame.draw.line(self.screen, (20, 35, 55), (i, 0), (i, SCREEN_H))
        for i in range(0, SCREEN_H, 120):
            pygame.draw.line(self.screen, (20, 35, 55), (0, i), (SCREEN_W, i))


class HostSetupMenu:
    """Einstellungen für den Host: Modus + Streckenlänge + Geschwindigkeit."""

    # Speed-Stufen: (Label, speed_scale-Wert)
    SPEED_OPTIONS = [("🐢  Langsam", 0.70), ("🏎  Normal", 1.00), ("⚡  Schnell", 1.40)]

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self._title = pygame.font.SysFont("Arial", 40, bold=True)
        self._lbl_font = pygame.font.SysFont("Arial", 20)
        self._ip_font = pygame.font.SysFont("Courier", 26, bold=True)
        self._ip_label = pygame.font.SysFont("Arial", 16)
        import socket as _sock

        try:
            with _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM) as _s:
                _s.connect(("8.8.8.8", 80))
                self._own_ip = _s.getsockname()[0]
        except OSError:
            self._own_ip = _sock.gethostbyname(_sock.gethostname())
        cx = SCREEN_W // 2
        self._slider = Slider(
            cx, SCREEN_H // 2 - 60, "Streckenlänge (Tiles)", 10, 50, 20
        )
        self._modes = [1, 2, 3]
        self._mode_idx = 0
        self._speed_idx = 1  # Standard = Normal
        self._mode_labels = {
            1: "Modus 1: Split Control",
            2: "Modus 2: Panic Pilot (Fog)",
            3: "Modus 3: PvP Racing",
        }
        y0 = SCREEN_H // 2 + 40
        self._btn_speed = Button(cx, y0, "Geschwindigkeit", w=280, h=50)
        self._btn_mode = Button(cx, y0 + 62, "Modus wechseln", w=280, h=50)
        self._btn_start = Button(cx, y0 + 132, "  SPIEL STARTEN  ")
        self._btn_back = Button(cx, y0 + 200, "  Zurück  ", w=180, h=44)

    def run(self, prefill: dict | None = None) -> tuple | None:
        """
        Gibt (mode, length, speed_scale) zurück oder None (zurück).
        prefill: dict mit vorherigen Werten für Settings-Rückkehr aus End-Screen.
        """
        if prefill:
            self._mode_idx = self._modes.index(prefill.get("mode", 1))
            self._speed_idx = prefill.get("speed_idx", 1)
            self._slider.value = prefill.get("length", 20)

        clock = pygame.time.Clock()
        while True:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                self._slider.handle_event(event)
                if self._btn_speed.is_clicked(event):
                    self._speed_idx = (self._speed_idx + 1) % len(self.SPEED_OPTIONS)
                if self._btn_mode.is_clicked(event):
                    self._mode_idx = (self._mode_idx + 1) % len(self._modes)
                if self._btn_start.is_clicked(event):
                    _, scale = self.SPEED_OPTIONS[self._speed_idx]
                    return self._modes[self._mode_idx], self._slider.value, scale
                if self._btn_back.is_clicked(event):
                    return None

            self.screen.fill(MENU_BG)
            t = self._title.render("HOST-EINSTELLUNGEN", True, YELLOW)
            self.screen.blit(t, ((SCREEN_W - t.get_width()) // 2, 80))
            # IP
            ip_hint = self._ip_label.render("Deine IP (für den Client):", True, C_LABEL)
            ip_val = self._ip_font.render(f"  {self._own_ip}:54321  ", True, CYAN)
            box = ip_val.get_rect(center=(SCREEN_W // 2, 148))
            pygame.draw.rect(
                self.screen, (15, 30, 60), box.inflate(20, 10), border_radius=6
            )
            pygame.draw.rect(
                self.screen, C_BTN_BORDER, box.inflate(20, 10), 2, border_radius=6
            )
            self.screen.blit(ip_hint, ((SCREEN_W - ip_hint.get_width()) // 2, 126))
            self.screen.blit(ip_val, box)
            self._slider.draw(self.screen)
            # Modus-Label
            m_lbl = self._lbl_font.render(
                self._mode_labels[self._modes[self._mode_idx]], True, CYAN
            )
            self.screen.blit(
                m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, SCREEN_H // 2 - 10)
            )
            # Speed-Button mit aktuellem Wert
            spd_label, _ = self.SPEED_OPTIONS[self._speed_idx]
            spd_colors = [(100, 160, 255), (50, 200, 50), (255, 140, 0)]
            spd_color = spd_colors[self._speed_idx]
            self._btn_speed._font  # ensure font exists
            # Temporär Button-Label überschreiben
            orig_label = self._btn_speed.label
            self._btn_speed.label = f"Tempo: {spd_label}"
            self._btn_speed.draw(self.screen, mouse)
            self._btn_speed.label = orig_label
            self._btn_mode.draw(self.screen, mouse)
            self._btn_start.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()
            clock.tick(60)


class SoloSetupMenu:
    """Setup-Screen für den Solo-Modus: Streckenlänge + Geschwindigkeit."""

    SPEED_OPTIONS = [("🐢  Langsam", 0.70), ("🏎  Normal", 1.00), ("⚡  Schnell", 1.40)]

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self._title = pygame.font.SysFont("Arial", 40, bold=True)
        self._lbl_font = pygame.font.SysFont("Arial", 20)
        cx = SCREEN_W // 2
        self._slider = Slider(
            cx, SCREEN_H // 2 - 60, "Streckenlänge (Tiles)", 10, 50, 15
        )
        self._speed_idx = 1
        y0 = SCREEN_H // 2 + 40
        self._btn_speed = Button(cx, y0, "Tempo", w=280, h=50)
        self._btn_start = Button(cx, y0 + 70, "  SOLO STARTEN  ")
        self._btn_back = Button(cx, y0 + 140, "  Zurück  ", w=180, h=44)

    def run(self) -> tuple[int, float] | None:
        """Gibt (length, speed_scale) oder None zurück."""
        clock = pygame.time.Clock()
        spd_colors = [ORANGE, GREEN, RED]
        while True:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                self._slider.handle_event(event)
                if self._btn_speed.is_clicked(event):
                    self._speed_idx = (self._speed_idx + 1) % len(self.SPEED_OPTIONS)
                if self._btn_start.is_clicked(event):
                    _, scale = self.SPEED_OPTIONS[self._speed_idx]
                    return self._slider.value, scale
                if self._btn_back.is_clicked(event):
                    return None

            self.screen.fill(MENU_BG)
            t = self._title.render("SOLO EINSTELLUNGEN", True, YELLOW)
            self.screen.blit(t, ((SCREEN_W - t.get_width()) // 2, 80))
            self._slider.draw(self.screen)
            # Solo-Info
            info = self._lbl_font.render(
                "Lokales Spiel – kein Netzwerk, kein zweites Auto", True, C_LABEL
            )
            self.screen.blit(
                info, ((SCREEN_W - info.get_width()) // 2, SCREEN_H // 2 + 10)
            )
            # Speed-Button
            spd_label, _ = self.SPEED_OPTIONS[self._speed_idx]
            orig = self._btn_speed.label
            self._btn_speed.label = f"Tempo: {spd_label}"
            self._btn_speed.draw(self.screen, mouse)
            self._btn_speed.label = orig
            self._btn_start.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()
            clock.tick(60)


class ClientSetupMenu:
    """IP-Eingabe für den Client."""

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self._title = pygame.font.SysFont("Arial", 40, bold=True)
        self._lbl = pygame.font.SysFont("Arial", 20)
        cx = SCREEN_W // 2
        self._input = TextInput(cx, SCREEN_H // 2 - 20, "z.B. 192.168.1.42")
        self._input.active = True
        self._btn_connect = Button(cx, SCREEN_H // 2 + 70, "  VERBINDEN  ")
        self._btn_back = Button(cx, SCREEN_H // 2 + 140, "  Zurück  ", w=180, h=44)
        self._hint = pygame.font.SysFont("Arial", 16)

    def run(self) -> str | None:
        """Gibt Host-IP zurück oder None (zurück)."""
        clock = pygame.time.Clock()
        while True:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        ip = self._input.text.strip()
                        return ip if ip else "127.0.0.1"
                self._input.handle_event(event)
                if self._btn_connect.is_clicked(event):
                    ip = self._input.text.strip()
                    return ip if ip else "127.0.0.1"
                if self._btn_back.is_clicked(event):
                    return None

            self.screen.fill(MENU_BG)
            t = self._title.render("CLIENT VERBINDEN", True, YELLOW)
            self.screen.blit(t, ((SCREEN_W - t.get_width()) // 2, 80))
            lbl = self._lbl.render("Host-IP-Adresse eingeben:", True, C_LABEL)
            self.screen.blit(
                lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H // 2 - 70)
            )
            self._input.draw(self.screen)
            hint = self._hint.render(
                "Die IP des Hosts steht im Fenster-Titel des Hosts.", True, C_LABEL
            )
            self.screen.blit(
                hint, ((SCREEN_W - hint.get_width()) // 2, SCREEN_H // 2 + 28)
            )
            self._btn_connect.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()
            clock.tick(60)


# ── Einstiegspunkt ────────────────────────────────────────────────────────────


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Panic Pilot")

    while True:
        choice = Menu(screen).run()

        if choice == "quit":
            break
        elif choice == "host":
            setup = HostSetupMenu(screen)
            result = setup.run()
            if result is not None:
                mode, length, speed_scale = result
                last_settings = {
                    "mode": mode,
                    "length": length,
                    "speed_idx": setup._speed_idx,
                }
                while True:  # Neustart-Schleife
                    pygame.quit()
                    pygame.init()
                    to_menu, to_settings = _start_host(mode, length, speed_scale)
                    pygame.init()
                    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
                    if to_settings:
                        # S gedrückt → zurück zu Einstellungen mit vorherigen Werten
                        setup2 = HostSetupMenu(screen)
                        result2 = setup2.run(prefill=last_settings)
                        if result2 is None:
                            break  # Einstellungen abgebrochen → Hauptmenü
                        mode, length, speed_scale = result2
                        last_settings = {
                            "mode": mode,
                            "length": length,
                            "speed_idx": setup2._speed_idx,
                        }
                        continue  # Neu starten mit geänderten Settings
                    break  # M oder ESC → Hauptmenü
        elif choice == "solo":
            result = SoloSetupMenu(screen).run()
            if result is not None:
                length, speed_scale = result
                pygame.quit()
                pygame.init()
                _start_solo(length, speed_scale)
                pygame.init()
                screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        elif choice == "client":
            host_ip = ClientSetupMenu(screen).run()
            if host_ip is not None:
                pygame.quit()
                pygame.init()
                _start_client(host_ip)
                pygame.init()
                screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

    pygame.quit()


if __name__ == "__main__":
    main()
