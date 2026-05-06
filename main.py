# =============================================================================
#  main.py  –  Panic Pilot | Phase 11.2: Stability Fix & UI Strictness
# =============================================================================
#
#  Changes from Phase 11.1:
#   1. 3-Way Handshake – Host sends "start" → Client replies "ready_for_map"
#                         → Host sends the map only then (timeout 0.5 s)
#   2. Map Timeout      – Client waits max 5 s for map data, then returns to lobby
#   3. Flag Reset       – reset_lobby_flags() before/after each game on both sides
#   4. UI Strictness    – Modes 1/2: no client marker in picker; only host chooses
#                          Mode 3: full PvP picker with client marker
#   5. Coop Info Box    – appears only when client is actually handshaked
#   1. IP Validation  – 4-block 0–255 check before connect, Errno-8 protection
#   2. Handshake Sync  – Client sends request_lobby_state right after TCP
#                        connect; host replies immediately; client shows "Connected"
#                        only when the first lobby_host snapshot arrives
#   3. Real-time Settings – HostLobby sets _lobby_timer=999 for instant
#                           broadcast; after returning from settings, sends directly
#   4. Mode-dependent Picker – Modes 1/2: centered picker without coop box
#                               (box only when client is actually handshaked);
#                               Mode 3: full PvP picker with client marker
#   5. HUD Fix – Client shows "?" only while no snapshot available; then falls back
#                to correct values
# =============================================================================
from __future__ import annotations
import math
import os
import random
import time
import string
import pygame

from settings import *

# Phase 12: Audio system
try:
    import sound_manager as _sound_mod
except Exception:
    _sound_mod = None

# ── UI Color and Layout Constants ──────────────────────────────────────────────
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


def _set_display_mode(fullscreen: bool) -> pygame.Surface:
    import settings as _s
    if fullscreen:
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
    return pygame.display.set_mode((w, h), flags)


def _handle_global_key(event: "pygame.event.Event") -> bool:
    """Handle global keys. Returns True if the event was consumed."""
    return False

CLASS_COLORS = {
    "balanced":  (210,  45,  45),
    "speedster": (255, 140,   0),
    "tank":      ( 50, 175,  55),
}


