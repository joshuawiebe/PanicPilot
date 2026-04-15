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
def _start_host(mode: int, length: int, speed_scale: float = 1.0,
                 car_class_host: str = DEFAULT_CAR_CLASS,
                 car_class_client: str = DEFAULT_CAR_CLASS) -> tuple[bool, bool]:
    """
    Startet das Spiel als Host.
    Phase 10: Akzeptiert car_class_host und car_class_client.
    Gibt (return_to_menu, return_to_settings) zurück.
    """
    from host import HostGame

    game = HostGame(mode=mode, track_length=length, speed_scale=speed_scale,
                   car_class_host=car_class_host, car_class_client=car_class_client)
    game.run()
    return (
        getattr(game, "_return_to_menu", False),
        getattr(game, "_return_to_settings", False),
    )


def _start_solo(length: int, speed_scale: float = 1.0,
                 car_class: str = DEFAULT_CAR_CLASS) -> bool:
    """
    Startet lokales Solo-Spiel (kein Netzwerk). 
    Phase 10: Akzeptiert car_class.
    Gibt return_to_menu zurück.
    """
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
    # ── Phase 9: Car Classes ──────────────────────────────────────────────
    game.car_class_host = car_class
    game.car_class_client = DEFAULT_CAR_CLASS
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


# ── Car Selection UI ──────────────────────────────────────────────────────────

