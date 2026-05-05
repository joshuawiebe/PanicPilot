# =============================================================================
#  hud.py  –  Panic Pilot | Head-Up-Display
# =============================================================================
from __future__ import annotations
import math
import pygame
from settings import *


class HUD:
    """Draws speedometer, fuel gauge, and timer as a fixed panel in the top-left.
    Modular design: method `draw(surface, speed, fuel, elapsed)` is sufficient.
    """

    PANEL_W = 240
    PANEL_H = 152   # +32 px for item slot
    PANEL_X = 16
    PANEL_Y = 16
    CORNER  = 8

    def __init__(self) -> None:
        self._font_lg  = pygame.font.SysFont("Arial", 22, bold=True)
        self._font_md  = pygame.font.SysFont("Arial", 17, bold=True)
        self._font_sm  = pygame.font.SysFont("Arial", 14)
        self._font_warn= pygame.font.SysFont("Arial", 36, bold=True)
        self._font_big = pygame.font.SysFont("Arial", 48, bold=True)

        # Panel surface (pre-rendered once, alpha)
        self._panel = pygame.Surface((self.PANEL_W, self.PANEL_H), pygame.SRCALPHA)

    # ─── Haupt-Draw ──────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             speed: float, fuel: float, elapsed: float,
             inventory: str | None = None,
             car_class: str = "balanced",
             latency: int | None = None,
             game_mode: int = 1) -> None:

        self._draw_panel(surface, speed, fuel, elapsed)
        self._draw_inventory(surface, inventory)
        self._draw_class_badge(surface, car_class)
        
        # Phase 12.2: Latency indicator in fog mode (Mode 2)
        if latency is not None and game_mode == 2:
            self._draw_latency(surface, latency)

        fuel_pct = fuel / FUEL_MAX
        if fuel <= 0:
            self._draw_centered_message(surface, "OUT OF FUEL!", ORANGE,
                                        self._font_big,
                                        y=SCREEN_H // 2 - 30)
            self._draw_centered_message(surface, "Press R to restart",
                                        WHITE, self._font_md,
                                        y=SCREEN_H // 2 + 30)
        elif fuel_pct < 0.25:
            # Flashing low fuel warning
            if int(elapsed * 2) % 2 == 0:
                self._draw_centered_message(surface, "LOW FUEL!",
                                            RED, self._font_warn,
                                            y=SCREEN_H - 62)

    # ─── Panel ───────────────────────────────────────────────────────────────

    def _draw_panel(self, surface: pygame.Surface,
                    speed: float, fuel: float, elapsed: float) -> None:
        pw, ph = self.PANEL_W, self.PANEL_H
        px, py = self.PANEL_X, self.PANEL_Y

        # Background
        self._panel.fill((0, 0, 0, 0))
        pygame.draw.rect(self._panel, (*HUD_BG, 195),
                         (0, 0, pw, ph), border_radius=self.CORNER)
        pygame.draw.rect(self._panel, (*WHITE, 60),
                         (0, 0, pw, ph), 2, border_radius=self.CORNER)
        surface.blit(self._panel, (px, py))

        # Speedometer
        speed_kmh = abs(speed) * 0.47   # Scaling px/s → km/h equivalent
        spd_lbl  = self._font_sm.render("SPEED", True, (150, 160, 180))
        spd_val  = self._font_lg.render(f"{speed_kmh:>3.0f} km/h", True, CYAN)
        surface.blit(spd_lbl, (px + 12, py + 10))
        surface.blit(spd_val, (px + 12, py + 26))

        # Speed bar
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

        # ── Fuel gauge ────────────────────────────────────────────────────────
        fuel_pct = max(0.0, fuel / FUEL_MAX)
        fuel_lbl = self._font_sm.render("FUEL", True, (150, 160, 180))
        surface.blit(fuel_lbl, (px + 12, py + 70))

        fb_x = px + 58
        fb_w = pw - 70
        fb_h = 12
        fb_y = py + 70
        pygame.draw.rect(surface, DARK_GRAY, (fb_x, fb_y, fb_w, fb_h),
                         border_radius=4)
        fc = GREEN if fuel_pct > 0.35 else (ORANGE if fuel_pct > 0.18 else RED)
        # CLAMP: fill width strictly limited to fb_w – prevents overflow when tank is full
        fill_w = max(0, min(fb_w, int(fb_w * fuel_pct)))
        pygame.draw.rect(surface, fc,
                         (fb_x, fb_y, fill_w, fb_h),
                         border_radius=4)
        pygame.draw.rect(surface, (80, 90, 110),
                         (fb_x, fb_y, fb_w, fb_h), 1, border_radius=4)
        pct_txt = self._font_sm.render(f"{fuel_pct*100:.0f}%", True, WHITE)
        # Right-aligned within the HUD box (6px margin from right edge)
        pct_x = px + pw - pct_txt.get_width() - 6
        pct_y = fb_y + (fb_h - pct_txt.get_height()) // 2   # vertikal zentriert
        surface.blit(pct_txt, (pct_x, pct_y))

        # ── Timer ─────────────────────────────────────────────────────────────
        mins  = int(elapsed) // 60
        secs  = int(elapsed) % 60
        csecs = int((elapsed % 1) * 100)
        timer_str = f"{mins:02d}:{secs:02d}.{csecs:02d}"
        t_lbl = self._font_sm.render("TIME", True, (150, 160, 180))
        t_val = self._font_lg.render(timer_str, True, WHITE)
        surface.blit(t_lbl, (px + 12,  py + 90))
        surface.blit(t_val, (px + 55,  py + 88))

    def _draw_inventory(self, surface: pygame.Surface,
                        inventory: str | None) -> None:
        """Item slot: small square below the HUD panel."""
        px, py = self.PANEL_X, self.PANEL_Y
        pw     = self.PANEL_W

        # Position within the extended panel
        slot_y  = py + 126
        slot_x  = px + 12
        slot_w  = 32
        slot_h  = 20
        label_x = slot_x + slot_w + 8

        # Label "ITEM"
        lbl = self._font_sm.render("ITEM", True, (150, 160, 180))
        surface.blit(lbl, (slot_x, slot_y + 2))

        # Slot box
        box_x = px + 58
        pygame.draw.rect(surface, (25, 20, 40),
                         (box_x, slot_y, slot_w, slot_h),
                         border_radius=4)

        if inventory is None:
            # Empty – gray grid pattern
            pygame.draw.rect(surface, (50, 50, 70),
                             (box_x, slot_y, slot_w, slot_h),
                             2, border_radius=4)
            empty = self._font_sm.render("—", True, (60, 60, 80))
            surface.blit(empty, (box_x + slot_w//2 - empty.get_width()//2,
                                  slot_y + slot_h//2 - empty.get_height()//2))
        elif inventory == "pocket_boost":
            # Yellow box with "B"
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
            # Black box with "O" (oil)
            pygame.draw.rect(surface, (18, 16, 10),
                             (box_x, slot_y, slot_w, slot_h),
                             border_radius=4)
            pygame.draw.rect(surface, (70, 60, 20),
                             (box_x, slot_y, slot_w, slot_h),
                             2, border_radius=4)
            item_lbl = self._font_md.render("O", True, (130, 110, 40))
            surface.blit(item_lbl, (box_x + slot_w//2 - item_lbl.get_width()//2,
                                    slot_y + slot_h//2 - item_lbl.get_height()//2))
            hint = self._font_sm.render("[SPACE]", True, GRAY)
            surface.blit(hint, (box_x + slot_w + 6,
                                 slot_y + slot_h//2 - hint.get_height()//2))
        elif inventory == "green_boomerang":
            # Green box with "↺"
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
            # Red box with "R"
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
            # Unknown item – purple "?"
            pygame.draw.rect(surface, (100, 40, 180),
                             (box_x, slot_y, slot_w, slot_h),
                             border_radius=4)
            item_lbl = self._font_md.render("?", True, WHITE)
            surface.blit(item_lbl, (box_x + slot_w//2 - item_lbl.get_width()//2,
                                    slot_y + slot_h//2 - item_lbl.get_height()//2))

    def _draw_class_badge(self, surface: pygame.Surface, car_class: str) -> None:
        """Small class badge in the top-right of the panel (Phase 11: no C=switch)."""
        from settings import CAR_CLASSES
        cs   = CAR_CLASSES.get(car_class, CAR_CLASSES["balanced"])
        name = cs["display"]
        col  = cs["color_host"]
        px, py, pw = self.PANEL_X, self.PANEL_Y, self.PANEL_W
        badge = self._font_sm.render(f"[ {name} ]", True, col)
        surface.blit(badge, (px + pw - badge.get_width() - 6, py + 6))

    # ─── Helper methods ────────────────────────────────────────────────────────

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
        # Shadow
        shadow = font.render(text, True, BLACK)
        cx = (SCREEN_W - lbl.get_width()) // 2
        surface.blit(shadow, (cx + 2, y + 2))
        surface.blit(lbl, (cx, y))

    def _draw_latency(self, surface: pygame.Surface, latency: int) -> None:
        """Phase 12.2: Draw latency/ping indicator in top-right for fog mode."""
        px = SCREEN_W - 160
        py = 16
        w, h = 144, 46
        
        # Determine color based on latency
        if latency < 50:
            color = (50, 220, 50)  # Green - excellent
            status = "EXCELLENT"
        elif latency < 100:
            color = (200, 220, 50)  # Yellow - good
            status = "GOOD"
        elif latency < 150:
            color = (255, 160, 50)  # Orange - fair
            status = "FAIR"
        else:
            color = (255, 80, 80)   # Red - poor
            status = "POOR"
        
        # Draw panel
        pygame.draw.rect(surface, (10, 10, 20), (px, py, w, h), border_radius=6)
        pygame.draw.rect(surface, color, (px, py, w, h), 2, border_radius=6)
        
        # Draw label and value
        label = self._font_sm.render("PING", True, (150, 160, 180))
        value = self._font_lg.render(f"{latency}ms", True, color)
        status_lbl = self._font_sm.render(status, True, color)
        
        surface.blit(label, (px + 8, py + 4))
        surface.blit(value, (px + 8, py + 18))
        surface.blit(status_lbl, (px + w - status_lbl.get_width() - 8, py + 4))
