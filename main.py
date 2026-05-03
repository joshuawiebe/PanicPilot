# =============================================================================
#  main.py  –  Panic Pilot | Phase 11.2: Stabilitäts-Fix & UI-Strenge
# =============================================================================
#
#  Änderungen gegenüber Phase 11.1:
#   1. 3-Wege-Handshake – Host sendet "start" → Client antwortet "ready_for_map"
#                         → Host sendet erst dann die Karte (Timeout 0.5 s)
#   2. Map-Timeout       – Client wartet max. 5 s auf Kartendaten, dann Lobby-Return
#   3. Flag-Reset        – reset_lobby_flags() vor/nach jedem Spiel auf beiden Seiten
#   4. UI-Strenge        – Modi 1/2: kein Client-Marker im Picker; nur Host wählt
#                          Modus 3: voller PvP-Picker mit Client-Marker
#   5. Coop-Info-Box     – erscheint nur wenn Client tatsächlich handshaked ist
#   1. IP-Validierung  – 4-Block-0–255-Check vor Connect, Errno-8-Schutz
#   2. Handshake-Sync  – Client sendet request_lobby_state direkt nach TCP-
#                        Connect; Host antwortet sofort; Client zeigt erst dann
#                        "Verbunden", wenn der erste lobby_host-Snapshot eintrifft
#   3. Echtzeit-Settings – HostLobby setzt _lobby_timer=999 für sofortigen
#                          Broadcast; nach Settings-Rückkehr wird direkt gesendet
#   4. Modus-abhängiger Picker – Modi 1/2: zentrierter Picker ohne Coop-Box
#                                (Box nur wenn Client wirklich handshaked ist);
#                                Modus 3: voller PvP-Picker mit Client-Marker
#   5. HUD-Fix – Client zeigt "?" nur solange kein Snapshot da; fällt danach
#                auf korrekte Werte zurück
# =============================================================================
from __future__ import annotations
import math
import time
import pygame

from settings import *

# Phase 12: Audio-System
try:
    import sound_manager as _sound_mod
except Exception:
    _sound_mod = None

# ── UI-Farb- und Layout-Konstanten ────────────────────────────────────────────
MENU_BG        = (6, 8, 18)
PANEL_BG       = (12, 18, 35)
ACCENT         = (0, 200, 210)
ACCENT2        = (255, 200, 30)
BTN_W, BTN_H   = 340, 54
BTN_GAP        = 16
BTN_RADIUS     = 10
C_BTN_IDLE     = (22,  36,  68)
C_BTN_HOVER    = (38,  68, 128)
C_BTN_BORDER   = (70, 120, 210)
C_TEXT         = (220, 232, 255)
C_LABEL        = (130, 155, 200)
C_INPUT_BG     = (14,  22,  44)
C_INPUT_BORD   = (70, 120, 210)
C_ERROR        = (220, 60, 60)

CLASS_COLORS = {
    "balanced":  (210,  45,  45),
    "speedster": (255, 140,   0),
    "tank":      ( 50, 175,  55),
}
CLASS_ICONS = {"balanced": "◈", "speedster": "▶▶", "tank": "⬡"}
CLASS_DESCRIPTIONS = {
    "balanced":  "Balanced  –  Good grip, normal speed",
    "speedster": "Speedy  –  High speed, slippery & thirsty",
    "tank":      "Tank  –  Slow but sturdy, off-road king",
}


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_ip(ip: str) -> bool:
    """Prüft ob ip eine gültige IPv4-Adresse ist (0.0.0.0 – 255.255.255.255)."""
    if ip == "localhost":
        return True
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


# ── Zeichenhelfer ─────────────────────────────────────────────────────────────

def _draw_bg(surface: pygame.Surface, t: float = 0.0) -> None:
    col = (20, 34, 54)
    for i in range(0, SCREEN_W, 120):
        pygame.draw.line(surface, col, (i, 0), (i, SCREEN_H))
    for i in range(0, SCREEN_H, 120):
        pygame.draw.line(surface, col, (0, i), (SCREEN_W, i))


def _draw_title(surface: pygame.Surface, text: str, y: int,
                font: pygame.font.Font,
                color: tuple = (255, 215, 0)) -> None:
    shd = font.render(text, True, (0, 0, 0))
    surface.blit(shd, ((SCREEN_W - shd.get_width()) // 2 + 3, y + 3))
    lbl = font.render(text, True, color)
    surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, y))


def _shadow_rect(surface: pygame.Surface, rect: pygame.Rect,
                 radius: int = BTN_RADIUS) -> None:
    sr = rect.move(0, 4).inflate(2, 2)
    s  = pygame.Surface((sr.w, sr.h), pygame.SRCALPHA)
    pygame.draw.rect(s, (0, 0, 0, 110), s.get_rect(), border_radius=radius + 2)
    surface.blit(s, sr.topleft)


def _glow_rect(surface: pygame.Surface, rect: pygame.Rect,
               color: tuple, layers: int = 3) -> None:
    for i in range(layers, 0, -1):
        inf = i * 5
        r   = rect.inflate(inf * 2, inf * 2)
        s   = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        alpha = 55 - i * 14
        pygame.draw.rect(s, (*color, alpha), s.get_rect(),
                         border_radius=BTN_RADIUS + inf)
        surface.blit(s, r.topleft)


# ── Wiederverwendbare UI-Komponenten ──────────────────────────────────────────

