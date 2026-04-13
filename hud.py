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
    PANEL_H = 152   # +32 px für Item-Slot
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
             speed: float, fuel: float, elapsed: float,
             inventory: str | None = None) -> None:

        self._draw_panel(surface, speed, fuel, elapsed)
        self._draw_inventory(surface, inventory)

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
        # Rechts-bündig innerhalb der HUD-Box (6px Rand vor dem rechten Rand)
        pct_x = px + pw - pct_txt.get_width() - 6
        pct_y = fb_y + (fb_h - pct_txt.get_height()) // 2   # vertikal zentriert
        surface.blit(pct_txt, (pct_x, pct_y))

        # ── Timer ─────────────────────────────────────────────────────────────
        mins  = int(elapsed) // 60
        secs  = int(elapsed) % 60
        csecs = int((elapsed % 1) * 100)
        timer_str = f"{mins:02d}:{secs:02d}.{csecs:02d}"
        t_lbl = self._font_sm.render("ZEIT", True, (150, 160, 180))
        t_val = self._font_lg.render(timer_str, True, WHITE)
        surface.blit(t_lbl, (px + 12,  py + 90))
        surface.blit(t_val, (px + 55,  py + 88))

    def _draw_inventory(self, surface: pygame.Surface,
                        inventory: str | None) -> None:
        """Item-Slot: kleines Quadrat unter dem HUD-Panel."""
        px, py = self.PANEL_X, self.PANEL_Y
        pw     = self.PANEL_W

        # Positions-Zeile innerhalb des erweiterten Panels
        slot_y  = py + 126
        slot_x  = px + 12
        slot_w  = 32
        slot_h  = 20
        label_x = slot_x + slot_w + 8

        # Label "ITEM"
        lbl = self._font_sm.render("ITEM", True, (150, 160, 180))
        surface.blit(lbl, (slot_x, slot_y + 2))

        # Slot-Box
        box_x = px + 58
        pygame.draw.rect(surface, (25, 20, 40),
                         (box_x, slot_y, slot_w, slot_h),
                         border_radius=4)

        if inventory is None:
            # Leer – graues Raster-Muster
            pygame.draw.rect(surface, (50, 50, 70),
                             (box_x, slot_y, slot_w, slot_h),
                             2, border_radius=4)
            empty = self._font_sm.render("—", True, (60, 60, 80))
            surface.blit(empty, (box_x + slot_w//2 - empty.get_width()//2,
                                  slot_y + slot_h//2 - empty.get_height()//2))
        elif inventory == "pocket_boost":
            # Gelbe Box mit "B"
            pygame.draw.rect(surface, (200, 160, 0),
                             (box_x, slot_y, slot_w, slot_h),
                             border_radius=4)
            pygame.draw.rect(surface, (255, 220, 50),
                             (box_x, slot_y, slot_w, slot_h),
                             2, border_radius=4)
            item_lbl = self._font_md.render("B", True, BLACK)
            surface.blit(item_lbl, (box_x + slot_w//2 - item_lbl.get_width()//2,
                                    slot_y + slot_h//2 - item_lbl.get_height()//2))
            hint = self._font_sm.render("[SPACE]", True, YELLOW)
            surface.blit(hint, (box_x + slot_w + 6,
                                 slot_y + slot_h//2 - hint.get_height()//2))
        elif inventory == "oil_drop":
            # Schwarze Box mit "Ö" (Öl)
            pygame.draw.rect(surface, (18, 16, 10),
                             (box_x, slot_y, slot_w, slot_h),
                             border_radius=4)
            pygame.draw.rect(surface, (70, 60, 20),
                             (box_x, slot_y, slot_w, slot_h),
                             2, border_radius=4)
            item_lbl = self._font_md.render("Ö", True, (130, 110, 40))
            surface.blit(item_lbl, (box_x + slot_w//2 - item_lbl.get_width()//2,
                                    slot_y + slot_h//2 - item_lbl.get_height()//2))
            hint = self._font_sm.render("[SPACE]", True, GRAY)
            surface.blit(hint, (box_x + slot_w + 6,
                                 slot_y + slot_h//2 - hint.get_height()//2))
        elif inventory == "green_boomerang":
            # Grüne Box mit "↺"
            pygame.draw.rect(surface, (20, 80, 30),
                             (box_x, slot_y, slot_w, slot_h),
                             border_radius=4)
            pygame.draw.rect(surface, (80, 220, 100),
                             (box_x, slot_y, slot_w, slot_h),
                             2, border_radius=4)
            item_lbl = self._font_md.render("G", True, (150, 255, 160))
            surface.blit(item_lbl, (box_x + slot_w//2 - item_lbl.get_width()//2,
                                    slot_y + slot_h//2 - item_lbl.get_height()//2))
            hint = self._font_sm.render("[SPACE]", True, GREEN)
            surface.blit(hint, (box_x + slot_w + 6,
                                 slot_y + slot_h//2 - hint.get_height()//2))
        elif inventory == "red_boomerang":
            # Rote Box mit "R"
            pygame.draw.rect(surface, (80, 20, 20),
                             (box_x, slot_y, slot_w, slot_h),
                             border_radius=4)
            pygame.draw.rect(surface, (230, 60, 60),
                             (box_x, slot_y, slot_w, slot_h),
                             2, border_radius=4)
            item_lbl = self._font_md.render("R", True, (255, 160, 160))
            surface.blit(item_lbl, (box_x + slot_w//2 - item_lbl.get_width()//2,
                                    slot_y + slot_h//2 - item_lbl.get_height()//2))
            hint = self._font_sm.render("[SPACE]", True, RED)
            surface.blit(hint, (box_x + slot_w + 6,
                                 slot_y + slot_h//2 - hint.get_height()//2))
        else:
            # Unbekanntes Item – lila "?"
            pygame.draw.rect(surface, (100, 40, 180),
                             (box_x, slot_y, slot_w, slot_h),
                             border_radius=4)
            item_lbl = self._font_md.render("?", True, WHITE)
            surface.blit(item_lbl, (box_x + slot_w//2 - item_lbl.get_width()//2,
                                    slot_y + slot_h//2 - item_lbl.get_height()//2))

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