def _draw_class_icon(surface: pygame.Surface, cls: str, rect: pygame.Rect, color: tuple) -> None:
    """Draw a detailed geometric icon for the class without relying on system fonts."""
    cx, cy = rect.centerx, rect.centery
    w, h = rect.width, rect.height
    if cls == "balanced":
        # Diamond with inner cross and corner dots
        pts = [(cx, cy - h//3), (cx + w//3, cy), (cx, cy + h//3), (cx - w//3, cy)]
        pygame.draw.polygon(surface, color, pts, 2)
        pygame.draw.line(surface, color, (cx, cy - h//4), (cx, cy + h//4), 2)
        pygame.draw.line(surface, color, (cx - w//5, cy), (cx + w//5, cy), 2)
        pygame.draw.circle(surface, color, (cx, cy), 3)
        for dx, dy in [(-w//3, -h//3), (w//3, -h//3), (-w//3, h//3), (w//3, h//3)]:
            pygame.draw.circle(surface, color, (cx + dx//2, cy + dy//2), 1)
    elif cls == "speedster":
        # Triple chevron arrows with trail lines
        for i in range(3):
            offset = (i - 1) * 10
            pts = [(cx + offset - 4, cy - h//3),
                   (cx + offset + w//3, cy),
                   (cx + offset - 4, cy + h//3)]
            pygame.draw.polygon(surface, color, pts, 2 if i == 1 else 1)
        pygame.draw.line(surface, color, (cx - w//3, cy - h//4), (cx - w//3 - 6, cy - h//4), 1)
        pygame.draw.line(surface, color, (cx - w//3, cy + h//4), (cx - w//3 - 6, cy + h//4), 1)
    elif cls == "tank":
        # Shield shape with inner diamond and bolts
        pts = [(cx - w//3, cy - h//3),
               (cx + w//3, cy - h//3),
               (cx + w//3, cy + h//6),
               (cx, cy + h//3),
               (cx - w//3, cy + h//6)]
        pygame.draw.polygon(surface, color, pts, 2)
        inner = [(cx, cy - h//5), (cx + w//5, cy), (cx, cy + h//5), (cx - w//5, cy)]
        pygame.draw.polygon(surface, color, inner, 1)
        for bx, by in [(cx - w//3, cy - h//3), (cx + w//3, cy - h//3)]:
            pygame.draw.circle(surface, color, (bx, by), 2)
    else:
        pygame.draw.circle(surface, color, (cx, cy), 8, 2)
CLASS_DESCRIPTIONS = {
    "balanced":  "Balanced  -  Good grip, normal speed",
    "speedster": "Speedy  -  High speed, slippery & thirsty",
    "tank":      "Tank  -  Slow but sturdy, off-road king",
}


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_ip(ip: str) -> bool:
    """Checks if ip is a valid IPv4 address (0.0.0.0 - 255.255.255.255)."""
    if ip == "localhost":
        return True
    parts = ip.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


# ── Drawing Helpers ───────────────────────────────────────────────────────────

def _draw_bg(surface: pygame.Surface, t: float = 0.0) -> None:
    col = (20, 34, 54)
    for i in range(0, SCREEN_W, 120):
        pygame.draw.line(surface, col, (i, 0), (i, SCREEN_H))
    for i in range(0, SCREEN_H, 120):
        pygame.draw.line(surface, col, (0, i), (SCREEN_W, i))


class _Particle:
    def __init__(self) -> None:
        self.reset()
        self.y = random.uniform(0, SCREEN_H)
    def reset(self) -> None:
        self.x = random.uniform(0, SCREEN_W)
        self.y = SCREEN_H + 10
        self.speed = random.uniform(15, 40)
        self.size = random.uniform(1, 3)
        self.alpha = random.randint(30, 80)
        self.drift = random.uniform(-8, 8)
    def update(self, dt: float) -> None:
        self.y -= self.speed * dt
        self.x += self.drift * dt
        if self.y < -10:
            self.reset()
    def draw(self, surface: pygame.Surface, color: tuple) -> None:
        s = pygame.Surface((int(self.size * 2), int(self.size * 2)), pygame.SRCALPHA)
        c = (*color, self.alpha)
        pygame.draw.circle(s, c, (int(self.size), int(self.size)), int(self.size))
        surface.blit(s, (int(self.x), int(self.y)))


_particles: list[_Particle] | None = None

def _draw_animated_bg(surface: pygame.Surface, t: float,
                      count: int = 35, color: tuple = ACCENT) -> None:
    global _particles
    if _particles is None or len(_particles) != count:
        _particles = [_Particle() for _ in range(count)]
    _draw_bg(surface, t)
    dt = 1 / 60.0
    for p in _particles:
        p.update(dt)
        p.draw(surface, color)


def _draw_title(surface: pygame.Surface, text: str, y: int,
                font: pygame.font.Font,
                color: tuple = (255, 215, 0)) -> None:
    shd = font.render(text, True, (0, 0, 0))
    surface.blit(shd, ((SCREEN_W - shd.get_width()) // 2 + 3, y + 3))
    lbl = font.render(text, True, color)
    surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, y))


def _draw_title_glow(surface: pygame.Surface, text: str, y: int,
                     font: pygame.font.Font, color: tuple, t: float) -> None:
    glow_amount = int(30 * math.sin(t * 1.8))
    glow_col = (max(0, min(255, color[0] + glow_amount)),
                max(0, min(255, color[1] + glow_amount)),
                max(0, min(255, color[2] + glow_amount)))
    for offset in [(2, 2), (-1, -1), (1, 0), (0, 1)]:
        g = font.render(text, True, (glow_col[0]//4, glow_col[1]//4, glow_col[2]//4))
        surface.blit(g, ((SCREEN_W - g.get_width()) // 2 + offset[0],
                         y + offset[1]))
    lbl = font.render(text, True, glow_col)
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
    def __init__(self, cx: int, cy: int, placeholder: str = "",
                 allowed_chars: str = "0123456789.", max_len: int = 15,
                 width: int = 340) -> None:
        self.rect        = pygame.Rect(cx - width // 2, cy - 26, width, 52)
        self.text        = ""
        self.placeholder = placeholder
        self.active      = False
        self.error       = ""
        self.allowed_chars = allowed_chars
        self.max_len     = max_len
        self._font    = pygame.font.SysFont("Courier", 20, bold=True)
        self._ph_font = pygame.font.SysFont("Arial",   17)
        self._err_f   = pygame.font.SysFont("Arial",   14)

    @staticmethod
    def _get_clipboard() -> str:
        """Get clipboard content (cross-platform). Tries pygame.scrap first, then subprocess."""
        import sys
        # Try pygame.scrap first (works without external tools)
        try:
            if pygame.scrap.get_init():
                data = pygame.scrap.get(pygame.SCRAP_TEXT)
                if data:
                    return data.decode("utf-8", errors="ignore").rstrip("\x00").strip()
        except Exception:
            pass
        # Fallback: subprocess
        import subprocess
        try:
            if sys.platform == "win32":
                return subprocess.check_output(["powershell", "-Command", "Get-Clipboard"],
                                               text=True, timeout=1).strip()
            elif sys.platform == "darwin":
                return subprocess.check_output(["pbpaste"], text=True, timeout=1).strip()
            else:  # Linux
                try:
                    return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"],
                                                   text=True, timeout=1).strip()
                except FileNotFoundError:
                    try:
                        return subprocess.check_output(["xsel", "-b"],
                                                       text=True, timeout=1).strip()
                    except FileNotFoundError:
                        pass
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        return ""

    @staticmethod
    def _set_clipboard(text: str) -> None:
        """Set clipboard content (cross-platform). Tries pygame.scrap first, then subprocess."""
        import sys
        # Try pygame.scrap first
        try:
            if pygame.scrap.get_init():
                pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8") + b"\x00")
                return
        except Exception:
            pass
        # Fallback: subprocess
        import subprocess
        try:
            if sys.platform == "win32":
                subprocess.run(["powershell", "-Command",
                                f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'\'"],
                               timeout=1, check=False)
            elif sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=text.encode(), timeout=1, check=False)
            else:  # Linux
                try:
                    subprocess.run(["xclip", "-selection", "clipboard"],
                                   input=text.encode(), timeout=1, check=False)
                except FileNotFoundError:
                    try:
                        subprocess.run(["xsel", "-b"],
                                       input=text.encode(), timeout=1, check=False)
                    except FileNotFoundError:
                        pass
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
            cmd_mask = getattr(pygame, "KMOD_CMD", 0)
            if event.key == pygame.K_c and (event.mod & pygame.KMOD_CTRL or event.mod & cmd_mask):
                self._set_clipboard(self.text)
            elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL or event.mod & cmd_mask):
                clipboard = self._get_clipboard()
                filtered = "".join(c for c in clipboard if c in self.allowed_chars)
                available = self.max_len - len(self.text)
                self.text += filtered[:available]
                self.error = ""
            elif event.key == pygame.K_a and (event.mod & pygame.KMOD_CTRL or event.mod & cmd_mask):
                pass
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
                self.error = ""
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.active = False
            elif len(self.text) < self.max_len and event.unicode in self.allowed_chars:
                self.text  += event.unicode
                self.error  = ""


# ── Class Selection Widget ───────────────────────────────────────────────────

class ClassPicker:
    """
    Three vehicle classes as clickable glow tiles.

    pvp_mode  = True  -> PvP layout: client class is shown as marker
    pvp_mode  = False -> Coop/Solo: no client marker, optional info line below
    """
    CLASSES  = list(CAR_CLASSES.keys())
    TILE_W   = 260
    TILE_H   = 130
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
        locked_classes  - {label: class_name} marker (only useful in PvP)
        show_coop_info  - shows coop hint below tiles (only modes 1/2
                           AND client actually connected)
        In pvp_mode=False: client markers are completely suppressed.
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
            icon_rect = pygame.Rect(r.x + 6, r.y + 12, 32, 100)
            _draw_class_icon(surface, cls, icon_rect, col if active else (60, 75, 100))

            # Name
            name = self._fn.render(cs["display"], True,
                                   col if active else (90, 110, 150))
            surface.blit(name, (r.x + 46, r.y + 10))

            # Description - clipped to box width
            desc_text = CLASS_DESCRIPTIONS[cls]
            max_desc_w = self.TILE_W - 52
            desc_surf = self._fd.render(desc_text, True,
                                        C_LABEL if active else (60, 75, 100))
            if desc_surf.get_width() > max_desc_w:
                for n in range(len(desc_text) - 1, 0, -1):
                    desc_surf = self._fd.render(desc_text[:n], True,
                                                C_LABEL if active else (60, 75, 100))
                    if desc_surf.get_width() <= max_desc_w:
                        break
            surface.blit(desc_surf, (r.x + 46, r.y + 34))

            stats = [
                ("Speed", cs["speed_mul"],       (0, 195, 100)),
                ("Grip",  cs["grip_mod"] / 2.0,  ACCENT),
                ("Fuel",  1.0 / cs["fuel_mul"],  ACCENT2),
            ]
            for si, (slbl, val, scol) in enumerate(stats):
                bx = r.x + 46 + si * 70;  by = r.y + 56
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

            # Phase 11.2: Client marker only in PvP mode
            if locked_classes and self.pvp_mode:
                for lbl_txt, locked_cls in locked_classes.items():
                    if locked_cls == cls:
                        tag = self._fs.render(f"<< {lbl_txt}", True,
                                              col if active else GRAY)
                        surface.blit(tag,
                                     (r.x + r.w - tag.get_width() - 8,
                                      r.y + r.h - tag.get_height() - 6))

        # Coop info only when client is actually connected + coop mode
        if show_coop_info and not self.pvp_mode:
            self._draw_coop_info(surface)

    def _draw_coop_info(self, surface: pygame.Surface) -> None:
        y = self.cy + self.TILE_H // 2 + 14
        text = "Co-op Mode  -  Client controls throttle & steering of the same car"
        lbl  = self._fc.render(text, True, (70, 110, 150))
        surface.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, y))


# ── Main Menu ─────────────────────────────────────────────────────────────────

class MainMenu:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen;  self._t = 0.0
        cx = SCREEN_W // 2
        y0 = SCREEN_H // 2 - 96
        self._title_f = pygame.font.SysFont("Arial", 76, bold=True)
        self._sub_f   = pygame.font.SysFont("Arial", 19)
        self._btn_host     = Button(cx, y0,                       "  START HOST  ",    accent=ACCENT2)
        self._btn_solo     = Button(cx, y0 +   BTN_H + BTN_GAP,   "  SOLO PLAY  ",     accent=GREEN)
        self._btn_client   = Button(cx, y0 + 2*(BTN_H+BTN_GAP),   "  CONNECT CLIENT  ")
        self._btn_settings = Button(cx, y0 + 3*(BTN_H+BTN_GAP),   "  SETTINGS  ",      accent=(0, 180, 180))
        self._btn_quit     = Button(cx, y0 + 3*(BTN_H+BTN_GAP) + BTN_H + BTN_GAP + 24,
                                    "  EXIT  ",          accent=(160, 40, 40))

    def run(self) -> str:
        global _particles
        _particles = None
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if _handle_global_key(event):                         continue
                if event.type == pygame.QUIT:                        return "quit"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return "quit"
                if self._btn_host.is_clicked(event):                 return "host"
                if self._btn_solo.is_clicked(event):                 return "solo"
                if self._btn_client.is_clicked(event):               return "client"
                if self._btn_settings.is_clicked(event):             return "settings"
                if self._btn_quit.is_clicked(event):                 return "quit"
            self.screen.fill(MENU_BG)
            _draw_animated_bg(self.screen, self._t, count=40, color=ACCENT)

            # Animated separator line with glow pulse
            line_alpha = int(180 + 75 * math.sin(self._t * 2))
            line_col = (min(255, ACCENT[0] + line_alpha // 4),
                        min(255, ACCENT[1] + line_alpha // 4),
                        min(255, ACCENT[2] + line_alpha // 4))
            pygame.draw.line(self.screen, line_col,
                             (SCREEN_W//2 - 200, 168), (SCREEN_W//2 + 200, 168), 2)

            # Pulsing title with glow
            glow = int(40 * math.sin(self._t * 1.5))
            title_col = (max(0, min(255, ACCENT2[0] + glow)),
                         max(0, min(255, ACCENT2[1] + glow)),
                         max(0, min(255, ACCENT2[2] + glow)))
            _draw_title(self.screen, "PANIC PILOT", 86, self._title_f, title_col)

            # Subtle pulse on subtitle
            sub_alpha = int(200 + 55 * math.sin(self._t * 2.5))
            sub = self._sub_f.render("Asymmetric Co-op Racing Game", True,
                                     (max(0, min(255, C_LABEL[0] + sub_alpha // 6)),
                                      max(0, min(255, C_LABEL[1] + sub_alpha // 6)),
                                      max(0, min(255, C_LABEL[2] + sub_alpha // 6))))
            self.screen.blit(sub, ((SCREEN_W - sub.get_width()) // 2, 186))

            # Buttons with staggered entrance animation
            all_btns = (self._btn_host, self._btn_solo,
                        self._btn_client, self._btn_settings, self._btn_quit)
            btn_colors = [ACCENT2, GREEN, None, (0, 180, 180), (160, 40, 40)]
            for i, btn in enumerate(all_btns):
                enter_t = min(1.0, max(0.0, (self._t - i * 0.08) * 3))
                if enter_t < 1.0:
                    ease = enter_t * enter_t * (3 - 2 * enter_t)
                    oy = int((1 - ease) * 30)
                    orig_rect = btn.rect.copy()
                    btn.rect = btn.rect.move(0, oy)
                    btn.draw(self.screen, mouse)
                    btn.rect = orig_rect
                else:
                    btn.draw(self.screen, mouse)

            pygame.display.flip()


# ── Solo Class Selection ──────────────────────────────────────────────────────

class SoloClassPicker:
    """Phase 11.1: pvp_mode=False, no coop info (no client in solo)."""
    SPEED_OPTIONS = [("Slow", 0.70), ("Normal", 1.00), ("Fast", 1.40)]

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen;  self._t = 0.0
        cx = SCREEN_W // 2
        self._title_f = pygame.font.SysFont("Arial", 38, bold=True)
        # Solo → no PvP, no coop info
        self._picker  = ClassPicker(cx, SCREEN_H // 2 - 50, pvp_mode=False)
        self._slider  = Slider(cx, SCREEN_H // 2 + 108, "Track Length", 10, 50, 15)
        self._speed_idx = 1
        y0 = SCREEN_H // 2 + 176
        self._btn_speed = Button(cx, y0,       "Speed")
        self._btn_start = Button(cx, y0 + BTN_H + BTN_GAP,  "  START SOLO  ", accent=GREEN)
        self._btn_back  = Button(cx, y0 + 2*(BTN_H+BTN_GAP), "  Back  ")

    def run(self) -> tuple[str, int, float] | None:
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if _handle_global_key(event):         continue
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
            self.screen.fill(MENU_BG)
            _draw_animated_bg(self.screen, self._t, count=20, color=GREEN)
            _draw_title_glow(self.screen, "SELECT VEHICLE", 52, self._title_f,
                             GREEN, self._t)
            # Solo: show_coop_info always False
            self._picker.draw(self.screen, show_coop_info=False)
            self._slider.draw(self.screen)
            spd_lbl, spd_val = self.SPEED_OPTIONS[self._speed_idx]
            orig = self._btn_speed.label
            self._btn_speed.label = f"Speed: {spd_lbl}"
            self._btn_speed.draw(self.screen, mouse)
            bars_c = ACCENT2 if spd_val >= 1.4 else (100, 180, 255) if spd_val <= 0.7 else ACCENT
            bw, bh, bg = 8, 10, 3
            bx = self._btn_speed.rect.right - 52
            by = self._btn_speed.rect.centery - bh // 2
            for b in range(1 if spd_val <= 0.7 else 2 if spd_val <= 1.0 else 3):
                pygame.draw.rect(self.screen, bars_c, (bx + b * (bw + bg), by, bw, bh), border_radius=2)
            self._btn_speed.label = orig
            self._btn_start.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()


# ── Host Setup ────────────────────────────────────────────────────────────────

class HostSetupMenu:
    SPEED_OPTIONS = [("Slow", 0.70), ("Normal", 1.00), ("Fast", 1.40)]

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
        import settings as _s
        username = getattr(_s, "USERNAME", "").strip()
        self._room_label = f"{username}'s Room" if username else f"Host ({self._own_ip})"
        cx = SCREEN_W // 2
        self._slider   = Slider(cx, SCREEN_H // 2 - 40, "Track Length (Tiles)", 10, 50, 20)
        self._modes    = [1, 2, 3]
        self._mode_idx = 0
        self._speed_idx = 1
        self._mode_labels = {1: "Split Control  - both control one car",
                             2: "Panic Pilot  - fog, navigator pings",
                             3: "PvP Racing  - two cars, one winner"}
        self._mode_colors = {1: (100, 180, 255), 2: ACCENT, 3: ACCENT2}
        self._mode_names  = {1: "Split Control", 2: "Panic Pilot", 3: "PvP Racing"}
        self._mode_flash  = 0.0  # Flash timer for mode change feedback
        y0 = SCREEN_H // 2 + 100
        self._btn_speed = Button(cx, y0,       "Speed")
        self._btn_mode  = Button(cx, y0 + BTN_H + BTN_GAP,  "Switch Mode")
        self._btn_lobby = Button(cx, y0 + 2*(BTN_H+BTN_GAP), "  OPEN LOBBY  ", accent=ACCENT2)
        self._btn_back  = Button(cx, y0 + 3*(BTN_H+BTN_GAP), "  Back  ")

    def run(self, prefill: dict | None = None, client_connected: bool = False) -> tuple | None:
        if prefill:
            mode_val = prefill.get("mode", 1)
            self._mode_idx = self._modes.index(mode_val) if mode_val in self._modes else 0
            self._speed_idx = prefill.get("speed_idx", 1)
            self._slider.value = prefill.get("length", 20)
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if _handle_global_key(event):         continue
                if event.type == pygame.QUIT:         return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                self._slider.handle_event(event)
                if self._btn_speed.is_clicked(event):
                    self._speed_idx = (self._speed_idx + 1) % len(self.SPEED_OPTIONS)
                if self._btn_mode.is_clicked(event) and not client_connected:
                    self._mode_idx  = (self._mode_idx  + 1) % len(self._modes)
                    self._mode_flash = 0.3  # Flash for 300ms
                if self._btn_lobby.is_clicked(event):
                    _, scale = self.SPEED_OPTIONS[self._speed_idx]
                    return self._modes[self._mode_idx], self._slider.value, scale
                if self._btn_back.is_clicked(event):  return None
            self.screen.fill(MENU_BG)
            _draw_animated_bg(self.screen, self._t, count=20, color=ACCENT2)
            _draw_title_glow(self.screen, "HOST SETTINGS", 72, self._title_f,
                             ACCENT2, self._t)
            room_display = self._lbl_f.render(f"Room: {self._room_label}", True, C_LABEL)
            self.screen.blit(room_display,
                             ((SCREEN_W - room_display.get_width()) // 2, 120))
            ip_hint = self._ip_lbl.render("Your IP (for the client):", True, C_LABEL)
            ip_val  = self._ip_font.render(f"{self._own_ip}:54321", True, ACCENT)
            box_w = 340
            box = pygame.Rect((SCREEN_W - box_w) // 2, 156, box_w, 48)
            _shadow_rect(self.screen, box, radius=8)
            pygame.draw.rect(self.screen, (10, 20, 45), box, border_radius=8)
            pygame.draw.rect(self.screen, C_BTN_BORDER, box, 2, border_radius=8)
            self.screen.blit(ip_hint, ((SCREEN_W - ip_hint.get_width()) // 2, 138))
            self.screen.blit(ip_val, (box.x + (box_w - ip_val.get_width()) // 2,
                                      box.y + (box.h - ip_val.get_height()) // 2))
            self._slider.draw(self.screen)
            self._mode_flash = max(0.0, self._mode_flash - dt)
            cur_mode = self._modes[self._mode_idx]
            m_col    = self._mode_colors.get(cur_mode, C_LABEL)
            m_lbl    = self._lbl_f.render(self._mode_labels[cur_mode], True, m_col)
            self.screen.blit(m_lbl, ((SCREEN_W - m_lbl.get_width()) // 2, SCREEN_H // 2 + 46))
            spd_lbl, spd_val = self.SPEED_OPTIONS[self._speed_idx]
            orig = self._btn_speed.label
            self._btn_speed.label = f"Speed: {spd_lbl}"
            self._btn_speed.draw(self.screen, mouse)
            bars_c = ACCENT2 if spd_val >= 1.4 else (100, 180, 255) if spd_val <= 0.7 else ACCENT
            bw, bh, bg = 8, 10, 3
            bx = self._btn_speed.rect.right - 52
            by = self._btn_speed.rect.centery - bh // 2
            for b in range(1 if spd_val <= 0.7 else 2 if spd_val <= 1.0 else 3):
                pygame.draw.rect(self.screen, bars_c, (bx + b * (bw + bg), by, bw, bh), border_radius=2)
            self._btn_speed.label = orig
            # Update mode button label with current mode
            self._btn_mode.label = f"Mode: {self._mode_names[cur_mode]}"
            mode_override = self._mode_colors[cur_mode] if self._mode_flash > 0 else None
            self._btn_mode.draw(self.screen, mouse, override_color=mode_override, disabled=client_connected)
            self._btn_lobby.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()


# ── Client IP Input with Validation ───────────────────────────────────────────

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
        
        self._input   = TextInput(cx, SCREEN_H // 2 + 30, "e.g. 192.168.1.42")
        self._input.active = True
        
        self._btn_connect = Button(cx, SCREEN_H // 2 + 120, "  CONNECT  ", accent=ACCENT)
        self._btn_back    = Button(cx, SCREEN_H // 2 + 120 + BTN_H + BTN_GAP, "  Back  ")
        
        # Recent connections and discovered rooms will be drawn as buttons
        self._recent_rects: list[tuple[pygame.Rect, str]] = []  # (rect, ip)
        self._discovered_rects: list[tuple[pygame.Rect, str]] = []  # (rect, ip)

    def _try_connect(self) -> str | None:
        """Validates IP and returns it, or sets error and returns None."""
        ip = self._input.text.strip() or "127.0.0.1"
        if not _validate_ip(ip):
            self._input.error = "Invalid IP address (e.g. 192.168.1.42)"
            return None
        return ip
    
    def _update_discovered_rooms(self) -> None:
        """Update list of discovered rooms from listener."""
        self._discovered_rooms = self._listener.get_rooms()
        if not self._listener.is_listening():
            self._listener.start_discovery(timeout=3.0)

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
                if _handle_global_key(event):         continue
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
            
            self.screen.fill(MENU_BG)
            _draw_animated_bg(self.screen, self._t, count=20, color=ACCENT)
            _draw_title_glow(self.screen, "CONNECT TO HOST", 76, self._title_f,
                             ACCENT, self._t)
            
            # Draw history and discovered rooms above input field
            self._draw_connection_options(mouse)
            
            lbl = self._lbl.render("Enter host IP address:", True, C_LABEL)
            self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H // 2 - 38))
            self._input.draw(self.screen)
            h = self._hint.render(
                "Host IP is shown in the host's window title | CTRL+V to paste", 
                True, C_LABEL)
            self.screen.blit(h, ((SCREEN_W - h.get_width()) // 2, SCREEN_H // 2 + 68))
            
            self._btn_connect.draw(self.screen, mouse)
            self._btn_back.draw(self.screen, mouse)
            pygame.display.flip()
    
    def _draw_connection_options(self, mouse: tuple) -> None:
        """Draw recent connections and discovered rooms as clickable options."""
        self._recent_rects.clear()
        self._discovered_rects.clear()
        
        cx = SCREEN_W // 2
        y = 150
        
        # Draw recent connections
        recent = self._history.get_recent(limit=3)
        if recent:
            y_label = y
            lbl = self._lbl.render("Recent Connections:", True, ACCENT)
            self.screen.blit(lbl, (cx - lbl.get_width() // 2, y_label))
            y += 28
            
            for conn in recent:
                ip = conn["ip"]
                username = conn.get("username", ip)
                
                rect = pygame.Rect(cx - 160, y, 320, 32)
                hovered = rect.collidepoint(mouse)
                
                bg = (40, 60, 100) if hovered else (20, 32, 60)
                border = ACCENT if hovered else (50, 80, 140)
                
                pygame.draw.rect(self.screen, bg, rect, border_radius=6)
                pygame.draw.rect(self.screen, border, rect, 1, border_radius=6)
                
                text = self._small_f.render(f"[*]  {username}  ({ip})", True,
                                           ACCENT if hovered else C_LABEL)
                self.screen.blit(text, (rect.x + 12, rect.centery - text.get_height() // 2))
                
                self._recent_rects.append((rect, ip))
                y += 36
        
        y += 8
        
        # Draw discovered rooms
        if self._discovered_rooms:
            y_label = y
            lbl = self._lbl.render("Discovered Rooms:", True, ACCENT2)
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
                
                text = self._small_f.render(f"[*]  {room_name}  ({ip})", True,
                                           ACCENT2 if hovered else C_LABEL)
                self.screen.blit(text, (rect.x + 12, rect.centery - text.get_height() // 2))
                
                self._discovered_rects.append((rect, ip))
                y += 36


# ── Chat Panel ────────────────────────────────────────────────────────

class ChatPanel:
    """Toggleable chat overlay for lobby communication."""

    def __init__(self, screen: pygame.Surface, username: str = "Player") -> None:
        self.screen = screen
        self._username = username
        self._t = 0.0
        self._open = False

        # Toggle button - top right corner
        self._btn_size = 42
        self._btn_x = SCREEN_W - self._btn_size - 12
        self._btn_y = 12
        self._btn_rect = pygame.Rect(self._btn_x, self._btn_y, self._btn_size, self._btn_size)

        # Unread badge
        self._unread = 0

        # Chat window
        self.w = 360
        self.h = 380
        self.x = SCREEN_W - self.w - 16
        self.y = 60

        # Messages: list of {"sender": str, "text": str, "time": float}
        self.messages: list[dict] = []

        # Fonts
        self._title_f = pygame.font.SysFont("Arial", 15, bold=True)
        self._msg_f = pygame.font.SysFont("Arial", 13)
        self._sender_f = pygame.font.SysFont("Arial", 13, bold=True)
        self._icon_f = pygame.font.SysFont("Arial", 18)
        self._badge_f = pygame.font.SysFont("Arial", 11, bold=True)

        # Input field
        cx = self.x + self.w // 2
        self._input = TextInput(cx, self.y + self.h - 28, "Type message...",
                                allowed_chars=string.printable.replace('\n', '').replace('\r', '').replace('\x0b', '').replace('\x0c', ''),
                                max_len=200)

        self._btn_send = Button(self.x + self.w - 40, self.y + self.h - 28, ">", w=36, h=32, accent=ACCENT)
        self._btn_close = Button(self.x + self.w - 40, self.y + 4, "X", w=36, h=28)

        # Message line height
        self._line_h = 20

    def toggle(self) -> None:
        """Toggle chat open/closed."""
        if self._open:
            self._open = False
            self._input.active = False
        else:
            self._open = True
            self._unread = 0

    def is_clicked(self, pos: tuple) -> bool:
        """Check if toggle button was clicked."""
        return self._btn_rect.collidepoint(pos)

    def add_message(self, sender: str, text: str) -> None:
        """Add a message to the chat history."""
        self.messages.append({"sender": sender, "text": text, "time": self._t})
        if len(self.messages) > 50:
            self.messages = self.messages[-50:]
        # Increment unread badge when chat is closed
        if not self._open:
            self._unread += 1

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if message was sent."""
        if not self._open:
            return False
        if self._btn_send.is_clicked(event):
            text = self._input.text.strip()
            if text:
                self.add_message(self._username, text)
                self._input.text = ""
                return True
        if self._btn_close.is_clicked(event):
            self.toggle()
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self._input.active:
                text = self._input.text.strip()
                if text:
                    self.add_message(self._username, text)
                    self._input.text = ""
                    return True
        self._input.handle_event(event)
        if event.type == pygame.MOUSEWHEEL:
            pass  # scroll support if needed
        return False

    def _draw_toggle_btn(self, mouse: tuple) -> None:
        """Draw the chat toggle button."""
        hovered = self._btn_rect.collidepoint(mouse)
        bg = (40, 70, 130) if hovered else (20, 35, 65)
        border = ACCENT if hovered else (50, 80, 140)

        _shadow_rect(self.screen, self._btn_rect, radius=8)
        pygame.draw.rect(self.screen, bg, self._btn_rect, border_radius=8)
        pygame.draw.rect(self.screen, border, self._btn_rect, 2, border_radius=8)

        # Chat icon (speech bubble)
        icon = self._icon_f.render("C", True, ACCENT if hovered else (130, 160, 200))
        self.screen.blit(icon, (self._btn_rect.centerx - icon.get_width() // 2,
                                self._btn_rect.centery - icon.get_height() // 2))

        # Unread badge
        if self._unread > 0:
            badge_txt = self._badge_f.render(str(self._unread), True, WHITE)
            badge_r = 10
            bx = self._btn_rect.right - 4
            by = self._btn_rect.top - 4
            pygame.draw.circle(self.screen, (220, 60, 60), (bx, by), badge_r)
            self.screen.blit(badge_txt, (bx - badge_txt.get_width() // 2,
                                         by - badge_txt.get_height() // 2))

    def _draw_window(self, mouse: tuple) -> None:
        """Draw the open chat window."""
        # Overlay dim
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        self.screen.blit(overlay, (0, 0))

        # Window background
        pygame.draw.rect(self.screen, (12, 18, 35), (self.x, self.y, self.w, self.h), border_radius=10)
        pygame.draw.rect(self.screen, (60, 100, 180), (self.x, self.y, self.w, self.h), 2, border_radius=10)

        # Title bar
        title = self._title_f.render("CHAT", True, ACCENT)
        self.screen.blit(title, (self.x + 14, self.y + 6))

        # Close button
        self._btn_close.draw(self.screen, mouse)

        # Separator
        pygame.draw.line(self.screen, (40, 60, 100), (self.x + 8, self.y + 32),
                         (self.x + self.w - 8, self.y + 32), 1)

        # Messages area
        msg_area_y = self.y + 40
        msg_area_h = self.h - 82

        visible_lines = msg_area_h // self._line_h
        start_idx = max(0, len(self.messages) - visible_lines)

        y = msg_area_y
        for i in range(start_idx, len(self.messages)):
            msg = self.messages[i]
            sender = msg["sender"]
            text = msg["text"]

            is_self = (sender == self._username)
            sender_col = ACCENT if is_self else (200, 180, 100)
            sender_lbl = self._sender_f.render(f"{sender}:", True, sender_col)
            self.screen.blit(sender_lbl, (self.x + 12, y))

            # Message text with truncation
            max_text_w = self.w - 24 - sender_lbl.get_width()
            text_color = (180, 190, 210) if is_self else C_LABEL
            self._draw_wrapped_text(text, self.x + 16 + sender_lbl.get_width(), y,
                                    max_text_w, text_color)

            y += self._line_h
            if y > msg_area_y + msg_area_h:
                break

        # Input field
        self._input.draw(self.screen)
        self._btn_send.draw(self.screen, mouse)

    def _draw_wrapped_text(self, text: str, x: int, y: int, max_w: int, color: tuple) -> None:
        """Draw text that may be truncated if too long."""
        lbl = self._msg_f.render(text, True, color)
        if lbl.get_width() > max_w:
            for i in range(len(text) - 1, 0, -1):
                lbl = self._msg_f.render(text[:i] + "..", True, color)
                if lbl.get_width() <= max_w:
                    break
        self.screen.blit(lbl, (x, y))

    def draw(self, mouse: tuple) -> None:
        """Draw the chat UI (toggle button always, window when open)."""
        self._draw_toggle_btn(mouse)
        if self._open:
            self._draw_window(mouse)


# ── HOST LOBBY ────────────────────────────────────────────────────────

class HostLobby:
    """
    Persistent Lobby.
    Phase 11.1:
     - _lobby_timer starts at 999 -> instant broadcast on first frame
     - client_requests_state() -> instant snapshot independent of timer
     - _client_handshaked: only True when first lobby_client packet arrived
     - show_coop_info: only for coop + handshaked client
    """
    NET_PORT      = 54321
    LOBBY_SEND_HZ = 10

    def __init__(self, screen: pygame.Surface, mode: int,
                 length: int, speed_scale: float,
                 room_name: str | None = None,
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
        
        import settings as _s
        username = getattr(_s, "USERNAME", "").strip()
        if room_name and room_name.strip():
            self._room_name = room_name.strip()
        elif username:
            self._room_name = f"{username}'s Room"
        else:
            self._room_name = f"Host ({own_ip})"
        self._verify_code = f"{random.randint(0, 9999):04d}"
        self._broadcaster = RoomBroadcaster(self._room_name, tcp_port=self.NET_PORT, verify_code=self._verify_code)
        self._broadcaster.start()

        cx = SCREEN_W // 2
        self._title_f  = pygame.font.SysFont("Arial", 38, bold=True)
        self._lbl_f    = pygame.font.SysFont("Arial", 17)
        self._status_f = pygame.font.SysFont("Arial", 14, bold=True)
        self._hint_f   = pygame.font.SysFont("Arial", 13)
        self._wait_f   = pygame.font.SysFont("Arial", 26, bold=True)
        self._wait_f2  = pygame.font.SysFont("Arial", 16)

        pvp = (mode == 3)
        # Phase 11.2: Picker always centered; pvp_mode only controls marker display
        self._picker = ClassPicker(cx, SCREEN_H // 2 - 30, pvp_mode=pvp)
        self._client_class: str | None = None
        self._client_room_name: str = "Client"
        self._client_handshaked = False
        self._lobby_timer = 999.0

        y0 = SCREEN_H // 2 + 140
        self._btn_start    = Button(cx, y0,       "  START RACE  ",  accent=(50, 200, 80))
        self._btn_kick     = Button(cx, y0 + BTN_H + BTN_GAP,  "  KICK CLIENT  ",  accent=(200, 60, 60))
        self._btn_settings = Button(cx, y0 + 2*(BTN_H+BTN_GAP), "  Settings  ")
        self._btn_back     = Button(cx, y0 + 3*(BTN_H+BTN_GAP), "  Main Menu  ")

        # Chat panel
        self._username = username or "Host"
        self._chat = ChatPanel(screen, self._username)

    # ── Main loop ────────────────────────────────────────────────────

    def run(self) -> str:
        """Returns 'back' or 'settings'."""
        global _particles
        _particles = None
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if _handle_global_key(event):                 continue
                if event.type == pygame.QUIT:
                    self._close(); return "back"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._close(); return "back"
                self._picker.handle_event(event)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._chat.is_clicked(event.pos):
                        self._chat.toggle()
                if self._chat.handle_event(event):
                    # Message was sent - send to client
                    if self._net.is_connected():
                        msg = self._chat.messages[-1]
                        self._net.send_chat(msg["text"], self._username)
                if self._btn_start.is_clicked(event,
                                              disabled=not self._client_handshaked):
                    outcome = self._run_game()
                    if outcome == "settings": return "settings"
                if self._btn_kick.is_clicked(event) and self._net.is_connected():
                    self._net.send_kick()
                    self._client_class     = None
                    self._client_handshaked = False
                if self._btn_settings.is_clicked(event):
                    return "settings"   # Network stays alive
                if self._btn_back.is_clicked(event):
                    self._close(); return "back"

            # ── Client-Lobby-Update ───────────────────────────────────────────
            cl = self._net.get_client_lobby()
            if cl:
                # Verify code if host has one set
                client_code = cl.get("verify_code", "")
                if self._verify_code and client_code != self._verify_code:
                    # Wrong code - kick client
                    self._net.send_kick()
                    self._client_handshaked = False
                else:
                    self._client_class      = cl.get("car_class", "balanced")
                    self._client_room_name  = cl.get("client_name", "Client")
                    self._client_handshaked = True   # first data exchange confirmed

            # ── Chat messages from client ──────────────────────────────────────
            chat_msg = self._net.get_client_chat()
            while chat_msg:
                sender = chat_msg.get("sender", "Client")
                text = chat_msg.get("text", "")
                if text:
                    self._chat.add_message(sender, text)
                chat_msg = self._net.get_client_chat()

            if self._net.client_left():
                self._client_class      = None
                self._client_room_name  = "Client"
                self._client_handshaked = False

            # ── Phase 11.1: Immediate response to request_lobby_state ────────
            if self._net.client_requests_state():
                self._send_lobby_packet()
                self._lobby_timer = 0.0   # Reset timer

            # ── Regular Broadcast Timer ────────────────────────────────────────
            self._lobby_timer += dt
            if self._lobby_timer >= 1.0 / self.LOBBY_SEND_HZ:
                self._lobby_timer = 0.0
                self._send_lobby_packet()

            self._draw(mouse)

    def _send_lobby_packet(self) -> None:
        """Builds and sends the full lobby packet (when connected)."""
        if self._net.is_connected():
            self._net.send_lobby({
                "host_class":  self._picker.selected,
                "mode":        self.mode,
                "length":      self.length,
                "speed_scale": self.speed_scale,
                "status":      "lobby",
                "room_name":   getattr(self, "_room_name", f"Host"),
                "verify_code": getattr(self, "_verify_code", ""),
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

        # ── Phase 11.3: Step 1 – Send start repeatedly ──────────────────────
        # Resend every 100 ms until client sends "ready_for_map" or 2s timeout.
        # For Solo/Coop (not PvP): sending once is enough.
        if pvp and self._net.is_connected():
            RETRY_INTERVAL = 0.10   # 100 ms
            READY_TIMEOUT  = 2.0
            deadline       = time.time() + READY_TIMEOUT
            ready          = False
            next_send      = 0.0
            print("DEBUG: Host starting start-retry loop ...")
            while time.time() < deadline:
                if time.time() >= next_send:
                    self._net.send_start(start_pkt)
                    print(f"DEBUG: Host sending start packet "
                          f"({READY_TIMEOUT - (deadline - time.time()):.1f}s)")
                    next_send = time.time() + RETRY_INTERVAL
                if self._net.client_ready_for_map():
                    ready = True
                    print("DEBUG: Host received ready_for_map -> sending map")
                    break
                self._draw_waiting_for_ready()
                pygame.time.wait(10)
                for event in pygame.event.get():
                    if _handle_global_key(event):                 continue
                    if event.type == pygame.QUIT:
                        self._close(); return "back"
            if not ready:
                print("DEBUG: Host timeout - sending map without confirmation")
        else:
            # Coop / Solo: one start packet is enough
            self._net.send_start(start_pkt)
            print("DEBUG: Host sending start (co-op/solo)")

        # ── Phase 11.3: Step 2 – Send map, then reset flags ─────────────────
        print("DEBUG: Host sending map")
        self._net.send_map(map_data)

        # Only reset now – map is sent, client inbox doesn't matter
        self._net.reset_lobby_flags()

        # ── Start game ────────────────────────────────────────────────────────
        import settings as _s
        host_username = getattr(_s, "USERNAME", "").strip() or "Host"
        client_username = getattr(self, "_client_room_name", "Client")
        if not getattr(self, "_client_room_name", None):
            client_username = "Client"
        game = HostGame(
            screen           = self.screen,
            mode             = self.mode,
            track_length     = self.length,
            speed_scale      = self.speed_scale,
            net              = self._net,
            car_class_host   = self._picker.selected,
            car_class_client = client_cls,
            host_room_name   = getattr(self, "_room_name", host_username),
            client_room_name = client_username,
        )
        game._generated_track = generated
        game._init_game_objects(track=generated)
        game.run()

        # Back in lobby: instant broadcast + reset state
        self._lobby_timer = 999.0
        # Do not reset _client_handshaked here; rely on network timeout or client_left()
        print("DEBUG: Host returned to lobby")
        return "settings" if getattr(game, "_return_to_settings", False) else "back"

    def _draw_waiting_for_ready(self) -> None:
        """Brief loading screen while host waits for ready_for_map."""
        self.screen.fill(MENU_BG)
        t = self._wait_f.render("Waiting for client readiness ...", True, ACCENT)
        self.screen.blit(t, ((SCREEN_W - t.get_width())  // 2,
                               (SCREEN_H - t.get_height()) // 2))
        s = self._wait_f2.render(
            "Establishing connection ...", True, C_LABEL)
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
        self.screen.fill(MENU_BG)
        _draw_animated_bg(self.screen, self._t, count=25, color=ACCENT2)
        _draw_title_glow(self.screen, "HOST LOBBY", 42, self._title_f, ACCENT2, self._t)

        # ── Info Panel with margins ───────────────────────────────────────────
        panel_y = 80
        panel_h = 110
        panel_w = 520
        panel_rect = pygame.Rect((SCREEN_W - panel_w) // 2, panel_y, panel_w, panel_h)

        # Panel background
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (15, 25, 50, 200), panel_surf.get_rect(), border_radius=10)
        pygame.draw.rect(panel_surf, (60, 100, 180, 40), panel_surf.get_rect(), 2, border_radius=10)
        self.screen.blit(panel_surf, panel_rect)

        # Room name
        room_txt = self._lbl_f.render(f"Room: {self._room_name}", True, C_LABEL)
        self.screen.blit(room_txt, ((SCREEN_W - room_txt.get_width()) // 2, panel_y + 14))

        # Verification code – prominent display
        vc_font = pygame.font.SysFont("Courier", 28, bold=True)
        vc_lbl = vc_font.render(f"Code: {self._verify_code}", True, (255, 220, 60))
        self.screen.blit(vc_lbl, ((SCREEN_W - vc_lbl.get_width()) // 2, panel_y + 40))

        # Mode and Track
        modes_lbl = {1: "Split Control", 2: "Panic Pilot (Fog)", 3: "PvP Racing"}
        modes_col = {1: (100, 180, 255), 2: ACCENT, 3: ACCENT2}
        info_col = modes_col.get(self.mode, C_LABEL)
        info = self._lbl_f.render(
            f"Mode: {modes_lbl.get(self.mode,'?')}   |   Track: {self.length} Tiles", True, info_col)
        self.screen.blit(info, ((SCREEN_W - info.get_width()) // 2, panel_y + 68))

        # Phase 11.2: locked_classes & coop_info correctly per mode
        pvp       = (self.mode == 3)
        locked    = ({"Client": self._client_class}
                     if pvp and self._client_handshaked and self._client_class
                     else {})
        coop_info = (not pvp and self._client_handshaked)
        self._picker.pvp_mode = pvp   # update live
        self._picker.draw(self.screen,
                          locked_classes=locked,
                          show_coop_info=coop_info)

        # Status line – distinguishes TCP-open vs. fully handshaked
        if self._client_handshaked:
            st, sc = "[OK] NAVIGATOR CONNECTED & READY", (50, 210, 100)
        elif self._net.is_connected():
            st, sc = "[..] TCP connected - waiting for handshake ...", (180, 180, 60)
        else:
            st, sc = f"[--] Waiting for navigator ...   Port {self.NET_PORT}", ORANGE
        status = self._status_f.render(st, True, sc)
        self.screen.blit(status, ((SCREEN_W - status.get_width()) // 2,
                                   SCREEN_H // 2 + 92))

        # Start button: requires connected client for any hosted mode
        start_disabled = not self._client_handshaked
        self._btn_start.draw(self.screen, mouse, disabled=start_disabled)
        self._btn_kick.draw(self.screen, mouse, disabled=not self._net.is_connected())
        self._btn_settings.draw(self.screen, mouse)
        self._btn_back.draw(self.screen, mouse)

        for i, h in enumerate([
            "Choose class - START RACE",
             "ESC = Main Menu  |  Settings keeps connection alive",
        ]):
            hl = self._hint_f.render(h, True, (60, 80, 110))
            self.screen.blit(hl, ((SCREEN_W - hl.get_width()) // 2,
                                   SCREEN_H - 44 + i * 18))

        # ── Chat Panel ───────────────────────────────────────────────────────
        self._chat.draw(mouse)

        pygame.display.flip()


# ── CLIENT LOBBY ──────────────────────────────────────────────────────

class ClientLobby:
    """
    Phase 11.1:
     - Shows "Handshake in progress ..." until first lobby_host snapshot arrives
     - Sends request_lobby_state in first frame of lobby loop
     - Shows mode/length/speed from host_info immediately and correctly
     - pvp_mode of picker is dynamically updated from host_mode
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
        self._initial_sent   = False   # Phase 11.1: send request once
        self._verify_code    = ""      # Filled in after popup

        cx = SCREEN_W // 2
        self._title_f  = pygame.font.SysFont("Arial", 38, bold=True)
        self._lbl_f    = pygame.font.SysFont("Arial", 17)
        self._status_f = pygame.font.SysFont("Arial", 14, bold=True)
        self._hint_f   = pygame.font.SysFont("Arial", 13)
        # Picker starts as PvP; updated immediately after first host_info
        self._picker   = ClassPicker(cx, SCREEN_H // 2 - 30, pvp_mode=True)
        y0 = SCREEN_H // 2 + 134
        self._btn_back = Button(cx, y0, "  Leave (ESC)  ", accent=(200, 60, 60))

        import settings as _s
        self._username = getattr(_s, "USERNAME", "").strip() or "Client"
        self._chat = ChatPanel(screen, self._username)

    def _show_verify_popup(self) -> str | None:
        """Shows a modal popup asking for verification code. Returns code or None on cancel."""
        popup_w, popup_h = 420, 240
        px = (SCREEN_W - popup_w) // 2
        py = (SCREEN_H - popup_h) // 2
        popup_rect = pygame.Rect(px, py, popup_w, popup_h)

        cx = SCREEN_W // 2
        title_f = pygame.font.SysFont("Arial", 22, bold=True)
        lbl_f = pygame.font.SysFont("Arial", 16)
        inp = TextInput(cx, py + 100, "Enter code shown on host screen",
                        allowed_chars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", max_len=8,
                        width=300)
        inp.active = True

        btn_ok = Button(cx - 80, py + 170, "  JOIN  ", w=140, h=42, accent=ACCENT)
        btn_cancel = Button(cx + 80, py + 170, "  CANCEL  ", w=140, h=42)

        # Draw underlying screen first so popup overlays it
        self._draw_status(f"Connected to {self.host_ip} - Enter code to join", (100, 180, 255))

        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0
            self._t += dt
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return None
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return inp.text.strip() if inp.text.strip() else None
                inp.handle_event(event)
                if btn_ok.is_clicked(event):
                    return inp.text.strip() if inp.text.strip() else None
                if btn_cancel.is_clicked(event):
                    return None

            # Dimmed overlay
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            self.screen.blit(overlay, (0, 0))

            # Popup background
            pygame.draw.rect(self.screen, (20, 30, 55), popup_rect, border_radius=12)
            pygame.draw.rect(self.screen, ACCENT, popup_rect, 2, border_radius=12)

            title = title_f.render("VERIFICATION REQUIRED", True, ACCENT)
            self.screen.blit(title, ((SCREEN_W - title.get_width()) // 2, py + 22))

            desc = lbl_f.render("Enter the code displayed on the host screen", True, C_LABEL)
            self.screen.blit(desc, ((SCREEN_W - desc.get_width()) // 2, py + 55))

            inp.draw(self.screen)
            btn_ok.draw(self.screen, mouse)
            btn_cancel.draw(self.screen, mouse)

            hint = self._hint_f.render("Ask the host for their code to join", True, (80, 100, 140))
            self.screen.blit(hint, ((SCREEN_W - hint.get_width()) // 2, py + 215))

            pygame.display.flip()

    def run(self) -> None:
        from connection_history import ConnectionHistory
        _history = ConnectionHistory()

        clock = pygame.time.Clock()
        self._draw_status(f"Connecting to {self.host_ip} ...", WHITE)
        if not self._net.connect(timeout=self.CONNECT_TIMEOUT):
            _history.add_or_update(self.host_ip, f"Host ({self.host_ip})", success=False)
            self._draw_status("Connection failed.", RED)
            pygame.time.wait(2500)
            return
        self._connected = True
        global _particles
        _particles = None
        pygame.event.clear()  # Clear stale events from connection screen

        # Show verification code popup after TCP connection
        code = self._show_verify_popup()
        if code is None:
            self._leave()
            return
        self._verify_code = code

        while True:
            dt = clock.tick(60) / 1000.0;  self._t += dt
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if _handle_global_key(event):             continue
                if event.type == pygame.QUIT:
                    self._leave(); return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._leave(); return
                self._picker.handle_event(event)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._chat.is_clicked(event.pos):
                        self._chat.toggle()
                if self._chat.handle_event(event):
                    if self._net.is_connected():
                        msg = self._chat.messages[-1]
                        self._net.send_chat(msg["text"], self._username)
                if self._btn_back.is_clicked(event):
                    self._leave(); return

            if not self._net.is_connected():
                self._draw_status("Connection lost.", RED)
                pygame.time.wait(2000); return

            # Chat messages from host
            chat_msg = self._net.get_host_chat()
            while chat_msg:
                sender = chat_msg.get("sender", "Host")
                text = chat_msg.get("text", "")
                if text:
                    self._chat.add_message(sender, text)
                chat_msg = self._net.get_host_chat()

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
                    self._draw_status("You were kicked by the host.", ORANGE)
                    pygame.time.wait(100)
                self._leave(); return

            # Phase 11.1: request lobby again in first frame
            # (request_lobby_state was already sent in connect(),
            # but only here the client sends its class too)
            if not self._initial_sent:
                self._initial_sent = True
                import settings as _s
                client_name = getattr(_s, "USERNAME", "").strip() or "Client"
                self._net.send_lobby({"car_class": self._picker.selected, "client_name": client_name, "verify_code": self._verify_code})

            # Receive host lobby info
            hl = self._net.get_host_lobby()
            if hl:
                prev_handshaked = bool(self._host_info)
                self._host_info   = hl
                self._last_update = self._t
                # Update picker mode immediately
                host_mode = int(hl.get("mode", 3))
                self._picker.pvp_mode = (host_mode == 3)
                # Record successful connection in history on first handshake
                if not prev_handshaked:
                    room_name = hl.get("room_name", f"Host ({self.host_ip})")
                    _history.add_or_update(self.host_ip, room_name, success=True)

            # Start signal – Phase 11.3: send ready_for_map IMMEDIATELY, BEFORE ClientGame is built
            start = self._net.get_start()
            if start:
                print("DEBUG: Client received start packet - sending ready_for_map")
                # Send three times for reliability (idempotent on host)
                for _ in range(3):
                    try: self._net.send_ready_for_map()
                    except Exception: pass
                    pygame.time.wait(30)
                print("DEBUG: Client ruft _run_game()")
                self._run_game(start)
                if not self._net.is_connected(): return
                # Fully reset state
                self._host_info    = {}
                self._last_update  = 0.0
                self._initial_sent = False
                self._lobby_timer  = 0.0
                try: self._net.send_request_lobby_state()
                except Exception: pass
                print("DEBUG: Client returned to lobby")
                continue

            # Regular class broadcast
            self._lobby_timer += dt
            if self._lobby_timer >= 1.0 / self.LOBBY_SEND_HZ:
                self._lobby_timer = 0.0
                import settings as _s
                client_name = getattr(_s, "USERNAME", "").strip() or "Client"
                self._net.send_lobby({"car_class": self._picker.selected, "client_name": client_name, "verify_code": self._verify_code})

            self._draw_lobby(mouse)

    def _run_game(self, start_data: dict) -> None:
        """
        Phase 11.3: ready_for_map was already sent before this call
        (3x in the lobby loop). Here only start ClientGame.
        NO reset_lobby_flags() BEFORE the game - the map might already
        be in _map_inbox and would be deleted.
        """
        from client import ClientGame
        print("DEBUG: ClientLobby creating ClientGame ...")
        host_room = self._host_info.get("room_name", "Host")
        import settings as _s
        client_username = getattr(_s, "USERNAME", "").strip() or "Client"
        game = ClientGame(
            host_ip          = self.host_ip,
            net              = self._net,
            car_class_host   = start_data.get("host_class",   "balanced"),
            car_class_client = self._picker.selected,
            host_room_name   = host_room,
            client_room_name = client_username,
        )
        # Phase 11.3: Signals _connect_loop that ready_for_map was already sent
        game._lobby_ready_sent = True
        print("DEBUG: ClientGame.run() starting")
        game.run()
        print("DEBUG: ClientGame.run() finished, return_to_lobby =",
              getattr(game, "_return_to_lobby", False))
        # Reset flags AFTER game
        if self._net.is_connected():
            self._net.reset_lobby_flags()

    def _leave(self) -> None:
        if self._connected:
            try: self._net.send_leave()
            except Exception: pass
        self._net.shutdown()

    def _draw_status(self, msg: str, color: tuple) -> None:
        self.screen.fill(MENU_BG)
        if not hasattr(self, "_status_font"):
            self._status_font = pygame.font.SysFont("Arial", 28, bold=True)
        t = self._status_font.render(msg, True, color)
        self.screen.blit(t, ((SCREEN_W - t.get_width())  // 2,
                              (SCREEN_H - t.get_height()) // 2))
        pygame.display.flip()

    def _draw_lobby(self, mouse: tuple) -> None:
        self.screen.fill(MENU_BG)
        _draw_animated_bg(self.screen, self._t, count=25, color=ACCENT)
        _draw_title_glow(self.screen, "CLIENT LOBBY", 42, self._title_f, ACCENT, self._t)

        # ── Info line with real-time settings from host ───────────────────────
        host_cls   = self._host_info.get("host_class", "")
        mode_raw   = self._host_info.get("mode", None)
        length_raw = self._host_info.get("length", None)
        speed_raw  = self._host_info.get("speed_scale", None)

        handshaked = bool(self._host_info)   # True sobald erster Snapshot da

        modes_lbl  = {1: "Split Control", 2: "Panic Pilot", 3: "PvP Racing"}
        speed_lbl  = {0.70: "Slow", 1.00: "Normal", 1.40: "Fast"}
        # Find closest match for speed_scale
        spd_text = "-"
        if speed_raw is not None:
            key = min(speed_lbl.keys(), key=lambda k: abs(k - float(speed_raw)))
            spd_text = speed_lbl.get(key, f"{speed_raw:.1f}x")

        if handshaked:
            info_parts = []
            if mode_raw is not None:
                info_parts.append(f"Mode: {modes_lbl.get(int(mode_raw),'?')}")
            if length_raw is not None:
                info_parts.append(f"Track: {length_raw} Tiles")
            info_parts.append(f"Speed: {spd_text}")
            info_str = "  |  ".join(info_parts)
            info_col = ACCENT2
        else:
            info_str = "Waiting for host data ..."
            info_col = (100, 100, 100)

        info = self._lbl_f.render(info_str, True, info_col)
        self.screen.blit(info, ((SCREEN_W - info.get_width()) // 2, 104))

        # ── Class Picker ─────────────────────────────────────────────────────
        locked = ({"Host": host_cls}
                  if handshaked and host_cls and self._picker.pvp_mode
                  else {})
        self._picker.draw(self.screen,
                          locked_classes=locked,
                           show_coop_info=False)  # Client does not show coop box

        # ── Connection Status ────────────────────────────────────────────────
        since = self._t - self._last_update
        if not handshaked:
            st, sc = "[..] Handshake in progress - waiting for host data ...", (180, 180, 60)
        elif since > 3.0:
            st, sc = "[OK] Connected - Host is configuring settings ...", (180, 180, 80)
        else:
            st, sc = f"[OK] Connected to {self.host_ip} - Waiting for start ...", (50, 210, 100)
        status = self._status_f.render(st, True, sc)
        self.screen.blit(status, ((SCREEN_W - status.get_width()) // 2,
                                   SCREEN_H // 2 + 96))

        self._btn_back.draw(self.screen, mouse)
        h = self._hint_f.render(
            "Choose class - host starts the race  |  ESC = Leave",
            True, (60, 80, 110))
        self.screen.blit(h, ((SCREEN_W - h.get_width()) // 2, SCREEN_H - 34))

        # ── Chat Panel ───────────────────────────────────────────────────────
        self._chat.draw(mouse)

        pygame.display.flip()


# ── Start Solo Game ───────────────────────────────────────────────────

def _run_solo(screen: pygame.Surface,
              car_class: str, length: int, speed_scale: float) -> None:
    from game  import Game
    from track import Track
    track = Track.generate(length=length)
    game  = Game(screen=screen, locked_class0=car_class)
    game.speed_scale = speed_scale
    game.reset(track=track)
    pygame.display.set_caption("Panic Pilot - SOLO  |  ESC/P=Pause  R=Reset")
    game.run()


        # ── Phase 12: Audio Settings ───────────────────────────────────────────

class SettingsScene:
    """
    Shows two volume sliders:
      - Music Volume
      - Effects Volume

    Values are passed immediately to the SoundManager and saved in
    settings.py (MUSIC_VOLUME / SFX_VOLUME) so they remain
    globally valid throughout the session.
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
        init_username = getattr(_s, "USERNAME", "")

        self._sl_music = Slider(cx, SCREEN_H // 2 - 120,
                                "Music Volume", 0, 100, init_music)
        self._sl_sfx   = Slider(cx, SCREEN_H // 2 - 30,
                                "Effects Volume", 0, 100, init_sfx)

        import string
        self._inp_username = TextInput(cx, SCREEN_H // 2 + 64, "Your Name (shown to other players)",
                                       allowed_chars=string.printable.replace('\n', '').replace('\r', ''),
                                       max_len=20)
        self._inp_username.text = init_username

        self._btn_test  = Button(cx, SCREEN_H // 2 + 150,
                                 "  Play Test Sound  ", accent=(0, 195, 100))
        self._btn_back  = Button(cx, SCREEN_H // 2 + 150 + BTN_H + BTN_GAP,
                                 "  Back  ")
        self._test_hint = ""
        self._test_t    = 0.0

    # ── Main Loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0
            self._t     += dt
            self._test_t = max(0.0, self._test_t - dt)
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if _handle_global_key(event):                 continue
                if event.type == pygame.QUIT:
                    return
                self._sl_music.handle_event(event)
                self._sl_sfx.handle_event(event)
                self._inp_username.handle_event(event)
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self._inp_username.active:
                        self._inp_username.active = False
                    else:
                        return
                # Apply volumes live while dragging
                if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
                    self._apply_volumes()
                if self._btn_test.is_clicked(event):
                    self._apply_volumes()
                    if _sound_mod:
                        _sound_mod.get().play_pickup_fuel()
                    self._test_hint = "[>] Test sound ..."
                    self._test_t    = 1.2
                if self._btn_back.is_clicked(event):
                    self._apply_volumes()
                    import settings as _s
                    _s.USERNAME = self._inp_username.text.strip()
                    _s.save_settings()
                    return

            self._draw(mouse)

    def _apply_volumes(self) -> None:
        import settings as _s
        _s.MUSIC_VOLUME = int(self._sl_music.value)
        _s.SFX_VOLUME   = int(self._sl_sfx.value)
        if _sound_mod and _sound_mod.get():
            _sound_mod.get().set_music_volume(_s.MUSIC_VOLUME)
            _sound_mod.get().set_sfx_volume(_s.SFX_VOLUME)

    def _draw(self, mouse: tuple) -> None:
        self.screen.fill(MENU_BG)
        _draw_animated_bg(self.screen, self._t, count=20, color=(0, 180, 180))
        _draw_title_glow(self.screen, "AUDIO SETTINGS", 72, self._title_f,
                         (0, 180, 180), self._t)

        # Animated separator line
        sep_alpha = int(100 + 60 * math.sin(self._t * 2))
        sep_col = (min(255, 30 + sep_alpha // 3),
                   min(255, 50 + sep_alpha // 3),
                   min(255, 80 + sep_alpha // 2))
        pygame.draw.line(self.screen, sep_col,
                         (SCREEN_W // 2 - 260, 154),
                         (SCREEN_W // 2 + 260, 154), 1)

        # Info-Text
        info = self._sub_f.render(
            "Changes are applied immediately", True, C_LABEL)
        self.screen.blit(info, ((SCREEN_W - info.get_width()) // 2, 126))

        self._sl_music.draw(self.screen)
        self._sl_sfx.draw(self.screen)
        self._inp_username.draw(self.screen)

        # Sound source hint
        if _sound_mod is not None:
            src_txt = "[OK] Audio system active (procedurally generated sounds)"
            src_col = (60, 200, 100)
        else:
            src_txt = "[--] Audio system not available"
            src_col = (200, 70, 50)
        src = self._hint_f.render(src_txt, True, src_col)
        self.screen.blit(src, ((SCREEN_W - src.get_width()) // 2,
                                SCREEN_H // 2 + 100))

        import settings as _s
        self._btn_test.draw(self.screen, mouse)
        self._btn_back.draw(self.screen, mouse)

        if self._test_hint and self._test_t > 0:
            th = self._hint_f.render(self._test_hint, True, (0, 200, 100))
            self.screen.blit(th, (SCREEN_W // 2 + 155,
                                   SCREEN_H // 2 + 121))

        # File path hint
        hints = [
            "Custom sounds: assets/sounds/  (music_menu.ogg, music_race.ogg, ..)",
            "Missing files are automatically replaced with procedural audio.",
        ]
        for i, h in enumerate(hints):
            hl = self._hint_f.render(h, True, (50, 70, 100))
            self.screen.blit(hl, ((SCREEN_W - hl.get_width()) // 2,
                                   SCREEN_H - 52 + i * 18))

        pygame.display.flip()


class _FirstStartSetup:
    """Multi-slide tutorial shown on first launch."""

    SLIDES = [
        {
            "title": "WELCOME TO PANIC PILOT",
            "icon": "racing",
            "lines": [
                "Panic Pilot is an asymmetric co-op racing game where two",
                "players share one car on a dangerous track.",
                "",
                "One player drives, the other navigates. Communication is key.",
            ],
        },
        {
            "title": "CONTROLS  -  DRIVER",
            "icon": "driver",
            "lines": [
                "The Driver (Player 1) steers the car.",
                "",
                "  A / D         -  Steer left / right",
                "  W / S         -  Accelerate / Brake",
                "  M             -  Toggle mirror view",
                "  R             -  Reset car on track",
            ],
        },
        {
            "title": "CONTROLS  -  NAVIGATOR",
            "icon": "navigator",
            "lines": [
                "The Navigator (Player 2) sees the full map but NOT the car.",
                "They guide the driver by placing ping markers.",
                "",
                "  Mouse click   -  Place ping marker on map",
                "  O / P         -  Zoom in / out (fog mode)",
                "  I             -  Use inventory item",
            ],
        },
        {
            "title": "GAME MODES",
            "icon": "modes",
            "lines": [
                "  Split Control   -  Both players control one car together",
                "",
                "  Panic Pilot     -  Fog covers the driver; navigator has",
                "                    the full map and uses pings to guide",
                "",
                "  PvP Racing      -  Two cars race head-to-head; collect",
                "                    items and use them against your opponent",
            ],
        },
        {
            "title": "FUEL & ITEMS",
            "icon": "fuel",
            "lines": [
                "Your car burns fuel constantly. Collect yellow canisters",
                "on the track to refuel, or you will be eliminated!",
                "",
                "  Boost pads     -  Speed boost when driven over",
                "  Oil slicks     -  Drop behind you to spin out pursuers",
                "  Item boxes     -  Random power-up (PvP mode)",
            ],
        },
        {
            "title": "MULTIPLAYER (LAN)",
            "icon": "multiplayer",
            "lines": [
                "Play with a friend over your local network.",
                "",
                "  Host            -  Opens a room and waits for connection",
                "  Connect Client  -  Enter the host's IP address to join",
                "",
                "Both players must agree on the game mode and settings.",
            ],
        },
    ]

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self._t = 0.0
        cx = SCREEN_W // 2
        self._title_f = pygame.font.SysFont("Arial", 42, bold=True)
        self._sub_f = pygame.font.SysFont("Arial", 18)
        self._hint_f = pygame.font.SysFont("Arial", 14)
        self._key_f = pygame.font.SysFont("Courier", 15, bold=True)

        self._slide = 0
        self._inp = TextInput(cx, SCREEN_H // 2 + 40, "Enter your display name")
        self._inp.active = True

        self._btn_next = Button(SCREEN_W // 2 + 100, SCREEN_H - 100,
                                "  NEXT  >>  ", w=160, h=46, accent=ACCENT)
        self._btn_skip = Button(SCREEN_W // 2 - 100, SCREEN_H - 100,
                                "  SKIP  ", w=160, h=46)

    def run(self) -> None:
        import settings as _s
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000.0
            self._t += dt
            mouse = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit
                self._inp.handle_event(event)
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RIGHT or event.key == pygame.K_RETURN:
                        if self._slide < len(self.SLIDES):
                            self._slide += 1
                        elif self._inp.text.strip():
                            _s.USERNAME = self._inp.text.strip()
                            _s.save_settings()
                            return
                    elif event.key == pygame.K_LEFT:
                        if self._slide > 0:
                            self._slide -= 1
                if self._btn_next.is_clicked(event):
                    if self._slide < len(self.SLIDES):
                        self._slide += 1
                    elif self._inp.text.strip():
                        _s.USERNAME = self._inp.text.strip()
                        _s.save_settings()
                        return
                if self._btn_skip.is_clicked(event):
                    if self._slide > 0:
                        self._slide -= 1

            self.screen.fill(MENU_BG)
            _draw_bg(self.screen, self._t)
            self._draw_slide(mouse)
            pygame.display.flip()

    def _draw_slide(self, mouse: tuple) -> None:
        global _particles
        _particles = None
        cx = SCREEN_W // 2
        self.screen.fill(MENU_BG)
        _draw_animated_bg(self.screen, self._t, count=25, color=ACCENT2)
        if self._slide < len(self.SLIDES):
            slide = self.SLIDES[self._slide]
            _draw_title_glow(self.screen, slide["title"], 60, self._title_f,
                             ACCENT2, self._t)
            y = 140
            for line in slide["lines"]:
                if line.startswith("  "):
                    txt = line.strip()
                    col = (100, 180, 255) if " - " in txt else (255, 220, 0)
                    lbl = self._hint_f.render(txt, True, col)
                elif line:
                    lbl = self._sub_f.render(line, True, C_LABEL)
                else:
                    y += 12
                    continue
                self.screen.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, y))
                y += 26
        else:
            _draw_title_glow(self.screen, "YOU'RE ALL SET!", 60, self._title_f,
                             GREEN, self._t)
            sub = self._sub_f.render("Choose a name to show other players", True, C_LABEL)
            self.screen.blit(sub, ((SCREEN_W - sub.get_width()) // 2, 120))
            self._inp.draw(self.screen)

        # Slide dots
        total = len(self.SLIDES) + 1
        dot_r, dot_gap = 5, 16
        dx = cx - (total - 1) * dot_gap // 2
        for i in range(total):
            color = ACCENT if i == self._slide else (60, 70, 100)
            pygame.draw.circle(self.screen, color, (dx + i * dot_gap, SCREEN_H - 60), dot_r)

        self._btn_next.draw(self.screen, mouse)
        if self._slide >= len(self.SLIDES):
            self._btn_next.label = "  START  \u25B6  "
        if self._slide > 0:
            self._btn_skip.draw(self.screen, mouse)
            back_lbl = self._hint_f.render("\u25C0  Back", True, (100, 110, 130))
            self.screen.blit(back_lbl,
                             (self._btn_skip.rect.centerx - back_lbl.get_width() // 2,
                              self._btn_skip.rect.centery - back_lbl.get_height() // 2))


# ── Entry Point ────────────────────────────────────────────────────────────────

def main() -> None:
    import settings as _s
    _s.load_settings()

    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")
    pygame.init()
    screen = _set_display_mode(FULLSCREEN)
    pygame.display.set_caption("Panic Pilot")

    try:
        pygame.scrap.init()
    except Exception:
        pass

    if not getattr(_s, "USERNAME", "").strip():
        _FirstStartSetup(screen).run()
        _s.load_settings()

    # ── Phase 12: Initialize audio system ───────────────────────────
    _sm = None
    if _sound_mod is not None:
        _sm = _sound_mod.get()
        import settings as _s
        _sm.set_music_volume(getattr(_s, "MUSIC_VOLUME", 70))
        _sm.set_sfx_volume(getattr(_s, "SFX_VOLUME", 80))
        _sm.play_music("menu")

    last_host_settings: dict | None = None

    while True:
        # Start menu music (after returning from game)
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
            import settings as _s
            username = getattr(_s, "USERNAME", "").strip()
            room_name = f"{username}'s Room" if username else f"Host ({settings._own_ip})"
            last_host_settings = {
                "mode": mode, "length": length,
                "speed_idx": settings._speed_idx,
            }
            existing_net = None
            while True:
                if _sm: _sm.play_music("menu")
                lobby   = HostLobby(screen, mode, length, speed_scale,
                                    room_name=room_name,
                                    net=existing_net)
                outcome = lobby.run()

                if outcome == "settings":
                    existing_net = lobby._net
                    client_connected = existing_net.is_connected() if existing_net else False
                    result2 = HostSetupMenu(screen).run(
                        prefill={"mode": mode, "length": length,
                                 "speed_idx": last_host_settings.get("speed_idx", 1)},
                        client_connected=client_connected)
                    if result2 is None:
                        continue
                    mode, length, speed_scale = result2
                    last_host_settings = {"mode": mode, "length": length,
                                          "speed_idx": last_host_settings.get("speed_idx", 1)}
                    continue

                existing_net = None
                break
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