class CarSelectionMenu:
    """
    Car Selection Screen – zeigt 3 Klassen mit Icons, Stats und Navigation.
    Phase 10: Erste Komponente des Pro Lobby Systems.
    """

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self._title_font = pygame.font.SysFont("Arial", 40, bold=True)
        self._class_font = pygame.font.SysFont("Arial", 28, bold=True)
        self._stat_font = pygame.font.SysFont("Arial", 16)
        self._info_font = pygame.font.SysFont("Arial", 14)
        
        self.selected_idx = 0  # 0=balanced, 1=speedster, 2=tank
        self.class_list = ["balanced", "speedster", "tank"]
        
        # Buttons
        cx = SCREEN_W // 2
        self._btn_prev = Button(cx - 250, SCREEN_H // 2 + 80, "< Zurück")
        self._btn_next = Button(cx + 250, SCREEN_H // 2 + 80, "Weiter >")
        self._btn_select = Button(cx, SCREEN_H // 2 + 160, "WÄHLEN")
        self._btn_cancel = Button(cx, SCREEN_H // 2 + 230, "Abbrechen")

    def run(self, title: str = "AUTO WÄHLEN") -> str | None:
        """
        Blockierendes Menü. Gibt gewählte Klasse zurück ("balanced", "speedster", "tank") oder None (abgebrochen).
        """
        clock = pygame.time.Clock()
        while True:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                
                if self._btn_prev.is_clicked(event):
                    self.selected_idx = (self.selected_idx - 1) % len(self.class_list)
                elif self._btn_next.is_clicked(event):
                    self.selected_idx = (self.selected_idx + 1) % len(self.class_list)
                elif self._btn_select.is_clicked(event):
                    return self.class_list[self.selected_idx]
                elif self._btn_cancel.is_clicked(event):
                    return None
                
                # Keyboard-Shortcuts
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:
                        self.selected_idx = (self.selected_idx - 1) % len(self.class_list)
                    elif event.key == pygame.K_RIGHT:
                        self.selected_idx = (self.selected_idx + 1) % len(self.class_list)
                    elif event.key == pygame.K_RETURN:
                        return self.class_list[self.selected_idx]

            self._draw(title, mouse)
            pygame.display.flip()
            clock.tick(60)

    def _draw(self, title: str, mouse_pos: tuple) -> None:
        self.screen.fill(MENU_BG)
        self._draw_bg()
        
        # Titel
        t = self._title_font.render(title, True, YELLOW)
        self.screen.blit(t, ((SCREEN_W - t.get_width()) // 2, 80))
        
        # Drei Klassen nebeneinander anzeigen
        cx = SCREEN_W // 2
        class_x_positions = [cx - 320, cx, cx + 320]
        class_colors = [
            CAR_CLASSES["balanced"]["color"],
            CAR_CLASSES["speedster"]["color"],
            CAR_CLASSES["tank"]["color"],
        ]
        
        for i, class_name in enumerate(self.class_list):
            x = class_x_positions[i]
            is_selected = i == self.selected_idx
            self._draw_class_card(x, SCREEN_H // 2 + 20, class_name, class_colors[i], is_selected)
        
        # Buttons
        self._btn_prev.draw(self.screen, mouse_pos)
        self._btn_next.draw(self.screen, mouse_pos)
        self._btn_select.draw(self.screen, mouse_pos)
        self._btn_cancel.draw(self.screen, mouse_pos)

    def _draw_class_card(self, x: int, y: int, class_name: str, color: tuple, selected: bool) -> None:
        """Zeichnet eine Auto-Klassen-Karte mit Icon und Stats."""
        stats = CAR_CLASSES[class_name]
        
        # Card-Hintergrund
        card_rect = pygame.Rect(x - 120, y - 100, 240, 200)
        border_color = YELLOW if selected else (100, 100, 100)
        border_width = 4 if selected else 2
        
        # Card mit Gradient-ähnlichem Effekt
        pygame.draw.rect(self.screen, (15, 25, 50), card_rect, border_radius=12)
        pygame.draw.rect(self.screen, border_color, card_rect, border_width, border_radius=12)
        
        # Glow-Effect wenn selected
        if selected:
            glow_rect = card_rect.inflate(8, 8)
            pygame.draw.rect(self.screen, (255, 220, 0, 40), glow_rect, 2, border_radius=14)
        
        # Klassen-Name
        name_lbl = self._class_font.render(stats["display_name"], True, color)
        self.screen.blit(name_lbl, (x - name_lbl.get_width() // 2, y - 80))
        
        # Beschreibung
        desc_lbl = self._info_font.render(stats["description"], True, C_LABEL)
        self.screen.blit(desc_lbl, (x - desc_lbl.get_width() // 2, y - 50))
        
        # Stats mit Balken-Visualisierung
        speed = stats["max_speed"]
        accel = stats["accel"]
        fuel_drain = stats["fuel_drain"]
        
        # Speed Bar (0-700 normalize)
        speed_pct = min(100, int((speed / 700.0) * 100))
        stat_y = y - 20
        bar_width = 180
        pygame.draw.rect(self.screen, (40, 40, 40), (x - bar_width // 2, stat_y, bar_width, 12), border_radius=3)
        pygame.draw.rect(self.screen, (100, 200, 255), (x - bar_width // 2, stat_y, int(bar_width * speed_pct / 100), 12), border_radius=3)
        speed_lbl = self._info_font.render(f"Speed: {int(speed)}", True, WHITE)
        self.screen.blit(speed_lbl, (x - speed_lbl.get_width() // 2, stat_y - 16))
        
        # Acceleration Bar
        accel_pct = min(100, int((accel / 450.0) * 100))
        stat_y = y + 8
        pygame.draw.rect(self.screen, (40, 40, 40), (x - bar_width // 2, stat_y, bar_width, 12), border_radius=3)
        pygame.draw.rect(self.screen, (255, 165, 0), (x - bar_width // 2, stat_y, int(bar_width * accel_pct / 100), 12), border_radius=3)
        accel_lbl = self._info_font.render(f"Accel: {int(accel)}", True, WHITE)
        self.screen.blit(accel_lbl, (x - accel_lbl.get_width() // 2, stat_y - 16))
        
        # Efficiency (inverse of fuel_drain)
        eff_pct = 100 - min(100, int((fuel_drain / 12.0) * 100))
        stat_y = y + 36
        pygame.draw.rect(self.screen, (40, 40, 40), (x - bar_width // 2, stat_y, bar_width, 12), border_radius=3)
        pygame.draw.rect(self.screen, (100, 255, 100), (x - bar_width // 2, stat_y, int(bar_width * eff_pct / 100), 12), border_radius=3)
        eff_lbl = self._info_font.render(f"Efficiency: {eff_pct}%", True, WHITE)
        self.screen.blit(eff_lbl, (x - eff_lbl.get_width() // 2, stat_y - 16))

    def _draw_bg(self) -> None:
        """Dekorative Linien."""
        for i in range(0, SCREEN_W, 120):
            pygame.draw.line(self.screen, (20, 35, 55), (i, 0), (i, SCREEN_H))
        for i in range(0, SCREEN_H, 120):
            pygame.draw.line(self.screen, (20, 35, 55), (0, i), (SCREEN_W, i))


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
            ip_val = self._ip_font.render(f"  {self._own_ip}:8081  ", True, CYAN)
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
    """Setup-Screen für den Solo-Modus: Streckenlänge + Geschwindigkeit + Auto.
    Phase 10: Mit Car-Selection UI."""

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
        self._car_class = DEFAULT_CAR_CLASS  # ← Phase 10
        y0 = SCREEN_H // 2 + 40
        self._btn_speed = Button(cx, y0, "Tempo", w=280, h=50)
        self._btn_car = Button(cx, y0 + 70, "Auto: Balanced", w=280, h=50)  # ← Phase 10
        self._btn_start = Button(cx, y0 + 140, "  SOLO STARTEN  ")
        self._btn_back = Button(cx, y0 + 210, "  Zurück  ", w=180, h=44)

    def run(self) -> tuple[int, float, str] | None:
        """Gibt (length, speed_scale, car_class) oder None zurück."""
        clock = pygame.time.Clock()
        spd_colors = [ORANGE, GREEN, RED]
        car_select = CarSelectionMenu(self.screen)  # ← Phase 10
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
                # ── Phase 10: Auto-Button ────────────────────────────────────────
                if self._btn_car.is_clicked(event):
                    result = car_select.run("WÄHLE DEIN AUTO")
                    if result:
                        self._car_class = result
                if self._btn_start.is_clicked(event):
                    _, scale = self.SPEED_OPTIONS[self._speed_idx]
                    return self._slider.value, scale, self._car_class  # ← Phase 10
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
            # ── Phase 10: Auto-Button-Label ──────────────────────────────────────
            car_stats = CAR_CLASSES[self._car_class]
            self._btn_car.label = f"Auto: {car_stats['display_name']}"
            self._btn_car.draw(self.screen, mouse)
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


# ── Phase 10: Lobby System ─────────────────────────────────────────────────────

class HostLobby:
    """
    Host-Side Lobby: Wartet auf Client, zeigt beide Auto-Auswahlen.
    Phase 10: Pro Lobby System.
    """

    def __init__(self, screen: pygame.Surface, mode: int, track_length: int, speed_scale: float) -> None:
        self.screen = screen
        self.mode = mode
        self.track_length = track_length
        self.speed_scale = speed_scale
        
        self._title_font = pygame.font.SysFont("Arial", 40, bold=True)
        self._status_font = pygame.font.SysFont("Arial", 20)
        self._info_font = pygame.font.SysFont("Arial", 16)
        
        self.host_car_class = DEFAULT_CAR_CLASS
        self.client_car_class = DEFAULT_CAR_CLASS
        self.host_ready = False
        self.client_connected = False
        self.client_ready = False
        
        # Buttons
        cx = SCREEN_W // 2
        self._btn_host_car = Button(cx - 240, SCREEN_H // 2 + 40, "HOST AUTO")
        self._btn_client_car = Button(cx + 240, SCREEN_H // 2 + 40, "CLIENT AUTO")
        self._btn_ready = Button(cx, SCREEN_H // 2 + 140, "✓ BEREIT", w=280, h=60)
        self._btn_cancel = Button(cx, SCREEN_H // 2 + 220, "Abbrechen")
        
        self._countdown = 0.0
        self._start_game = False

    def run(self) -> tuple[str, str] | None:
        """
        Host-Lobby. Gibt (host_car_class, client_car_class) zurück wenn bereit, oder None (abgebrochen).
        Wird blockierend bis beide Spieler ready sind.
        """
        # Placeholder: In echter Version würde hier Network-Connection gemanagt
        self.client_connected = True  # Vereinfacht für MVP
        
        car_select = CarSelectionMenu(self.screen)
        
        clock = pygame.time.Clock()
        while True:
            mouse = pygame.mouse.get_pos()
            dt = clock.tick(60) / 1000.0
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                
                if self._btn_host_car.is_clicked(event):
                    result = car_select.run("WÄHLE DEIN AUTO (HOST)")
                    if result:
                        self.host_car_class = result
                elif self._btn_client_car.is_clicked(event):
                    result = car_select.run("WÄHLE AUTO FÜR CLIENT")
                    if result:
                        self.client_car_class = result
                elif self._btn_ready.is_clicked(event):
                    self.host_ready = not self.host_ready
                    if self.host_ready:
                        self._countdown = 5.0
                elif self._btn_cancel.is_clicked(event):
                    return None
                
                # Keyboard
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        if self.host_ready and self.client_ready:
                            return (self.host_car_class, self.client_car_class)

            # Simulation: Im echten System würde hier Network-Sync stattfinden
            if self.host_ready:
                # Client sollte bereit sein (Simulation)
                self.client_ready = True
                self._countdown -= dt
                if self._countdown <= 0:
                    return (self.host_car_class, self.client_car_class)
            
            self._draw(mouse)
            pygame.display.flip()

        return None

    def _draw(self, mouse_pos: tuple) -> None:
        self.screen.fill(MENU_BG)
        self._draw_bg()
        
        # Titel
        t = self._title_font.render("LOBBY - WARTET AUF CLIENTS", True, YELLOW)
        self.screen.blit(t, ((SCREEN_W - t.get_width()) // 2, 60))
        
        # Host Auto (Linke Seite)
        self._draw_player_info(
            200, SCREEN_H // 2,
            "HOST (Du)", self.host_car_class,
            self.host_ready, True
        )
        
        # Client Auto (Rechte Seite)
        if self.client_connected:
            client_ready_text = "✓ BEREIT" if self.client_ready else "Wählt Auto..."
            self._draw_player_info(
                SCREEN_W - 200, SCREEN_H // 2,
                "CLIENT", self.client_car_class,
                self.client_ready, False
            )
        else:
            nc_lbl = self._status_font.render("⏳ CLIENT VERBINDUNGSSTEHT AUS...", True, ORANGE)
            self.screen.blit(nc_lbl, ((SCREEN_W - nc_lbl.get_width()) // 2, SCREEN_H // 2 + 10))
        
        # Buttons
        self._btn_host_car.draw(self.screen, mouse_pos)
        self._btn_client_car.draw(self.screen, mouse_pos)
        
        ready_label = "✓ BEREIT!" if self.host_ready else "BEREIT?"
        self._btn_ready.label = ready_label
        self._btn_ready.draw(self.screen, mouse_pos)
        self._btn_cancel.draw(self.screen, mouse_pos)
        
        # Status
        if self.host_ready and self.client_ready:
            status = self._status_font.render(f"STARTING IN {max(0, int(self._countdown))}...", True, GREEN)
            self.screen.blit(status, ((SCREEN_W - status.get_width()) // 2, SCREEN_H - 100))

    def _draw_player_info(self, x: int, y: int, player_name: str, car_class: str, is_ready: bool, is_host: bool) -> None:
        """Zeichnet Spieler-Info Box."""
        # Box
        box_rect = pygame.Rect(x - 90, y - 80, 180, 160)
        pygame.draw.rect(self.screen, (20, 30, 60), box_rect, border_radius=10)
        border_color = GREEN if is_ready else CYAN
        pygame.draw.rect(self.screen, border_color, box_rect, 3, border_radius=10)
        
        # Name
        name_lbl = self._status_font.render(player_name, True, C_TEXT)
        self.screen.blit(name_lbl, (x - name_lbl.get_width() // 2, y - 70))
        
        # Auto-Info
        stats = CAR_CLASSES[car_class]
        class_lbl = self._info_font.render(stats["display_name"], True, stats["color"])
        self.screen.blit(class_lbl, (x - class_lbl.get_width() // 2, y - 35))
        
        # Ready Status
        ready_text = "✓ READY" if is_ready else "AUSWAHL"
        ready_color = GREEN if is_ready else ORANGE
        ready_lbl = self._info_font.render(ready_text, True, ready_color)
        self.screen.blit(ready_lbl, (x - ready_lbl.get_width() // 2, y + 20))

    def _draw_bg(self) -> None:
        """Dekorative Linien."""
        for i in range(0, SCREEN_W, 120):
            pygame.draw.line(self.screen, (20, 35, 55), (i, 0), (i, SCREEN_H))
        for i in range(0, SCREEN_H, 120):
            pygame.draw.line(self.screen, (20, 35, 55), (0, i), (SCREEN_W, i))


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
                
                # ── Phase 10: HostLobby für Auto-Auswahl ──────────────────────────
                lobby = HostLobby(screen, mode, length, speed_scale)
                lobby_result = lobby.run()
                if lobby_result is None:
                    continue  # Abgebrochen → Hauptmenü
                
                host_car, client_car = lobby_result
                
                last_settings = {
                    "mode": mode,
                    "length": length,
                    "speed_idx": setup._speed_idx,
                }
                while True:  # Neustart-Schleife
                    pygame.quit()
                    pygame.init()
                    to_menu, to_settings = _start_host(
                        mode, length, speed_scale,
                        car_class_host=host_car,
                        car_class_client=client_car
                    )
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
                        # Neuer Lobby-Screen nach Settings-Change
                        lobby = HostLobby(screen, mode, length, speed_scale)
                        lobby_result = lobby.run()
                        if lobby_result is None:
                            break
                        host_car, client_car = lobby_result
                        continue  # Neu starten mit geänderten Settings
                    break  # M oder ESC → Hauptmenü
        elif choice == "solo":
            result = SoloSetupMenu(screen).run()
            if result is not None:
                # ── Phase 10: Car-Class extrahieren ─────────────────────────────
                length, speed_scale, car_class = result
                pygame.quit()
                pygame.init()
                _start_solo(length, speed_scale, car_class)
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