class Button:
    def __init__(self, cx: int, cy: int, label: str,
                 w: int = BTN_W, h: int = BTN_H,
                 accent: tuple | None = None) -> None:
        self.rect   = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        self.label  = label
        self.accent = accent
        self._font  = pygame.font.SysFont("Arial", 21, bold=True)

    def draw(self, surface: pygame.Surface, mouse_pos: tuple,
             override_color: tuple | None = None,
             disabled: bool = False) -> None:
        hovered = self.rect.collidepoint(mouse_pos) and not disabled
        if disabled:
            bg = (18, 22, 38);  border = (40, 50, 70)
        elif override_color:
            bg = override_color;  border = C_BTN_BORDER
        elif hovered:
            bg = C_BTN_HOVER;  border = self.accent or ACCENT
        else:
            bg = C_BTN_IDLE;   border = C_BTN_BORDER
        _shadow_rect(surface, self.rect)
        if hovered and not disabled:
            _glow_rect(surface, self.rect, self.accent or ACCENT, layers=2)
        pygame.draw.rect(surface, bg,     self.rect, border_radius=BTN_RADIUS)
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=BTN_RADIUS)
        col = (100, 110, 130) if disabled else (C_TEXT if hovered else C_LABEL)
        lbl = self._font.render(self.label, True, col)
        surface.blit(lbl, (self.rect.centerx - lbl.get_width()  // 2,
                            self.rect.centery - lbl.get_height() // 2))

    def is_clicked(self, event: pygame.event.Event,
                   disabled: bool = False) -> bool:
        return (not disabled
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(event.pos))


class Slider:
    def __init__(self, cx: int, cy: int, label: str,
                 vmin: int, vmax: int, value: int) -> None:
        self.cx = cx;  self.cy = cy
        self.label = label
        self.vmin  = vmin;  self.vmax = vmax;  self.value = value
        self.width = 300
        self._track    = pygame.Rect(cx - self.width // 2, cy - 4, self.width, 8)
        self._dragging = False
        self._font  = pygame.font.SysFont("Arial", 18)
        self._lbl_f = pygame.font.SysFont("Arial", 14)

    def _handle_x(self) -> int:
        t = (self.value - self.vmin) / (self.vmax - self.vmin)
        return self._track.left + int(t * self._track.width)

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, (30, 42, 72), self._track, border_radius=4)
        hx = self._handle_x()
        filled = pygame.Rect(self._track.left, self._track.top,
                             hx - self._track.left, 8)
        pygame.draw.rect(surface, ACCENT, filled, border_radius=4)
        pygame.draw.circle(surface, C_BTN_BORDER, (hx, self.cy), 12)
        pygame.draw.circle(surface, ACCENT,       (hx, self.cy),  8)
        lbl = self._lbl_f.render(self.label, True, C_LABEL)
        surface.blit(lbl, (self.cx - self.width // 2, self.cy - 26))
        val = self._font.render(str(self.value), True, C_TEXT)
        surface.blit(val, (self.cx + self.width // 2 + 14,
                           self.cy - val.get_height() // 2))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hx = self._handle_x()
            if math.hypot(event.pos[0] - hx, event.pos[1] - self.cy) < 18:
                self._dragging = True
        elif event.type == pygame.MOUSEBUTTONUP:
            self._dragging = False
        elif event.type == pygame.MOUSEMOTION and self._dragging:
            t = (event.pos[0] - self._track.left) / self._track.width
            self.value = self.vmin + int(max(0.0, min(1.0, t))
                                         * (self.vmax - self.vmin))


class TextInput:
    def __init__(self, cx: int, cy: int, placeholder: str = "") -> None:
        self.rect        = pygame.Rect(cx - 180, cy - 26, 360, 52)
        self.text        = ""
        self.placeholder = placeholder
        self.active      = False
        self.error       = ""   # Phase 11.1: Fehlernachricht
        self._font    = pygame.font.SysFont("Courier", 20, bold=True)
        self._ph_font = pygame.font.SysFont("Arial",   17)
        self._err_f   = pygame.font.SysFont("Arial",   14)

    @staticmethod
    def _get_clipboard() -> str:
        """Get clipboard content (cross-platform attempt)."""
        import subprocess
        import sys
        try:
            if sys.platform == "win32":
                return subprocess.check_output(["powershell", "-Command", "Get-Clipboard"], 
                                               text=True, timeout=1).strip()
            elif sys.platform == "darwin":  # macOS
                return subprocess.check_output(["pbpaste"], text=True, timeout=1).strip()
            else:  # Linux
                try:
                    return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"], 
                                                   text=True, timeout=1).strip()
                except FileNotFoundError:
                    return subprocess.check_output(["xsel", "-b"], 
                                                   text=True, timeout=1).strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            return ""

    @staticmethod
    def _set_clipboard(text: str) -> None:
        """Set clipboard content (cross-platform attempt)."""
        import subprocess
        import sys
        try:
            if sys.platform == "win32":
                subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'"], 
                              timeout=1, check=False)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["pbcopy"], input=text.encode(), timeout=1, check=False)
            else:  # Linux
                try:
                    subprocess.run(["xclip", "-selection", "clipboard"], 
                                  input=text.encode(), timeout=1, check=False)
                except FileNotFoundError:
                    subprocess.run(["xsel", "-b"], input=text.encode(), timeout=1, check=False)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    def draw(self, surface: pygame.Surface) -> None:
        border = (C_ERROR if self.error else
                  (ACCENT if self.active else C_INPUT_BORD))
        _shadow_rect(surface, self.rect, radius=8)
        pygame.draw.rect(surface, C_INPUT_BG, self.rect, border_radius=8)
        pygame.draw.rect(surface, border,     self.rect, 2, border_radius=8)
        if self.active and not self.error:
            _glow_rect(surface, self.rect, ACCENT, layers=1)
        lbl = (self._font.render(self.text, True, C_TEXT) if self.text
               else self._ph_font.render(self.placeholder, True, C_LABEL))
        surface.blit(lbl, (self.rect.x + 14,
                            self.rect.centery - lbl.get_height() // 2))
        if self.active and pygame.time.get_ticks() % 1000 < 500:
            x = (self.rect.x + 14
                 + (self._font.size(self.text)[0] if self.text else 0))
            pygame.draw.line(surface, ACCENT,
                             (x, self.rect.y + 9), (x, self.rect.bottom - 9), 2)
        if self.error:
            err = self._err_f.render(self.error, True, C_ERROR)
            surface.blit(err, (self.rect.x, self.rect.bottom + 6))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            # Phase 12.1: Copy/Paste support (CTRL+C / CTRL+V)
            if event.key == pygame.K_c and (event.mod & pygame.KMOD_CTRL or event.mod & pygame.KMOD_CMD):
                # Copy current text
                self._set_clipboard(self.text)
            elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL or event.mod & pygame.KMOD_CMD):
                # Paste from clipboard
                clipboard = self._get_clipboard()
                # Filter: only keep valid IP characters (0-9, .)
                filtered = "".join(c for c in clipboard if c in "0123456789.")
                available = 15 - len(self.text)
                self.text += filtered[:available]
                self.error = ""
            elif event.key == pygame.K_a and (event.mod & pygame.KMOD_CTRL or event.mod & pygame.KMOD_CMD):
                # Select all (mark but don't implement special visual, just usage)
                pass
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
                self.error = ""
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.active = False
            elif len(self.text) < 15 and event.unicode in "0123456789.":
                self.text  += event.unicode
                self.error  = ""


# ── Klassen-Auswahl-Widget ────────────────────────────────────────────────────

class ClassPicker:
    """
    Drei Fahrzeugklassen als klickbare Glow-Kacheln.

    pvp_mode  = True  → PvP-Layout: Client-Klasse wird als Marker angezeigt
    pvp_mode  = False → Koop/Solo: kein Client-Marker, optionale Info-Zeile darunter
    """
    CLASSES  = list(CAR_CLASSES.keys())
    TILE_W   = 248
    TILE_H   = 118
    TILE_GAP = 20

    def __init__(self, cx: int, cy: int, pvp_mode: bool = True) -> None:
        self.cx       = cx;  self.cy = cy
        self.pvp_mode = pvp_mode
        self.selected = "balanced"
        total_w = (len(self.CLASSES) * self.TILE_W
                   + (len(self.CLASSES) - 1) * self.TILE_GAP)
        x0 = cx - total_w // 2
        self._rects: list[pygame.Rect] = [
            pygame.Rect(x0 + i * (self.TILE_W + self.TILE_GAP),
                        cy - self.TILE_H // 2, self.TILE_W, self.TILE_H)
            for i in range(len(self.CLASSES))
        ]
        self._fn = pygame.font.SysFont("Arial", 20, bold=True)
        self._fi = pygame.font.SysFont("Arial", 26, bold=True)
        self._fd = pygame.font.SysFont("Arial", 12)
        self._fs = pygame.font.SysFont("Arial", 11)
        self._fc = pygame.font.SysFont("Arial", 13)   # coop info

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self._rects):
                if r.collidepoint(event.pos):
                    self.selected = self.CLASSES[i]

    def draw(self, surface: pygame.Surface,
             locked_classes: dict | None = None,
             show_coop_info: bool = False) -> None:
        """
        locked_classes  – {label: class_name} Marker (nur PvP sinnvoll)
        show_coop_info  – zeigt Koop-Hinweis unter den Kacheln (nur Modi 1/2
                          UND Client tatsächlich verbunden)
        In pvp_mode=False: Client-Marker werden komplett unterdrückt.
        """
        for i, cls in enumerate(self.CLASSES):
            r      = self._rects[i]
            active = (cls == self.selected)
            col    = CLASS_COLORS.get(cls, WHITE)

            if active:
                _glow_rect(surface, r, col, layers=3)

            bg = (col[0]//7, col[1]//7, col[2]//7) if active else (10, 14, 26)
            bw = 2 if active else 1
            bc = col if active else (45, 60, 90)
            _shadow_rect(surface, r, radius=10)
            pygame.draw.rect(surface, bg, r, border_radius=10)
            pygame.draw.rect(surface, bc, r, bw, border_radius=10)

            cs   = CAR_CLASSES[cls]
            icon = self._fi.render(CLASS_ICONS.get(cls, "•"), True,
                                   col if active else (60, 75, 100))
            surface.blit(icon, (r.x + 10, r.y + r.h // 2 - icon.get_height() // 2))

            name = self._fn.render(cs["display"], True,
                                   col if active else (90, 110, 150))
            surface.blit(name, (r.x + 54, r.y + 12))

            desc = self._fd.render(CLASS_DESCRIPTIONS[cls], True,
                                   C_LABEL if active else (60, 75, 100))
            surface.blit(desc, (r.x + 54, r.y + 36))

            stats = [
                ("Tempo", cs["speed_mul"],       (0, 195, 100)),
                ("Grip",  cs["grip_mod"] / 2.0,  ACCENT),
                ("Sprit", 1.0 / cs["fuel_mul"],  ACCENT2),
            ]
            for si, (slbl, val, scol) in enumerate(stats):
                bx = r.x + 54 + si * 65;  by = r.y + 60
                sl = self._fs.render(slbl, True,
                                     (130, 145, 170) if active else (50, 60, 80))
                surface.blit(sl, (bx, by))
                bw_full = 58;  bh = 6
                pygame.draw.rect(surface, (20, 25, 40),
                                 (bx, by + 14, bw_full, bh), border_radius=3)
                if active:
                    fill = max(2, int(bw_full * min(1.0, val)))
                    pygame.draw.rect(surface, scol,
                                     (bx, by + 14, fill, bh), border_radius=3)

            # Phase 11.2: Client-Marker nur im PvP-Modus
            if locked_classes and self.pvp_mode:
                for lbl_txt, locked_cls in locked_classes.items():
                    if locked_cls == cls:
                        tag = self._fs.render(f"◄ {lbl_txt}", True,
                                              col if active else GRAY)
                        surface.blit(tag,
                                     (r.x + r.w - tag.get_width() - 8,
                                      r.y + r.h - tag.get_height() - 6))

        # Koop-Info nur wenn Client wirklich verbunden + Koop-Modus
        if show_coop_info and not self.pvp_mode:
            self._draw_coop_info(surface)

    def _draw_coop_info(self, surface: pygame.Surface) -> None:
        y = self.cy + self.TILE_H // 2 + 14
        text = "Koop-Modus  –  Client steuert Gas & Lenkung des gleichen Fahrzeugs"
        lbl  = self._fc.render(text, True, (70, 110, 150))
        surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, y))


# ── Haupt-Menü ────────────────────────────────────────────────────────────────

class MainMenu:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen;  self._t = 0.0
        cx = SCREEN_W // 2
        y0 = SCREEN_H // 2 - 96
        self._title_f = pygame.font.SysFont("Arial", 76, bold=True)
        self._sub_f   = pygame.font.SysFont("Arial", 19)
        self._btn_host     = Button(cx, y0,                       "  START HOST  ",    accent=ACCENT2)
        self._btn_solo     = Button(cx, y0 +   BTN_H + BTN_GAP,   "  SOLO PLAY  ",    accent=GREEN)
        self._btn_client   = Button(cx, y0 + 2*(BTN_H+BTN_GAP),   "  CONNECT CLIENT  ")
        self._btn_settings = Button(cx, y0 + 3*(BTN_H+BTN_GAP),   "  ♪  SETTINGS  ",
                                    w=BTN_W, h=46, accent=(0, 180, 180))
        self._btn_quit     = Button(cx, y0 + 3*(BTN_H+BTN_GAP) + 62,
                                    "  EXIT  ", w=200, h=46, accent=(160, 40, 40))

    def run(self) -> str:
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:                        return "quit"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return "quit"
                if self._btn_host.is_clicked(event):                 return "host"
                if self._btn_solo.is_clicked(event):                 return "solo"
                if self._btn_client.is_clicked(event):               return "client"
                if self._btn_settings.is_clicked(event):             return "settings"
                if self._btn_quit.is_clicked(event):                 return "quit"
            self.screen.fill(MENU_BG);  _draw_bg(self.screen, self._t)
            pygame.draw.line(self.screen, ACCENT,
                             (SCREEN_W//2 - 200, 168), (SCREEN_W//2 + 200, 168), 1)
            _draw_title(self.screen, "PANIC PILOT", 86, self._title_f, ACCENT2)
            sub = self._sub_f.render("Asymmetric Co-op Racing Game", True, C_LABEL)
            self.screen.blit(sub, ((SCREEN_W - sub.get_width()) // 2, 186))
            for btn in (self._btn_host, self._btn_solo,
                        self._btn_client, self._btn_settings, self._btn_quit):
                btn.draw(self.screen, mouse)
            pygame.display.flip()


# ── Solo Klassen-Auswahl ──────────────────────────────────────────────────────

class SoloClassPicker:
    """Phase 11.1: pvp_mode=False, no coop info (no client in solo)."""
    SPEED_OPTIONS = [("🐢  Slow", 0.70), ("🏎  Normal", 1.00), ("⚡  Fast", 1.40)]

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen;  self._t = 0.0
        cx = SCREEN_W // 2
        self._title_f = pygame.font.SysFont("Arial", 38, bold=True)
        # Solo → no PvP, no coop info
        self._picker  = ClassPicker(cx, SCREEN_H // 2 - 50, pvp_mode=False)
        self._slider  = Slider(cx, SCREEN_H // 2 + 108, "Track Length", 10, 50, 15)
        self._speed_idx = 1
        y0 = SCREEN_H // 2 + 176
        self._btn_speed = Button(cx, y0,       "Speed",          w=280, h=46)
        self._btn_start = Button(cx, y0 + 62,  "  START SOLO  ", accent=GREEN)
        self._btn_back  = Button(cx, y0 + 124, "  Back  ",     w=180, h=44)

    def run(self) -> tuple[str, int, float] | None:
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:         return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                self._picker.handle_event(event)
                self._slider.handle_event(event)
                if self._btn_speed.is_clicked(event):
                    self._speed_idx = (self._speed_idx + 1) % len(self.SPEED_OPTIONS)
                if self._btn_start.is_clicked(event):
                    _, scale = self.SPEED_OPTIONS[self._speed_idx]
                    return self._picker.selected, self._slider.value, scale
                if self._btn_back.is_clicked(event):  return None
            self.screen.fill(MENU_BG);  _draw_bg(self.screen, self._t)
            _draw_title(self.screen, "FAHRZEUG WÄHLEN", 52, self._title_f)
            # Solo: show_coop_info immer False
            self._picker.draw(self.screen, show_coop_info=False)
            self._slider.draw(self.screen)
            spd_lbl, _ = self.SPEED_OPTIONS[self._speed_idx]
            orig = self._btn_speed.label
            self._btn_speed.label = f"Tempo: {spd_lbl}"
            self._btn_speed.draw(self.screen, mouse)
            self._btn_speed.label = orig
            self._btn_start.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()


# ── Host Setup ────────────────────────────────────────────────────────────────

class HostSetupMenu:
    SPEED_OPTIONS = [("🐢  Langsam", 0.70), ("🏎  Normal", 1.00), ("⚡  Schnell", 1.40)]

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen;  self._t = 0.0
        self._title_f = pygame.font.SysFont("Arial", 38, bold=True)
        self._lbl_f   = pygame.font.SysFont("Arial", 19)
        self._ip_font = pygame.font.SysFont("Courier", 24, bold=True)
        self._ip_lbl  = pygame.font.SysFont("Arial", 15)
        import socket as _sock
        try:
            with _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80));  self._own_ip = s.getsockname()[0]
        except OSError:
            self._own_ip = _sock.gethostbyname(_sock.gethostname())
        cx = SCREEN_W // 2
        self._slider   = Slider(cx, SCREEN_H//2 - 55, "Streckenlänge (Tiles)", 10, 50, 20)
        self._modes    = [1, 2, 3]
        self._mode_idx = 0
        self._speed_idx = 1
        self._mode_labels = {1: "Split Control  – beide steuern ein Auto",
                             2: "Panic Pilot  – Nebel, Ping-Karte",
                             3: "PvP Racing  – zwei Autos, ein Gewinner"}
        self._mode_colors = {1: (100, 180, 255), 2: ACCENT, 3: ACCENT2}
        y0 = SCREEN_H // 2 + 40
        self._btn_speed = Button(cx, y0,       "Tempo",           w=290, h=50)
        self._btn_mode  = Button(cx, y0 + 64,  "Modus wechseln",  w=290, h=50)
        self._btn_lobby = Button(cx, y0 + 136, "  LOBBY ÖFFNEN  ", accent=ACCENT2)
        self._btn_back  = Button(cx, y0 + 204, "  Zurück  ",      w=180, h=44)

    def run(self, prefill: dict | None = None) -> tuple | None:
        if prefill:
            self._mode_idx  = self._modes.index(prefill.get("mode", 1))
            self._speed_idx = prefill.get("speed_idx", 1)
            self._slider.value = prefill.get("length", 20)
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:         return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                self._slider.handle_event(event)
                if self._btn_speed.is_clicked(event):
                    self._speed_idx = (self._speed_idx + 1) % len(self.SPEED_OPTIONS)
                if self._btn_mode.is_clicked(event):
                    self._mode_idx  = (self._mode_idx  + 1) % len(self._modes)
                if self._btn_lobby.is_clicked(event):
                    _, scale = self.SPEED_OPTIONS[self._speed_idx]
                    return self._modes[self._mode_idx], self._slider.value, scale
                if self._btn_back.is_clicked(event):  return None
            self.screen.fill(MENU_BG);  _draw_bg(self.screen, self._t)
            _draw_title(self.screen, "HOST-EINSTELLUNGEN", 72, self._title_f)
            ip_hint = self._ip_lbl.render("Deine IP (für den Client):", True, C_LABEL)
            ip_val  = self._ip_font.render(f"  {self._own_ip}:54321  ", True, ACCENT)
            box = ip_val.get_rect(center=(SCREEN_W//2, 144))
            _shadow_rect(self.screen, box.inflate(22, 12), radius=8)
            pygame.draw.rect(self.screen, (10, 20, 45), box.inflate(22, 12), border_radius=8)
            pygame.draw.rect(self.screen, C_BTN_BORDER, box.inflate(22, 12), 2, border_radius=8)
            self.screen.blit(ip_hint, ((SCREEN_W - ip_hint.get_width()) // 2, 122))
            self.screen.blit(ip_val, box)
            self._slider.draw(self.screen)
            cur_mode = self._modes[self._mode_idx]
            m_col    = self._mode_colors.get(cur_mode, C_LABEL)
            m_lbl    = self._lbl_f.render(self._mode_labels[cur_mode], True, m_col)
            self.screen.blit(m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, SCREEN_H//2 - 8))
            spd_lbl, _ = self.SPEED_OPTIONS[self._speed_idx]
            orig = self._btn_speed.label
            self._btn_speed.label = f"Tempo: {spd_lbl}"
            self._btn_speed.draw(self.screen, mouse)
            self._btn_speed.label = orig
            self._btn_mode.draw(self.screen, mouse)
            self._btn_lobby.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()


# ── Client IP-Eingabe mit Validierung ─────────────────────────────────────────

class ClientSetupMenu:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen;  self._t = 0.0
        cx = SCREEN_W // 2
        
        # Phase 12.1: Connection history + room discovery
        from connection_history import ConnectionHistory
        from discovery import RoomListener
        
        self._history = ConnectionHistory()
        self._listener = RoomListener()
        self._discovered_rooms: list[dict] = []
        self._listener.start_discovery(timeout=3.0)  # Start finding rooms
        self._last_room_update = 0.0
        
        self._title_f = pygame.font.SysFont("Arial", 38, bold=True)
        self._lbl     = pygame.font.SysFont("Arial", 19)
        self._hint    = pygame.font.SysFont("Arial", 13)
        self._small_f = pygame.font.SysFont("Arial", 14)
        
        self._input   = TextInput(cx, SCREEN_H//2 + 20, "z.B. 192.168.1.42")
        self._input.active = True
        
        self._btn_connect = Button(cx, SCREEN_H//2 + 110, "  VERBINDEN  ", accent=ACCENT)
        self._btn_back    = Button(cx, SCREEN_H//2 + 170, "  Zurück  ", w=180, h=44)
        
        # Recent connections and discovered rooms will be drawn as buttons
        self._recent_rects: list[tuple[pygame.Rect, str]] = []  # (rect, ip)
        self._discovered_rects: list[tuple[pygame.Rect, str]] = []  # (rect, ip)

    def _try_connect(self) -> str | None:
        """Validiert IP und gibt sie zurück oder setzt Fehler und gibt None zurück."""
        ip = self._input.text.strip() or "127.0.0.1"
        if not _validate_ip(ip):
            self._input.error = "Ungültige IP-Adresse (z.B. 192.168.1.42)"
            return None
        # Phase 12.1: Mark as successful in history
        self._history.add_or_update(ip, "Host", success=True)
        return ip
    
    def _update_discovered_rooms(self) -> None:
        """Update list of discovered rooms from listener."""
        if not self._listener.is_listening():
            self._discovered_rooms = self._listener.get_rooms()

    def run(self) -> str | None:
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()
            
            # Periodically check for discovered rooms
            self._last_room_update += dt
            if self._last_room_update > 0.5:
                self._update_discovered_rooms()
                self._last_room_update = 0.0
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:         return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:  return None
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        ip = self._try_connect()
                        if ip: return ip
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # Check recent connections
                    for rect, ip in self._recent_rects:
                        if rect.collidepoint(event.pos):
                            self._input.text = ip
                            self._input.error = ""
                    # Check discovered rooms
                    for rect, ip in self._discovered_rects:
                        if rect.collidepoint(event.pos):
                            self._input.text = ip
                            self._input.error = ""
                
                self._input.handle_event(event)
                if self._btn_connect.is_clicked(event):
                    ip = self._try_connect()
                    if ip: return ip
                if self._btn_back.is_clicked(event):  return None
            
            self.screen.fill(MENU_BG);  _draw_bg(self.screen, self._t)
            _draw_title(self.screen, "CLIENT VERBINDEN", 76, self._title_f)
            
            # Draw history and discovered rooms above input field
            self._draw_connection_options(mouse)
            
            lbl = self._lbl.render("Host-IP-Adresse eingeben:", True, C_LABEL)
            self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H//2 - 48))
            self._input.draw(self.screen)
            h = self._hint.render(
                "Die IP des Hosts steht im Fenster-Titel des Hosts | CTRL+V zum Einfügen", 
                True, C_LABEL)
            self.screen.blit(h, ((SCREEN_W - h.get_width()) // 2, SCREEN_H//2 + 58))
            
            self._btn_connect.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()
    
    def _draw_connection_options(self, mouse: tuple) -> None:
        """Draw recent connections and discovered rooms as clickable options."""
        self._recent_rects.clear()
        self._discovered_rects.clear()
        
        cx = SCREEN_W // 2
        y = 100
        
        # Draw recent connections
        recent = self._history.get_recent(limit=3)
        if recent:
            y_label = y
            lbl = self._lbl.render("Letzte Verbindungen:", True, ACCENT)
            self.screen.blit(lbl, (cx - lbl.get_width() // 2, y_label))
            y += 28
            
            for conn in recent:
                ip = conn["ip"]
                username = conn.get("username", ip)
                
                # Draw as small button
                rect = pygame.Rect(cx - 160, y, 320, 32)
                hovered = rect.collidepoint(mouse)
                
                bg = (40, 60, 100) if hovered else (20, 32, 60)
                border = ACCENT if hovered else (50, 80, 140)
                
                pygame.draw.rect(self.screen, bg, rect, border_radius=6)
                pygame.draw.rect(self.screen, border, rect, 1, border_radius=6)
                
                text = self._small_f.render(f"🌐 {username} ({ip})", True, 
                                           ACCENT if hovered else C_LABEL)
                self.screen.blit(text, (rect.x + 12, rect.centery - text.get_height() // 2))
                
                self._recent_rects.append((rect, ip))
                y += 36
        
        y += 8
        
        # Draw discovered rooms
        if self._discovered_rooms:
            y_label = y
            lbl = self._lbl.render("Gefundene Räume:", True, ACCENT2)
            self.screen.blit(lbl, (cx - lbl.get_width() // 2, y_label))
            y += 28
            
            for room in self._discovered_rooms[:3]:  # Show max 3
                ip = room["ip"]
                room_name = room.get("room_name", "Unknown Room")
                
                # Draw as small button
                rect = pygame.Rect(cx - 160, y, 320, 32)
                hovered = rect.collidepoint(mouse)
                
                bg = (60, 80, 40) if hovered else (30, 40, 20)
                border = ACCENT2 if hovered else (80, 120, 60)
                
                pygame.draw.rect(self.screen, bg, rect, border_radius=6)
                pygame.draw.rect(self.screen, border, rect, 1, border_radius=6)
                
                text = self._small_f.render(f"🎮 {room_name} ({ip})", True, 
                                           ACCENT2 if hovered else C_LABEL)
                self.screen.blit(text, (rect.x + 12, rect.centery - text.get_height() // 2))
                
                self._discovered_rects.append((rect, ip))
                y += 36


# ── HOST LOBBY ────────────────────────────────────────────────────────────────

class HostLobby:
    """
    Persistente Lobby.
    Phase 11.1:
     • _lobby_timer startet bei 999 → sofortiger Broadcast beim ersten Frame
     • client_requests_state() → sofortiger Snapshot unabhängig vom Timer
     • _client_handshaked: erst True wenn erstes lobby_client-Paket ankam
     • show_coop_info: nur bei Koop + handshaked Client
    """
    NET_PORT      = 54321
    LOBBY_SEND_HZ = 10

    def __init__(self, screen: pygame.Surface, mode: int,
                 length: int, speed_scale: float,
                 net=None) -> None:
        self.screen      = screen
        self.mode        = mode
        self.length      = length
        self.speed_scale = speed_scale
        self._t          = 0.0

        if net is not None:
            self._net      = net
            self._owns_net = False
        else:
            from net import HostConnection
            self._net      = HostConnection(self.NET_PORT)
            self._net.start()
            self._owns_net = True

        # Phase 12.1: Start room discovery broadcaster
        from discovery import RoomBroadcaster
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                own_ip = s.getsockname()[0]
        except OSError:
            own_ip = "localhost"
        
        room_name = f"Host ({own_ip})"
        self._broadcaster = RoomBroadcaster(room_name, tcp_port=self.NET_PORT)
        self._broadcaster.start()

        cx = SCREEN_W // 2
        self._title_f  = pygame.font.SysFont("Arial", 38, bold=True)
        self._lbl_f    = pygame.font.SysFont("Arial", 17)
        self._status_f = pygame.font.SysFont("Arial", 14, bold=True)
        self._hint_f   = pygame.font.SysFont("Arial", 13)

        pvp = (mode == 3)
        # Phase 11.2: Picker immer zentriert; pvp_mode steuert nur Marker-Anzeige
        self._picker = ClassPicker(cx, SCREEN_H // 2 - 30, pvp_mode=pvp)
        self._client_class: str | None = None
        self._client_handshaked = False
        self._lobby_timer = 999.0

        y0 = SCREEN_H // 2 + 126
        self._btn_start    = Button(cx, y0,       "  RENNEN STARTEN  ",  accent=(50, 200, 80))
        self._btn_kick     = Button(cx, y0 + 66,  "  CLIENT KICKEN  ",   w=240, h=46, accent=(200, 60, 60))
        self._btn_settings = Button(cx, y0 + 126, "  Einstellungen  ",   w=240, h=44)
        self._btn_back     = Button(cx, y0 + 186, "  Hauptmenü  ",       w=220, h=44)

    # ── Haupt-Loop ────────────────────────────────────────────────────────────

    def run(self) -> str:
        """Gibt "back" oder "settings" zurück."""
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._close(); return "back"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._close(); return "back"
                self._picker.handle_event(event)
                if self._btn_start.is_clicked(event,
                                              disabled=not self._client_handshaked
                                              and self.mode == 3):
                    outcome = self._run_game()
                    if outcome == "settings": return "settings"
                if self._btn_kick.is_clicked(event) and self._net.is_connected():
                    self._net.send_kick()
                    self._client_class     = None
                    self._client_handshaked = False
                if self._btn_settings.is_clicked(event):
                    return "settings"   # Netz bleibt am Leben
                if self._btn_back.is_clicked(event):
                    self._close(); return "back"

            # ── Client-Lobby-Update ───────────────────────────────────────────
            cl = self._net.get_client_lobby()
            if cl:
                self._client_class      = cl.get("car_class", "balanced")
                self._client_handshaked = True   # erster Datenaustausch bestätigt

            if self._net.client_left():
                self._client_class      = None
                self._client_handshaked = False

            # ── Phase 11.1: Sofort-Antwort auf request_lobby_state ───────────
            if self._net.client_requests_state():
                self._send_lobby_packet()
                self._lobby_timer = 0.0   # Timer zurücksetzen

            # ── Regulärer Broadcast-Timer ─────────────────────────────────────
            self._lobby_timer += dt
            if self._lobby_timer >= 1.0 / self.LOBBY_SEND_HZ:
                self._lobby_timer = 0.0
                self._send_lobby_packet()

            self._draw(mouse)

    def _send_lobby_packet(self) -> None:
        """Baut das vollständige Lobby-Paket und sendet es (wenn verbunden)."""
        if self._net.is_connected():
            self._net.send_lobby({
                "host_class":  self._picker.selected,
                "mode":        self.mode,
                "length":      self.length,
                "speed_scale": self.speed_scale,
                "status":      "lobby",
            })

    def _run_game(self) -> str:
        from host  import HostGame
        from track import Track

        generated  = Track.generate(length=self.length)
        map_data   = {**generated.to_dict(), "game_mode": self.mode}
        client_cls = self._client_class or "balanced"
        pvp        = (self.mode == 3)
        start_pkt  = {
            "host_class":   self._picker.selected,
            "client_class": client_cls,
        }

        # ── Phase 11.3: Schritt 1 – Start wiederholt senden ─────────────────
        # Alle 100 ms neu senden bis Client "ready_for_map" schickt oder 2s um.
        # Für Solo/Koop (nicht PvP): einmal senden genügt.
        if pvp and self._net.is_connected():
            RETRY_INTERVAL = 0.10   # 100 ms
            READY_TIMEOUT  = 2.0
            deadline       = time.time() + READY_TIMEOUT
            ready          = False
            next_send      = 0.0
            print("DEBUG: Host startet Start-Retry-Loop …")
            while time.time() < deadline:
                if time.time() >= next_send:
                    self._net.send_start(start_pkt)
                    print(f"DEBUG: Host sendet start-Paket "
                          f"({READY_TIMEOUT - (deadline - time.time()):.1f}s)")
                    next_send = time.time() + RETRY_INTERVAL
                if self._net.client_ready_for_map():
                    ready = True
                    print("DEBUG: Host empfängt ready_for_map → sende Karte")
                    break
                self._draw_waiting_for_ready()
                pygame.time.wait(10)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self._close(); return "back"
            if not ready:
                print("DEBUG: Host-Timeout – sende Karte ohne Bestätigung")
        else:
            # Koop / Solo: ein Start-Paket reicht
            self._net.send_start(start_pkt)
            print("DEBUG: Host sendet start (Koop/Solo)")

        # ── Phase 11.3: Schritt 2 – Karte senden, dann Flags resetten ───────
        print("DEBUG: Host sendet Karte")
        self._net.send_map(map_data)

        # Erst jetzt sicher resetten – Karte ist raus, Client-Inbox ist egal
        self._net.reset_lobby_flags()

        # ── Spiel starten ─────────────────────────────────────────────────────
        game = HostGame(
            mode             = self.mode,
            track_length     = self.length,
            speed_scale      = self.speed_scale,
            net              = self._net,
            car_class_host   = self._picker.selected,
            car_class_client = client_cls,
        )
        game._generated_track = generated
        game._init_game_objects(track=generated)
        game.run()

        # Zurück in Lobby: Sofort-Broadcast + State zurücksetzen
        self._lobby_timer       = 999.0
        self._client_handshaked = False
        print("DEBUG: Host zurück in Lobby")
        return "settings" if getattr(game, "_return_to_settings", False) else "back"

    def _draw_waiting_for_ready(self) -> None:
        """Kurzer Ladescreen während Host auf ready_for_map wartet."""
        self.screen.fill(MENU_BG)
        f = pygame.font.SysFont("Arial", 26, bold=True)
        t = f.render("Warte auf Client-Bereitschaft …", True, ACCENT)
        self.screen.blit(t, ((SCREEN_W - t.get_width())  // 2,
                              (SCREEN_H - t.get_height()) // 2))
        s = pygame.font.SysFont("Arial", 16).render(
            "Verbindung wird aufgebaut …", True, C_LABEL)
        self.screen.blit(s, ((SCREEN_W - s.get_width()) // 2,
                              SCREEN_H // 2 + 40))
        pygame.display.flip()

    def _close(self) -> None:
        # Phase 12.1: Stop room discovery broadcaster
        if hasattr(self, "_broadcaster"):
            self._broadcaster.stop()
        if self._owns_net:
            self._net.shutdown()

    def _draw(self, mouse: tuple) -> None:
        self.screen.fill(MENU_BG);  _draw_bg(self.screen, self._t)
        _draw_title(self.screen, "HOST LOBBY", 42, self._title_f, ACCENT2)

        modes_lbl = {1: "Split Control", 2: "Panic Pilot (Fog)", 3: "PvP Racing"}
        modes_col = {1: (100, 180, 255), 2: ACCENT, 3: ACCENT2}
        info_col  = modes_col.get(self.mode, C_LABEL)
        info = self._lbl_f.render(
            f"Modus: {modes_lbl.get(self.mode,'?')}   •   "
            f"Strecke: {self.length} Tiles", True, info_col)
        self.screen.blit(info, ((SCREEN_W - info.get_width()) // 2, 94))

        # Phase 11.2: locked_classes & coop_info korrekt nach Modus
        pvp       = (self.mode == 3)
        locked    = ({"Client": self._client_class}
                     if pvp and self._client_handshaked and self._client_class
                     else {})
        coop_info = (not pvp and self._client_handshaked)
        self._picker.pvp_mode = pvp   # live aktualisieren
        self._picker.draw(self.screen,
                          locked_classes=locked,
                          show_coop_info=coop_info)

        # Status-Zeile – unterscheidet TCP-offen vs. vollständig handshaked
        if self._client_handshaked:
            st, sc = "● NAVIGATOR VERBUNDEN & BEREIT", (50, 210, 100)
        elif self._net.is_connected():
            st, sc = "◌ TCP verbunden – warte auf Handshake …", (180, 180, 60)
        else:
            st, sc = f"○ Warte auf Navigator …   Port {self.NET_PORT}", ORANGE
        status = self._status_f.render(st, True, sc)
        self.screen.blit(status, ((SCREEN_W - status.get_width()) // 2,
                                   SCREEN_H // 2 + 92))

        # Start-Button: Modi 1+2 immer erlaubt (Solo/Koop); Modus 3 nur mit Client
        start_disabled = (pvp and not self._client_handshaked)
        self._btn_start.draw(self.screen, mouse, disabled=start_disabled)
        self._btn_kick.draw(self.screen, mouse, disabled=not self._net.is_connected())
        self._btn_settings.draw(self.screen, mouse)
        self._btn_back.draw(self.screen, mouse)

        for i, h in enumerate([
            "Klasse wählen → RENNEN STARTEN",
            "ESC = Hauptmenü   •   Settings behält Verbindung",
        ]):
            hl = self._hint_f.render(h, True, (60, 80, 110))
            self.screen.blit(hl, ((SCREEN_W - hl.get_width()) // 2,
                                   SCREEN_H - 44 + i * 18))
        pygame.display.flip()


# ── CLIENT LOBBY ──────────────────────────────────────────────────────────────

class ClientLobby:
    """
    Phase 11.1:
     • Zeigt "Handshake läuft…" bis erster lobby_host-Snapshot eintrifft
     • Sendet request_lobby_state beim ersten Frame der Lobby-Loop
     • Zeigt Modus/Länge/Tempo aus host_info sofort korrekt an
     • pvp_mode des Pickers wird dynamisch aus host_mode aktualisiert
    """
    NET_PORT        = 54321
    CONNECT_TIMEOUT = 5.0
    LOBBY_SEND_HZ   = 10

    def __init__(self, screen: pygame.Surface, host_ip: str) -> None:
        self.screen   = screen
        self.host_ip  = host_ip
        self._t       = 0.0

        from net import ClientConnection
        self._net            = ClientConnection(host_ip, self.NET_PORT)
        self._connected      = False
        self._host_info: dict = {}
        self._lobby_timer    = 0.0
        self._last_update    = 0.0
        self._initial_sent   = False   # Phase 11.1: request einmalig senden

        cx = SCREEN_W // 2
        self._title_f  = pygame.font.SysFont("Arial", 38, bold=True)
        self._lbl_f    = pygame.font.SysFont("Arial", 17)
        self._status_f = pygame.font.SysFont("Arial", 14, bold=True)
        self._hint_f   = pygame.font.SysFont("Arial", 13)
        # Picker startet als PvP; wird sofort nach erstem host_info aktualisiert
        self._picker   = ClassPicker(cx, SCREEN_H // 2 - 30, pvp_mode=True)
        y0 = SCREEN_H // 2 + 134
        self._btn_back = Button(cx, y0, "  Verlassen (ESC)  ",
                                w=270, h=46, accent=(200, 60, 60))

    def run(self) -> None:
        clock = pygame.time.Clock()
        self._draw_status(f"Verbinde mit {self.host_ip} …", WHITE)
        if not self._net.connect(timeout=self.CONNECT_TIMEOUT):
            self._draw_status("Verbindung fehlgeschlagen.", RED)
            pygame.time.wait(2500)
            return
        self._connected = True

        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._leave(); return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._leave(); return
                self._picker.handle_event(event)
                if self._btn_back.is_clicked(event):
                    self._leave(); return

            if not self._net.is_connected():
                self._draw_status("Verbindung getrennt.", RED)
                pygame.time.wait(2000); return

            if self._net.was_kicked():
                # Phase 12.2: Kick handling - interruptible with ESC
                kick_start = pygame.time.get_ticks()
                kick_duration = 2000  # 2 seconds
                while pygame.time.get_ticks() - kick_start < kick_duration:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            self._leave(); return
                        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                            self._leave(); return
                    self._draw_status("Du wurdest vom Host gekickt.", ORANGE)
                    pygame.time.wait(100)
                self._leave(); return

            # Phase 11.1: im ersten Frame nochmal lobby anfordern
            # (request_lobby_state wurde schon in connect() gesendet,
            # aber erst hier sendet der Client auch seine Klasse)
            if not self._initial_sent:
                self._initial_sent = True
                self._net.send_lobby({"car_class": self._picker.selected})

            # Host-Lobby-Info empfangen
            hl = self._net.get_host_lobby()
            if hl:
                self._host_info   = hl
                self._last_update = self._t
                # Picker-Modus sofort aktualisieren
                host_mode = int(hl.get("mode", 3))
                self._picker.pvp_mode = (host_mode == 3)

            # Start-Signal – Phase 11.3: ready_for_map SOFORT senden, BEVOR ClientGame gebaut wird
            start = self._net.get_start()
            if start:
                print("DEBUG: Client empfängt start-Paket – sende ready_for_map")
                # Dreimal senden für Zuverlässigkeit (idempotent beim Host)
                for _ in range(3):
                    try: self._net.send_ready_for_map()
                    except Exception: pass
                    pygame.time.wait(30)
                print("DEBUG: Client ruft _run_game()")
                self._run_game(start)
                if not self._net.is_connected(): return
                # Zustand vollständig zurücksetzen
                self._host_info    = {}
                self._last_update  = 0.0
                self._initial_sent = False
                self._lobby_timer  = 0.0
                try: self._net.send_request_lobby_state()
                except Exception: pass
                print("DEBUG: Client zurück in Lobby")
                continue

            # Regulärer Klassen-Broadcast
            self._lobby_timer += dt
            if self._lobby_timer >= 1.0 / self.LOBBY_SEND_HZ:
                self._lobby_timer = 0.0
                self._net.send_lobby({"car_class": self._picker.selected})

            self._draw_lobby(mouse)

    def _run_game(self, start_data: dict) -> None:
        """
        Phase 11.3: ready_for_map wurde bereits vor diesem Aufruf gesendet
        (3× in der Lobby-Loop). Hier nur noch ClientGame starten.
        KEIN reset_lobby_flags() VOR dem Spiel – die Karte ist möglicherweise
        schon in _map_inbox und würde gelöscht.
        """
        from client import ClientGame
        print("DEBUG: ClientLobby erstellt ClientGame …")
        game = ClientGame(
            host_ip          = self.host_ip,
            net              = self._net,
            car_class_host   = start_data.get("host_class",   "balanced"),
            car_class_client = self._picker.selected,
        )
        # Phase 11.3: Signalisiert _connect_loop dass ready_for_map schon gesendet
        game._lobby_ready_sent = True
        print("DEBUG: ClientGame.run() startet")
        game.run()
        print("DEBUG: ClientGame.run() beendet, return_to_lobby =",
              getattr(game, "_return_to_lobby", False))
        # Flags NACH dem Spiel zurücksetzen
        if self._net.is_connected():
            self._net.reset_lobby_flags()

    def _leave(self) -> None:
        if self._connected:
            try: self._net.send_leave()
            except Exception: pass
        self._net.shutdown()

    def _draw_status(self, msg: str, color: tuple) -> None:
        self.screen.fill(MENU_BG)
        f = pygame.font.SysFont("Arial", 28, bold=True)
        t = f.render(msg, True, color)
        self.screen.blit(t, ((SCREEN_W - t.get_width())  // 2,
                              (SCREEN_H - t.get_height()) // 2))
        pygame.display.flip()

    def _draw_lobby(self, mouse: tuple) -> None:
        self.screen.fill(MENU_BG);  _draw_bg(self.screen, self._t)
        _draw_title(self.screen, "CLIENT LOBBY", 42, self._title_f, ACCENT)

        # ── Info-Zeile mit Echtzeit-Settings vom Host ─────────────────────────
        host_cls   = self._host_info.get("host_class", "")
        mode_raw   = self._host_info.get("mode", None)
        length_raw = self._host_info.get("length", None)
        speed_raw  = self._host_info.get("speed_scale", None)

        handshaked = bool(self._host_info)   # True sobald erster Snapshot da

        modes_lbl  = {1: "Split Control", 2: "Panic Pilot", 3: "PvP Racing"}
        speed_lbl  = {0.70: "Langsam", 1.00: "Normal", 1.40: "Schnell"}
        # Nächsten Treffer für speed_scale suchen
        spd_text = "–"
        if speed_raw is not None:
            key = min(speed_lbl.keys(), key=lambda k: abs(k - float(speed_raw)))
            spd_text = speed_lbl.get(key, f"{speed_raw:.1f}x")

        if handshaked:
            info_parts = []
            if mode_raw is not None:
                info_parts.append(f"Modus: {modes_lbl.get(int(mode_raw),'?')}")
            if length_raw is not None:
                info_parts.append(f"Strecke: {length_raw} Tiles")
            info_parts.append(f"Tempo: {spd_text}")
            info_str = "   •   ".join(info_parts)
            info_col = ACCENT2
        else:
            info_str = "Warte auf Host-Daten …"
            info_col = (100, 100, 100)

        info = self._lbl_f.render(info_str, True, info_col)
        self.screen.blit(info, ((SCREEN_W - info.get_width()) // 2, 94))

        # ── Klassen-Picker ─────────────────────────────────────────────────────
        locked = ({"Host": host_cls}
                  if handshaked and host_cls and self._picker.pvp_mode
                  else {})
        self._picker.draw(self.screen,
                          locked_classes=locked,
                          show_coop_info=False)  # Client zeigt keine Coop-Box

        # ── Verbindungsstatus ─────────────────────────────────────────────────
        since = self._t - self._last_update
        if not handshaked:
            st, sc = "◌ Handshake läuft – warte auf Host-Daten …", (180, 180, 60)
        elif since > 3.0:
            st, sc = "● Verbunden  –  Host konfiguriert Einstellungen …", (180, 180, 80)
        else:
            st, sc = f"● Verbunden mit {self.host_ip}  –  Warte auf Start …", (50, 210, 100)
        status = self._status_f.render(st, True, sc)
        self.screen.blit(status, ((SCREEN_W - status.get_width()) // 2,
                                   SCREEN_H // 2 + 96))

        self._btn_back.draw(self.screen, mouse)
        h = self._hint_f.render(
            "Klasse wählen – Host startet das Rennen   •   ESC = Verlassen",
            True, (60, 80, 110))
        self.screen.blit(h, ((SCREEN_W - h.get_width()) // 2, SCREEN_H - 34))
        pygame.display.flip()


# ── Solo-Spiel starten ────────────────────────────────────────────────────────

def _run_solo(screen: pygame.Surface,
              car_class: str, length: int, speed_scale: float) -> None:
    from game  import Game
    from track import Track
    import camera as _cam
    track = Track.generate(length=length)
    game  = Game.__new__(Game)
    game.screen            = screen
    game.clock             = pygame.time.Clock()
    game.running           = True
    game.mode              = 1
    game.pings             = []
    game._return_to_menu   = False
    game._return_to_lobby  = False
    game._lobby_initiator  = ""
    game._paused           = False
    game._pause_btn_rects  = {}
    game.speed_scale       = speed_scale
    game._locked_class0    = car_class
    game._locked_class1    = "balanced"
    game._warn_font        = pygame.font.SysFont("Arial", 18, bold=True)
    game._countdown_font   = pygame.font.SysFont("Arial", 160, bold=True)
    game._win_font         = pygame.font.SysFont("Arial", 72, bold=True)
    game._sub_font         = pygame.font.SysFont("Arial", 28, bold=True)
    game._pause_font       = pygame.font.SysFont("Arial", 80, bold=True)
    game._flash_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    game._fog_surf   = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    game.camera = _cam.Camera()
    game._init_game_objects(track=track)
    pygame.display.set_caption("Panic Pilot – SOLO  |  ESC/P=Pause  R=Reset")
    game.run()


# ── Phase 12: Audio-Einstellungen ─────────────────────────────────────────────

class SettingsScene:
    """
    Zeigt zwei Lautstärke-Schieberegler:
      • Musik-Lautstärke
      • Effekt-Lautstärke

    Werte werden sofort an den SoundManager weitergeleitet und in
    settings.py (MUSIC_VOLUME / SFX_VOLUME) gespeichert, damit sie
    in der gesamten Sitzung global gültig bleiben.
    """

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen   = screen
        self._t       = 0.0
        cx            = SCREEN_W // 2
        self._title_f = pygame.font.SysFont("Arial", 38, bold=True)
        self._hint_f  = pygame.font.SysFont("Arial", 14)
        self._sub_f   = pygame.font.SysFont("Arial", 17)

        import settings as _s
        init_music = getattr(_s, "MUSIC_VOLUME", 70)
        init_sfx   = getattr(_s, "SFX_VOLUME",   80)

        self._sl_music = Slider(cx, SCREEN_H // 2 - 56,
                                "♪  Musik-Lautstärke", 0, 100, init_music)
        self._sl_sfx   = Slider(cx, SCREEN_H // 2 + 24,
                                "★  Effekt-Lautstärke", 0, 100, init_sfx)

        self._btn_test  = Button(cx, SCREEN_H // 2 + 110,
                                 "  Testton abspielen  ", w=280, h=46,
                                 accent=(0, 195, 100))
        self._btn_back  = Button(cx, SCREEN_H // 2 + 178,
                                 "  Zurück  ", w=200, h=44)
        self._test_hint = ""
        self._test_t    = 0.0

    # ── Lautstärken live an SoundManager weitergeben ─────────────────────────

    def _apply_volumes(self) -> None:
        if _sound_mod is None:
            return
        sm = _sound_mod.get()
        sm.set_music_volume(self._sl_music.value)
        sm.set_sfx_volume(self._sl_sfx.value)
        # Persistenz in settings-Modul
        import settings as _s
        _s.MUSIC_VOLUME = self._sl_music.value
        _s.SFX_VOLUME   = self._sl_sfx.value

    # ── Haupt-Loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0
            self._t     += dt
            self._test_t = max(0.0, self._test_t - dt)
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return
                self._sl_music.handle_event(event)
                self._sl_sfx.handle_event(event)
                # Volumes live anwenden beim Ziehen
                if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
                    self._apply_volumes()
                if self._btn_test.is_clicked(event):
                    self._apply_volumes()
                    if _sound_mod:
                        _sound_mod.get().play_pickup_fuel()
                    self._test_hint = "▶ Testton …"
                    self._test_t    = 1.2
                if self._btn_back.is_clicked(event):
                    self._apply_volumes()
                    return

            self._draw(mouse)

    def _draw(self, mouse: tuple) -> None:
        self.screen.fill(MENU_BG)
        _draw_bg(self.screen, self._t)
        _draw_title(self.screen, "AUDIO-EINSTELLUNGEN", 72, self._title_f)

        # Info-Text
        info = self._sub_f.render(
            "Änderungen werden sofort übernommen", True, C_LABEL)
        self.screen.blit(info, ((SCREEN_W - info.get_width()) // 2, 126))

        # Trennlinie
        pygame.draw.line(self.screen, (30, 50, 80),
                         (SCREEN_W // 2 - 260, 154),
                         (SCREEN_W // 2 + 260, 154), 1)

        self._sl_music.draw(self.screen)
        self._sl_sfx.draw(self.screen)

        # Sound-Quelle-Hinweis
        if _sound_mod is not None:
            src_txt = "✓ Audio-System aktiv (prozedural generierte Sounds)"
            src_col = (60, 200, 100)
        else:
            src_txt = "✗ Audio-System nicht verfügbar"
            src_col = (200, 70, 50)
        src = self._hint_f.render(src_txt, True, src_col)
        self.screen.blit(src, ((SCREEN_W - src.get_width()) // 2,
                                SCREEN_H // 2 + 68))

        self._btn_test.draw(self.screen, mouse)
        self._btn_back.draw(self.screen, mouse)

        if self._test_hint and self._test_t > 0:
            th = self._hint_f.render(self._test_hint, True, (0, 200, 100))
            self.screen.blit(th, (SCREEN_W // 2 + 155,
                                   SCREEN_H // 2 + 121))

        # Dateipfad-Hinweis
        hints = [
            "Eigene Sounds: assets/sounds/  (music_menu.ogg, music_race.ogg, …)",
            "Fehlende Dateien werden automatisch prozedural ersetzt.",
        ]
        for i, h in enumerate(hints):
            hl = self._hint_f.render(h, True, (50, 70, 100))
            self.screen.blit(hl, ((SCREEN_W - hl.get_width()) // 2,
                                   SCREEN_H - 52 + i * 18))

        pygame.display.flip()


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

def main() -> None:
    pygame.init()
    # Phase 12.2: Fullscreen support
    flags = pygame.FULLSCREEN if FULLSCREEN else 0
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
    pygame.display.set_caption("Panic Pilot")

    # ── Phase 12: Audio-System initialisieren ─────────────────────────────────
    _sm = None
    if _sound_mod is not None:
        _sm = _sound_mod.get()
        import settings as _s
        _sm.set_music_volume(getattr(_s, "MUSIC_VOLUME", 70))
        _sm.set_sfx_volume(getattr(_s, "SFX_VOLUME", 80))
        _sm.play_music("menu")

    last_host_settings: dict | None = None

    while True:
        # Menü-Musik starten (nach Rückkehr aus dem Spiel)
        if _sm:
            _sm.play_music("menu")

        choice = MainMenu(screen).run()

        if choice == "quit":
            break

        elif choice == "settings":
            SettingsScene(screen).run()

        elif choice == "solo":
            result = SoloClassPicker(screen).run()
            if result is not None:
                car_class, length, speed_scale = result
                if _sm: _sm.play_music("race")
                _run_solo(screen, car_class, length, speed_scale)
                if _sm: _sm.engine_stop()

        elif choice == "host":
            settings = HostSetupMenu(screen)
            result   = settings.run(prefill=last_host_settings)
            if result is None:
                continue
            mode, length, speed_scale = result
            last_host_settings = {
                "mode": mode, "length": length,
                "speed_idx": settings._speed_idx,
            }
            # ── Phase 11.1: Lobby-Settings-Schleife mit persistentem Netz ────
            existing_net = None
            while True:
                if _sm: _sm.play_music("menu")
                lobby   = HostLobby(screen, mode, length, speed_scale,
                                    net=existing_net)
                outcome = lobby.run()

                if outcome == "settings":
                    # Netz bleibt am Leben – Client wartet in seiner Lobby
                    existing_net = lobby._net
                    result2 = HostSetupMenu(screen).run(
                        prefill={"mode": mode, "length": length,
                                 "speed_idx": last_host_settings.get("speed_idx", 1)})
                    if result2 is None:
                        continue
                    mode, length, speed_scale = result2
                    last_host_settings = {"mode": mode, "length": length}
                    continue

                existing_net = None
                break   # "back" → Hauptmenü
            if _sm: _sm.engine_stop()

        elif choice == "client":
            host_ip = ClientSetupMenu(screen).run()
            if host_ip is not None:
                if _sm: _sm.play_music("menu")
                ClientLobby(screen, host_ip).run()
                if _sm: _sm.engine_stop()

    if _sm:
        _sm.shutdown()
    pygame.quit()


if __name__ == "__main__":
    main()
