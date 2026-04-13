# =============================================================================
#  hud.py  –  Panic Pilot | Head-Up-Display
# =============================================================================
from __future__ import annotations
import math
import pygame
from settings import *


class HUD:
    """
    Zeichnet Tacho, Tankanzeige und Timer als festes Panel oben links.
    Modulares Design: Methode `draw(surface, speed, fuel, elapsed)` genügt.
    """

    PANEL_W = 240
    PANEL_H = 120
    PANEL_X = 16
    PANEL_Y = 16
    CORNER  = 8

    def __init__(self) -> None:
        self._font_lg  = pygame.font.SysFont("Arial", 22, bold=True)
        self._font_md  = pygame.font.SysFont("Arial", 17, bold=True)
        self._font_sm  = pygame.font.SysFont("Arial", 14)
        self._font_warn= pygame.font.SysFont("Arial", 36, bold=True)
        self._font_big = pygame.font.SysFont("Arial", 48, bold=True)

        # Panel-Oberfläche (einmal vorab, Alpha)
        self._panel = pygame.Surface((self.PANEL_W, self.PANEL_H), pygame.SRCALPHA)

    # ─── Haupt-Draw ──────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             speed: float, fuel: float, elapsed: float) -> None:

        self._draw_panel(surface, speed, fuel, elapsed)

        fuel_pct = fuel / FUEL_MAX
        if fuel <= 0:
            self._draw_centered_message(surface, "KEIN SPRIT!", ORANGE,
                                        self._font_big,
                                        y=SCREEN_H // 2 - 30)
            self._draw_centered_message(surface, "Drücke R zum Neustart",
                                        WHITE, self._font_md,
                                        y=SCREEN_H // 2 + 30)
        elif fuel_pct < 0.25:
            # Blinken
            if int(elapsed * 2) % 2 == 0:
                self._draw_centered_message(surface, "NIEDRIGER KRAFTSTOFF!",
                                            RED, self._font_warn,
                                            y=SCREEN_H - 62)

    # ─── Panel ───────────────────────────────────────────────────────────────

    def _draw_panel(self, surface: pygame.Surface,
                    speed: float, fuel: float, elapsed: float) -> None:
        pw, ph = self.PANEL_W, self.PANEL_H
        px, py = self.PANEL_X, self.PANEL_Y

        # Hintergrund
        self._panel.fill((0, 0, 0, 0))
        pygame.draw.rect(self._panel, (*HUD_BG, 195),
                         (0, 0, pw, ph), border_radius=self.CORNER)
        pygame.draw.rect(self._panel, (*WHITE, 60),
                         (0, 0, pw, ph), 2, border_radius=self.CORNER)
        surface.blit(self._panel, (px, py))

        # ── Tacho ─────────────────────────────────────────────────────────────
        speed_kmh = abs(speed) * 0.47   # Skalierung px/s → km/h-Äquivalent
        spd_lbl  = self._font_sm.render("SPEED", True, (150, 160, 180))
        spd_val  = self._font_lg.render(f"{speed_kmh:>3.0f} km/h", True, CYAN)
        surface.blit(spd_lbl, (px + 12, py + 10))
        surface.blit(spd_val, (px + 12, py + 26))

        # Tacho-Balken
        bar_x = px + 12
        bar_y = py + 54
        bar_w = pw - 24
        bar_h = 10
        pct   = min(1.0, speed_kmh / (CAR_MAX_SPEED * 0.47))
        pygame.draw.rect(surface, DARK_GRAY, (bar_x, bar_y, bar_w, bar_h),
                         border_radius=4)
        bar_color = self._speed_color(pct)
        pygame.draw.rect(surface, bar_color,
                         (bar_x, bar_y, int(bar_w * pct), bar_h),
                         border_radius=4)
        pygame.draw.rect(surface, (80, 90, 110),
                         (bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)

        # ── Tankanzeige ───────────────────────────────────────────────────────
        fuel_pct = max(0.0, fuel / FUEL_MAX)
        fuel_lbl = self._font_sm.render("TANK", True, (150, 160, 180))
        surface.blit(fuel_lbl, (px + 12, py + 70))

        fb_x = px + 58
        fb_w = pw - 70
        fb_h = 12
        fb_y = py + 70
        pygame.draw.rect(surface, DARK_GRAY, (fb_x, fb_y, fb_w, fb_h),
                         border_radius=4)
        fc = GREEN if fuel_pct > 0.35 else (ORANGE if fuel_pct > 0.18 else RED)
        # CLAMP: Füllbreite strikt auf fb_w begrenzen – verhindert Überlauf bei vollem Tank
        fill_w = max(0, min(fb_w, int(fb_w * fuel_pct)))
        pygame.draw.rect(surface, fc,
                         (fb_x, fb_y, fill_w, fb_h),
                         border_radius=4)
        pygame.draw.rect(surface, (80, 90, 110),
                         (fb_x, fb_y, fb_w, fb_h), 1, border_radius=4)
        pct_txt = self._font_sm.render(f"{fuel_pct*100:.0f}%", True, WHITE)
        surface.blit(pct_txt, (fb_x + fb_w + 6, fb_y - 1))

        # ── Timer ─────────────────────────────────────────────────────────────
        mins  = int(elapsed) // 60
        secs  = int(elapsed) % 60
        csecs = int((elapsed % 1) * 100)
        timer_str = f"{mins:02d}:{secs:02d}.{csecs:02d}"
        t_lbl = self._font_sm.render("ZEIT", True, (150, 160, 180))
        t_val = self._font_lg.render(timer_str, True, WHITE)
        surface.blit(t_lbl, (px + 12,  py + 90))
        surface.blit(t_val, (px + 55,  py + 88))

    # ─── Hilfsmethoden ───────────────────────────────────────────────────────

    @staticmethod
    def _speed_color(pct: float) -> tuple:
        if pct < 0.5:
            return CYAN
        elif pct < 0.8:
            return YELLOW
        else:
            return RED

    def _draw_centered_message(self, surface: pygame.Surface, text: str,
                                color: tuple, font: pygame.font.Font,
                                y: int) -> None:
        lbl = font.render(text, True, color)
        # Schatten
        shadow = font.render(text, True, BLACK)
        cx = (SCREEN_W - lbl.get_width()) // 2
        surface.blit(shadow, (cx + 2, y + 2))
        surface.blit(lbl, (cx, y))
