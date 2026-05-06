# =============================================================================
#  track.py  –  Panic Pilot | Tile system + sector generator + themes (Phase 5.2)
# =============================================================================
#
#  NEW (Phase 5.2):
#    - Theme system: color palette per biome (theme.py)
#    - Tile boundary walls: invisible walls at tile edges
#      → Car can drive next to the road but doesn't fall out of the world
#    - Extended sectors: S-curves, wide hairpin curves, long straights
#    - Canister density slightly increased; more evenly distributed along track
#
#  Extension hooks (Phase 6):
#    - TrackTile.spawn_points() → positions for items/ramps/boost pads
#    - Track.theme → physics hooks (slip, grip) for ice/sand physics
# =============================================================================
from __future__ import annotations
import math
import random
from typing import Optional
import pygame
from settings import *

# Lazy import to avoid circular references
def _get_theme_colors(theme):
    """Returns theme colors as dict, or default colors if no theme."""
    if theme is None:
        return {
            "grass_dark":  GRASS_DARK,
            "grass_light": GRASS_LIGHT,
            "road":        ROAD_GRAY,
            "curb_a":      CURB_RED,
            "curb_b":      CURB_WHITE,
            "centerline":  (170, 170, 170),
        }
    return {
        "grass_dark":  theme.grass_dark,
        "grass_light": theme.grass_light,
        "road":        theme.road_color,
        "curb_a":      theme.curb_a,
        "curb_b":      theme.curb_b,
        "centerline":  theme.centerline,
    }

# ── Tile constants ───────────────────────────────────────────────────────
TILE_SIZE = 800
ROAD_W    = TILE_SIZE // 3
INNER_R   = TILE_SIZE // 3
OUTER_R   = (TILE_SIZE * 2) // 3
CURB_W    = 16
CURB_SEGS = 14

STRAIGHT_H = "H"
STRAIGHT_V = "V"
CURVE_BL   = "BL"
CURVE_BR   = "BR"
CURVE_TL   = "TL"
CURVE_TR   = "TR"
FINISH_H   = "FH"
FINISH_V   = "FV"
NARROW_H   = "NH"   # Phase 7.2 – narrow roadway horizontal
NARROW_V   = "NV"   # Phase 7.2 – narrow roadway vertical

# Roadway width for Narrow-Tiles: 1/5 instead of 1/3 of tile
NARROW_W = 5   # Divisor: T // NARROW_W

EAST, SOUTH, WEST, NORTH = 0, 1, 2, 3

_STRAIGHT_FOR = {EAST: STRAIGHT_H, WEST: STRAIGHT_H,
                 NORTH: STRAIGHT_V, SOUTH: STRAIGHT_V}
_FINISH_FOR   = {EAST: FINISH_H,   WEST: FINISH_H,
                 NORTH: FINISH_V,  SOUTH: FINISH_V}

_TURN_OPTIONS = {
    EAST:  [(CURVE_BL, SOUTH), (CURVE_TL, NORTH)],
    WEST:  [(CURVE_BR, SOUTH), (CURVE_TR, NORTH)],
    NORTH: [(CURVE_BL, WEST),  (CURVE_BR, EAST)],
    SOUTH: [(CURVE_TL, WEST),  (CURVE_TR, EAST)],
}
_DELTA  = {EAST: (1, 0), WEST: (-1, 0), NORTH: (0, -1), SOUTH: (0, 1)}
_ANGLE  = {EAST: 90.0, SOUTH: 180.0, WEST: 270.0, NORTH: 0.0}

_PIVOT = {
    CURVE_BL: (0,         TILE_SIZE),
    CURVE_BR: (TILE_SIZE, TILE_SIZE),
    CURVE_TL: (0,         0),
    CURVE_TR: (TILE_SIZE, 0),
}
_SECTOR_MAP = {
    CURVE_BL: (+1, -1), CURVE_BR: (-1, -1),
    CURVE_TL: (+1, +1), CURVE_TR: (-1, +1),
}
_ARC = {
    CURVE_BL: (270.0, 360.0), CURVE_BR: (180.0, 270.0),
    CURVE_TL: (  0.0,  90.0), CURVE_TR: ( 90.0, 180.0),
}

# ── Sektor-Definitionen ────────────────────────────────────────────────────────
# "S"=Straight, "L"=Left, "R"=Right
# Phase 5.2: new patterns
SECTORS = {
    # High-speed passages (kept short – max 4 straights)
    "high_speed":       ["S", "S", "S", "S"],
    "high_speed_long":  ["S", "S", "S", "S", "S"],
    # Chicanes (short + medium)
    "chicane_lr":       ["S", "L", "S", "R"],
    "chicane_rl":       ["S", "R", "S", "L"],
    "double_chicane":   ["S", "L", "S", "R", "S", "L", "S", "R"],
    # Technical
    "technical_l":      ["L", "S", "L", "S", "R"],
    "technical_r":      ["R", "S", "R", "S", "L"],
    "hairpin_l":        ["L", "L", "S"],
    "hairpin_r":        ["R", "R", "S"],
    # S-curves (preferred)
    "s_curve_lr":       ["L", "S", "R", "S"],
    "s_curve_rl":       ["R", "S", "L", "S"],
    "s_curve_tight":    ["L", "R", "S", "L", "R"],
    "s_curve_long":     ["L", "S", "S", "R", "S", "S"],   # NEU
    # Mixed (curve-rich)
    "mixed":            ["S", "S", "L", "S", "S", "R"],
    "mixed_curvy":      ["L", "S", "R", "S", "L"],        # NEU
    "flowing":          ["S", "L", "S", "S", "R", "S"],
    "winding":          ["L", "S", "L", "S", "R", "S", "R"],  # NEU: stark kurvig
}

_SECTOR_GROUPS = {
    "high_speed": ["high_speed", "high_speed_long"],
    "chicane":    ["chicane_lr", "chicane_rl", "double_chicane"],
    "technical":  ["technical_l", "technical_r", "hairpin_l", "hairpin_r"],
    "s_curve":    ["s_curve_lr", "s_curve_rl", "s_curve_tight", "s_curve_long"],
    "mixed":      ["mixed", "mixed_curvy", "flowing", "winding"],
}


def _turn_heading(heading: int, direction: str) -> tuple[str, int]:
    opts = _TURN_OPTIONS[heading]
    return opts[0] if direction == "L" else opts[1]


# ── Tile-Boundary-Wall-Generierung ────────────────────────────────────────────

# Wall thickness outside (px) – wide enough so car doesn't drive through
_BOUNDARY_THICKNESS = 80

def _tile_boundary_walls(tile_type: str, wx: float, wy: float) -> list[tuple]:
    """
    Returns list of (x, y, w, h) world coordinates for boundary walls.
    Walls are at tile edges, not at the roadway.
    This allows driving on the shoulder but not leaving the tile.

    Principle: Each tile gets 4 narrow boundary walls (top, bottom, left, right).
    The openings (connections to next tile) are omitted.
    """
    T  = TILE_SIZE
    bw = _BOUNDARY_THICKNESS   # Wall thickness
    r1 = INNER_R               # = T//3
    r2 = OUTER_R               # = 2*T//3

    walls = []

    if tile_type in (STRAIGHT_H, FINISH_H):
        # Horizontal travel → block top and bottom
        walls.append((wx,       wy,          T,  bw))
        walls.append((wx,       wy + T - bw, T,  bw))

    elif tile_type in (STRAIGHT_V, FINISH_V):
        # Vertical travel → block left and right
        walls.append((wx,          wy, bw, T))
        walls.append((wx + T - bw, wy, bw, T))

    elif tile_type == NARROW_H:
        # Narrow roadway horizontal – walls closer to center
        nw = T // NARROW_W
        half = T // 2
        walls.append((wx, wy,               T, half - nw // 2))
        walls.append((wx, wy + half + nw // 2, T, half - nw // 2))

    elif tile_type == NARROW_V:
        # Narrow roadway vertical – walls closer to center
        nw = T // NARROW_W
        half = T // 2
        walls.append((wx,               wy, half - nw // 2, T))
        walls.append((wx + half + nw // 2, wy, half - nw // 2, T))

    elif tile_type in (CURVE_BL, CURVE_BR, CURVE_TL, CURVE_TR):
        # Curves: four boundary walls, short to keep connections clear
        # Common: corner walls on all four sides with gaps for roadway openings
        # The exact gaps correspond to the roadway [r1..r2] on each side
        if tile_type == CURVE_BL:   # Pivot bottom-left, opens left+bottom
            # Top: full width
            walls.append((wx,       wy,          T,         bw))
            # Right: full height
            walls.append((wx + T - bw, wy,       bw,        T))
            # Left: only corners (gap for exit to left)
            walls.append((wx,       wy,          bw,        r1))          # left top
            # Bottom: only corner right (exit to bottom)
            walls.append((wx + r2,  wy + T - bw, T - r2,   bw))          # bottom right

        elif tile_type == CURVE_BR:  # Pivot bottom-right, opens right+bottom
            walls.append((wx,       wy,          T,         bw))
            walls.append((wx,       wy,          bw,        T))
            walls.append((wx + T - bw, wy,       bw,        r1))
            walls.append((wx,       wy + T - bw, r1,        bw))

        elif tile_type == CURVE_TL:  # Pivot top-left, opens left+top
            walls.append((wx,       wy + T - bw, T,         bw))
            walls.append((wx + T - bw, wy,       bw,        T))
            walls.append((wx,       wy + r2,     bw,        T - r2))
            walls.append((wx + r2,  wy,          T - r2,    bw))

        elif tile_type == CURVE_TR:  # Pivot top-right, opens right+top
            walls.append((wx,       wy + T - bw, T,         bw))
            walls.append((wx,       wy,          bw,        T))
            walls.append((wx + T - bw, wy + r2,  bw,        T - r2))
            walls.append((wx,       wy,          r1,        bw))

    # Filter: only walls with positive size
    return [(x, y, max(1, w), max(1, h)) for x, y, w, h in walls if w > 0 and h > 0]


class TrackTile:
    """
    Individual track tile.
    Phase 5.2: theme-aware rendering, spawn_points() hook for Phase 6.
    """

    def __init__(self, world_x: float, world_y: float, tile_type: str,
                 theme=None) -> None:
        self.world_x   = world_x
        self.world_y   = world_y
        self.tile_type = tile_type
        self.theme     = theme           # Theme object for colors
        self._surf: Optional[pygame.Surface] = None
        self._scale_cache: dict = {}

    # ── Physics ────────────────────────────────────────────────────────────────

    def surface_at(self, wx: float, wy: float) -> Optional[str]:
        lx = wx - self.world_x; ly = wy - self.world_y
        T  = TILE_SIZE
        if not (0.0 <= lx <= T and 0.0 <= ly <= T): return None
        tt = self.tile_type
        if tt in (STRAIGHT_H, FINISH_H):
            return "asphalt" if T // 3 <= ly <= 2 * T // 3 else "grass"
        if tt in (STRAIGHT_V, FINISH_V):
            return "asphalt" if T // 3 <= lx <= 2 * T // 3 else "grass"
        if tt == NARROW_H:
            nw = T // NARROW_W
            return "asphalt" if T // 2 - nw // 2 <= ly <= T // 2 + nw // 2 else "grass"
        if tt == NARROW_V:
            nw = T // NARROW_W
            return "asphalt" if T // 2 - nw // 2 <= lx <= T // 2 + nw // 2 else "grass"
        px, py = _PIVOT[tt]; sx, sy = _SECTOR_MAP[tt]
        dist   = math.hypot(lx - px, ly - py)
        return "asphalt" if (INNER_R <= dist <= OUTER_R and
                              (lx-px)*sx >= 0 and (ly-py)*sy >= 0) else "grass"

    def road_center(self) -> tuple[float, float]:
        T = TILE_SIZE; tt = self.tile_type
        if tt in (STRAIGHT_H, STRAIGHT_V, FINISH_H, FINISH_V, NARROW_H, NARROW_V):
            return (self.world_x + T / 2, self.world_y + T / 2)
        px, py = _PIVOT[tt]; a0, a1 = _ARC[tt]
        mid    = math.radians((a0 + a1) / 2)
        mid_r  = (INNER_R + OUTER_R) / 2
        return (self.world_x + px + math.cos(mid) * mid_r,
                self.world_y + py + math.sin(mid) * mid_r)

    def boundary_walls(self) -> list[tuple]:
        """Tile boundary walls (for WallSystem). Returns (x,y,w,h) world coords."""
        return _tile_boundary_walls(self.tile_type, self.world_x, self.world_y)

    def spawn_points(self) -> list[tuple[float, float]]:
        """
        Phase 6 hook: Returns potential positions for items/boost pads.
        Current: road center + left/right offset.
        """
        cx, cy = self.road_center()
        return [(cx, cy), (cx + 60, cy), (cx - 60, cy)]

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"t": self.tile_type,
                "gx": int(self.world_x // TILE_SIZE),
                "gy": int(self.world_y // TILE_SIZE)}

    @classmethod
    def from_dict(cls, d: dict, theme=None) -> TrackTile:
        return cls(float(d["gx"] * TILE_SIZE), float(d["gy"] * TILE_SIZE),
                   d["t"], theme=theme)

    # ── Rendering ─────────────────────────────────────────────

    def draw(self, screen: pygame.Surface,
             off_x: int, off_y: int, zoom: float = 1.0) -> None:
        sx = round(self.world_x * zoom) + off_x
        sy = round(self.world_y * zoom) + off_y
        scaled = max(1, int(TILE_SIZE * zoom))
        if sx > SCREEN_W or sy > SCREEN_H or sx + scaled < 0 or sy + scaled < 0:
            return
        if self._surf is None:
            self._build_surface()
        if zoom == 1.0:
            screen.blit(self._surf, (sx, sy))
        else:
            key = round(zoom, 2)
            if key not in self._scale_cache:
                if len(self._scale_cache) > 8:
                    del self._scale_cache[next(iter(self._scale_cache))]
                self._scale_cache[key] = pygame.transform.scale(
                    self._surf, (scaled, scaled))
            screen.blit(self._scale_cache[key], (sx, sy))

    def _build_surface(self) -> None:
        T  = TILE_SIZE
        c  = _get_theme_colors(self.theme)
        s  = pygame.Surface((T, T))
        s.fill(c["grass_dark"])
        for r in range(0, T, 40):
            for col in range(0, T, 40):
                if (r // 40 + col // 40) % 2 == 0:
                    pygame.draw.rect(s, c["grass_light"], (col, r, 40, 40))
        tt = self.tile_type
        if tt in (STRAIGHT_H, FINISH_H):
            self._draw_straight_h(s, T, c, is_finish=(tt == FINISH_H))
        elif tt in (STRAIGHT_V, FINISH_V):
            self._draw_straight_v(s, T, c, is_finish=(tt == FINISH_V))
        elif tt == NARROW_H:
            self._draw_narrow_h(s, T, c)
        elif tt == NARROW_V:
            self._draw_narrow_v(s, T, c)
        else:
            self._draw_curve(s, T, c)
        self._surf = s

    def _draw_straight_h(self, s, T, c, is_finish=False):
        ry, rh = T // 3, T // 3
        pygame.draw.rect(s, c["road"], (0, ry, T, rh))
        self._curb_h(s, 0, T, ry - CURB_W, CURB_W, c)
        self._curb_h(s, 0, T, ry + rh,     CURB_W, c)
        if is_finish:
            self._draw_finish_line_h(s, T, ry, rh, c)
        else:
            mid = ry + rh // 2
            for x in range(0, T, 60):
                pygame.draw.rect(s, c["centerline"], (x, mid - 2, 38, 4))

    def _draw_straight_v(self, s, T, c, is_finish=False):
        rx, rw = T // 3, T // 3
        pygame.draw.rect(s, c["road"], (rx, 0, rw, T))
        self._curb_v(s, rx - CURB_W, CURB_W, 0, T, c)
        self._curb_v(s, rx + rw,     CURB_W, 0, T, c)
        if is_finish:
            self._draw_finish_line_v(s, T, rx, rw, c)
        else:
            mid = rx + rw // 2
            for y in range(0, T, 60):
                pygame.draw.rect(s, c["centerline"], (mid - 2, y, 4, 38))

    def _draw_narrow_h(self, s, T, c):
        """Narrow horizontal roadway – T//NARROW_W wide."""
        nw  = T // NARROW_W
        ry  = T // 2 - nw // 2
        pygame.draw.rect(s, c["road"], (0, ry, T, nw))
        # Curbs on both sides
        self._curb_h(s, 0, T, ry - CURB_W, CURB_W, c)
        self._curb_h(s, 0, T, ry + nw,     CURB_W, c)
        mid = T // 2
        for x in range(0, T, 60):
            pygame.draw.rect(s, c["centerline"], (x, mid - 1, 38, 2))

    def _draw_narrow_v(self, s, T, c):
        """Narrow vertical roadway – T//NARROW_W wide."""
        nw  = T // NARROW_W
        rx  = T // 2 - nw // 2
        pygame.draw.rect(s, c["road"], (rx, 0, nw, T))
        self._curb_v(s, rx - CURB_W, CURB_W, 0, T, c)
        self._curb_v(s, rx + nw,     CURB_W, 0, T, c)
        mid = T // 2
        for y in range(0, T, 60):
            pygame.draw.rect(s, c["centerline"], (mid - 1, y, 2, 38))

    def _draw_finish_line_h(self, s, T, ry, rh, c):
        pygame.draw.rect(s, c["road"], (0, ry, T, rh))
        tile_sz = 24; cols = T // tile_sz; rows = rh // tile_sz
        for r in range(rows):
            for col in range(cols):
                color = (230,230,230) if (r + col) % 2 == 0 else (25,25,25)
                pygame.draw.rect(s, color, (col*tile_sz, ry + r*tile_sz, tile_sz, tile_sz))
        pygame.draw.line(s, YELLOW, (0, ry),      (T, ry),      3)
        pygame.draw.line(s, YELLOW, (0, ry + rh), (T, ry + rh), 3)
        try:
            # Scale font to fit tile width
            font_size = min(52, max(20, T // 5))
            font = pygame.font.SysFont("Arial", font_size, bold=True)
            lbl  = font.render("FINISH", True, YELLOW)
            # Only render if it fits
            if lbl.get_width() < T * 0.9:
                s.blit(lbl, (T//2 - lbl.get_width()//2, ry + rh//2 - lbl.get_height()//2))
        except Exception:
            pass

    def _draw_finish_line_v(self, s, T, rx, rw, c):
        pygame.draw.rect(s, c["road"], (rx, 0, rw, T))
        tile_sz = 24; cols = rw // tile_sz; rows = T // tile_sz
        for r in range(rows):
            for col in range(cols):
                color = (230,230,230) if (r + col) % 2 == 0 else (25,25,25)
                pygame.draw.rect(s, color, (rx + col*tile_sz, r*tile_sz, tile_sz, tile_sz))
        pygame.draw.line(s, YELLOW, (rx,      0), (rx,      T), 3)
        pygame.draw.line(s, YELLOW, (rx + rw, 0), (rx + rw, T), 3)
        try:
            # Scale font to fit tile width
            font_size = min(52, max(16, rw // 4))
            font = pygame.font.SysFont("Arial", font_size, bold=True)
            lbl = font.render("FINISH", True, YELLOW)
            # Rotate text for vertical layout
            rotated = pygame.transform.rotate(lbl, 90)
            # Only render if it fits
            if rotated.get_width() < T * 0.9:
                s.blit(rotated, (rx + rw//2 - rotated.get_width()//2, T//2 - rotated.get_height()//2))
        except Exception:
            pass

    def _draw_curve(self, s, T, c):
        px, py = _PIVOT[self.tile_type]
        a0, a1 = _ARC[self.tile_type]
        steps  = 32
        self._draw_striped_curb(s, self._arc_poly(px,py,OUTER_R,OUTER_R+CURB_W,a0,a1,steps), steps, c)
        pygame.draw.polygon(s, c["road"], self._arc_poly(px,py,INNER_R,OUTER_R,a0,a1,steps))
        self._draw_striped_curb(s, self._arc_poly(px,py,INNER_R-CURB_W,INNER_R,a0,a1,steps), steps, c)
        mid_r = (INNER_R + OUTER_R) // 2
        for i in range(0, steps, 2):
            a_s = math.radians(a0 + (a1-a0)*i/steps)
            a_e = math.radians(a0 + (a1-a0)*(i+0.65)/steps)
            pygame.draw.line(s, c["centerline"],
                             (int(px+math.cos(a_s)*mid_r), int(py+math.sin(a_s)*mid_r)),
                             (int(px+math.cos(a_e)*mid_r), int(py+math.sin(a_e)*mid_r)), 3)

    def _arc_poly(self, cx, cy, r_in, r_out, a0, a1, steps):
        outer, inner = [], []
        for i in range(steps + 1):
            ang = math.radians(a0 + (a1-a0)*i/steps)
            ca, sa = math.cos(ang), math.sin(ang)
            outer.append((cx + ca*r_out, cy + sa*r_out))
            inner.append((cx + ca*r_in,  cy + sa*r_in))
        return outer + list(reversed(inner))

    def _draw_striped_curb(self, s, polygon, steps, c):
        n = steps+1; half = len(polygon)//2
        outer = polygon[:half]; inner = list(reversed(polygon[half:]))
        seg   = max(1, n // CURB_SEGS)
        for i in range(0, n-1, seg):
            j    = min(i+seg, n-1)
            col  = c["curb_a"] if (i//seg)%2==0 else c["curb_b"]
            poly = outer[i:j+1] + list(reversed(inner[i:j+1]))
            if len(poly) >= 3: pygame.draw.polygon(s, col, poly)

    def _curb_h(self, s, x0, x1, y, h, c):
        w = max(1, (x1-x0) // CURB_SEGS)
        for i in range(CURB_SEGS):
            pygame.draw.rect(s, c["curb_a"] if i%2==0 else c["curb_b"], (x0+i*w, y, w, h))

    def _curb_v(self, s, x, w, y0, y1, c):
        sh = max(1, (y1-y0) // CURB_SEGS)
        for i in range(CURB_SEGS):
            pygame.draw.rect(s, c["curb_a"] if i%2==0 else c["curb_b"], (x, y0+i*sh, w, sh))


# =============================================================================
#  Track
# =============================================================================

class Track:
    """
    Manages all tiles + theme.

    Phase 5.2 new:
      - self.theme: Theme object (colors, physics hooks)
      - build_boundary_walls(): Tile boundary walls (car doesn't fall out of world)
      - build_anticheat_walls(): Finish area walls
    """

    T = TILE_SIZE

    def __init__(self) -> None:
        from theme import Theme
        self.theme = Theme.by_name("standard")
        T = self.T
        self.tiles: list[TrackTile] = [
            TrackTile(0, T, STRAIGHT_H, self.theme),
            TrackTile(T, T, CURVE_BL,   self.theme),
            TrackTile(T, 2*T, STRAIGHT_V, self.theme),
            TrackTile(T, 3*T, CURVE_TL,   self.theme),
            TrackTile(0, 3*T, FINISH_H,   self.theme),
        ]
        self.start_x, self.start_y = float(T//2), float(T + T//2)
        self.start_angle = 90.0
        self._canister_positions: list[tuple] = []
        self._boost_positions:    list[tuple] = []
        self._oil_positions:      list[tuple] = []
        self._box_positions:      list[tuple] = []
        self._finish_tile_idx = len(self.tiles) - 1

    # ── Generator ─────────────────────────────────────────────────────────────

    @classmethod
    def generate(cls, length: int = 20, seed=None, theme=None) -> Track:
        """
        Generates a random track.
        theme=None → random theme selected from theme.THEMES.
        """
        from theme import Theme
        # Validate and clamp track length
        length = max(10, min(50, length))
        rng = random.Random(seed)

        # Choose theme
        if theme is None:
            chosen_theme = Theme.random(seed=rng.randint(0, 9999))
        else:
            chosen_theme = theme

        best_tiles, best_pos, best_boost, best_oil, best_boxes, best_finish = \
            [], [], [], [], [], 0
        for _ in range(5):
            tiles, can_pos, boost_pos, oil_pos, box_pos, finish_idx = \
                cls._sector_generate(length, rng, chosen_theme)
            if len(tiles) > len(best_tiles):
                best_tiles, best_pos, best_boost, best_oil, best_boxes, best_finish = \
                    tiles, can_pos, boost_pos, oil_pos, box_pos, finish_idx
            if len(tiles) >= length:
                break

        obj = cls.__new__(cls)
        obj.theme               = chosen_theme
        obj.tiles               = best_tiles
        obj.start_x             = float(TILE_SIZE // 2)
        obj.start_y             = float(TILE_SIZE // 2)
        obj.start_angle         = _ANGLE[EAST]
        obj._canister_positions = best_pos
        obj._boost_positions    = best_boost
        obj._oil_positions      = best_oil
        obj._box_positions      = best_boxes
        obj._finish_tile_idx    = best_finish
        return obj

    @classmethod
    def _sector_generate(cls, length, rng, theme):
        heading   = EAST; gx, gy = 0, 0
        visited   = {(gx, gy)}
        tiles     = [TrackTile(0, 0, _STRAIGHT_FOR[heading], theme)]
        remaining = length - 2

        # Curve tendency: S-curves and chicanes heavily weighted,
        # high_speed only once as occasional breather
        base_pool = [
            "s_curve", "s_curve", "s_curve",
            "chicane", "chicane",
            "technical", "technical",
            "mixed", "mixed",
            "high_speed",
        ]
        preferred = getattr(theme, "preferred_sectors", [])
        # preferred only 1× extra (was 2×) to maintain curve weight
        sector_pool = preferred + base_pool
        rng.shuffle(sector_pool)

        for sector_type in sector_pool:
            if remaining <= 0: break
            group = _SECTOR_GROUPS.get(sector_type, ["mixed"])
            pattern_name = rng.choice(group)
            pattern      = SECTORS[pattern_name]

            for step in pattern:
                if remaining <= 0: break
                dx, dy = _DELTA[heading]
                nx, ny = gx + dx, gy + dy
                if (nx, ny) in visited: break

                if step == "S":
                    base_type = _STRAIGHT_FOR[heading]
                    # Phase 7.2: ~12% chance of Narrow-Tile instead of normal straight
                    narrow_map = {STRAIGHT_H: NARROW_H, STRAIGHT_V: NARROW_V}
                    if rng.random() < 0.12 and base_type in narrow_map:
                        tile_type = narrow_map[base_type]
                    else:
                        tile_type = base_type
                    new_heading = heading
                else:
                    tile_type, new_heading = _turn_heading(heading, step)

                gx, gy = nx, ny
                visited.add((gx, gy))
                tiles.append(TrackTile(gx*TILE_SIZE, gy*TILE_SIZE, tile_type, theme))
                heading    = new_heading
                remaining -= 1

        # Finish line
        finish_type = _FINISH_FOR[heading]
        finish_idx  = len(tiles)
        dx, dy = _DELTA[heading]
        nx, ny = gx + dx, gy + dy
        if (nx, ny) not in visited:
            tiles.append(TrackTile(nx*TILE_SIZE, ny*TILE_SIZE, finish_type, theme))
        else:
            old = tiles[-1]
            tiles[-1] = TrackTile(old.world_x, old.world_y,
                                  finish_type if old.tile_type in
                                  (STRAIGHT_H, STRAIGHT_V) else old.tile_type, theme)
            finish_idx = len(tiles) - 1

        # Canisters + Phase 6.2: Boost pads & oil spills
        can_pos   = []
        boost_pos = []   # (x, y, angle)
        oil_pos   = []   # (x, y)
        box_pos   = []   # (x, y) item boxes – Phase 7

        for i, tile in enumerate(tiles[2:finish_idx], start=2):
            cx, cy = tile.road_center()
            can_pos.append((cx + rng.uniform(-25, 25), cy + rng.uniform(-25, 25)))
            if rng.random() < 0.67:
                can_pos.append((cx + rng.uniform(-60, 60), cy + rng.uniform(-60, 60)))
            # Boost only on straights (~30 %)
            if tile.tile_type in (STRAIGHT_H, STRAIGHT_V) and rng.random() < 0.30:
                angle = 0.0 if tile.tile_type == STRAIGHT_H else 90.0
                boost_pos.append((cx + rng.uniform(-40, 40),
                                   cy + rng.uniform(-30, 30), angle))
            # Oil on straights + curves (~20 %)
            if rng.random() < 0.20:
                oil_pos.append((cx + rng.uniform(-55, 55), cy + rng.uniform(-55, 55)))
            # ItemBox: rare (~15 %), preferred on curve tiles
            is_curve = tile.tile_type in (CURVE_BL, CURVE_BR, CURVE_TL, CURVE_TR)
            prob = 0.22 if is_curve else 0.12
            if rng.random() < prob:
                box_pos.append((cx + rng.uniform(-45, 45), cy + rng.uniform(-45, 45)))

        return tiles, can_pos, boost_pos, oil_pos, box_pos, finish_idx

    # ── Walls ─────────────────────────────────────────────────────────

    def build_boundary_walls(self) -> list[tuple[float, float, float, float]]:
        """
        Builds invisible boundary walls around the outside
        of the entire map (world boundary).
        All inner grass is freely driveable – no more tile-internal walls.
        Returns list of (x, y, w, h) in world coordinates.
        """
        if not self.tiles:
            return []
        T  = TILE_SIZE
        wt = _BOUNDARY_THICKNESS

        min_wx = min(t.world_x for t in self.tiles)
        max_wx = max(t.world_x for t in self.tiles) + T
        min_wy = min(t.world_y for t in self.tiles)
        max_wy = max(t.world_y for t in self.tiles) + T

        tw = max_wx - min_wx
        th = max_wy - min_wy

        return [
            (min_wx - wt, min_wy - wt, tw + 2 * wt, wt),  # oben
            (min_wx - wt, max_wy,      tw + 2 * wt, wt),  # unten
            (min_wx - wt, min_wy - wt, wt, th + 2 * wt),  # links
            (max_wx,      min_wy - wt, wt, th + 2 * wt),  # rechts
        ]

    def build_anticheat_walls(self) -> list[tuple]:
        """Phase 10: No internal Anti-Cheat walls – Grass is free."""
        return []

    # ── Finish line ─────────────────────────────────────────────────────

    def finish_center(self) -> tuple[float, float]:
        return self.tiles[self._finish_tile_idx].road_center()

    def crosses_finish(self, wx: float, wy: float, radius: float = 20) -> bool:
        tile   = self.tiles[self._finish_tile_idx]
        cx, cy = tile.road_center()
        return math.hypot(wx - cx, wy - cy) < radius + TILE_SIZE // 3

    # ── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "tiles":       [t.to_dict() for t in self.tiles],
            "start_x":     self.start_x,
            "start_y":     self.start_y,
            "start_angle": self.start_angle,
            "canisters":   [[c[0], c[1]] for c in self._canister_positions],
            "boosts":      [[b[0], b[1], b[2]] for b in self._boost_positions],
            "oils":        [[o[0], o[1]] for o in self._oil_positions],
            "boxes":       [[b[0], b[1]] for b in self._box_positions],
            "finish_idx":  self._finish_tile_idx,
            "theme":       self.theme.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Track:
        from theme import Theme
        theme = Theme.from_dict(data.get("theme", {"name": "standard"}))
        obj = cls.__new__(cls)
        obj.theme               = theme
        obj.tiles               = [TrackTile.from_dict(d, theme=theme)
                                    for d in data["tiles"]]
        obj.start_x             = float(data["start_x"])
        obj.start_y             = float(data["start_y"])
        obj.start_angle         = float(data["start_angle"])
        obj._canister_positions = [(float(c[0]), float(c[1])) for c in data["canisters"]]
        obj._boost_positions    = [(float(b[0]), float(b[1]), float(b[2]))
                                    for b in data.get("boosts", [])]
        obj._oil_positions      = [(float(o[0]), float(o[1]))
                                    for o in data.get("oils", [])]
        obj._box_positions      = [(float(b[0]), float(b[1]))
                                    for b in data.get("boxes", [])]
        obj._finish_tile_idx    = int(data.get("finish_idx", len(obj.tiles)-1))
        return obj

    # ── Physics / Canisters ─────────────────────────────────────────────────────

    def surface_at(self, wx: float, wy: float) -> str:
        for tile in self.tiles:
            if tile.surface_at(wx, wy) == "asphalt": return "asphalt"
        return "grass"

    def canister_positions(self) -> list[tuple[float, float]]:
        return list(self._canister_positions)

    def boost_positions(self) -> list[tuple]:
        return list(getattr(self, "_boost_positions", []))

    def oil_positions(self) -> list[tuple[float, float]]:
        return list(getattr(self, "_oil_positions", []))

    def box_positions(self) -> list[tuple[float, float]]:
        """ItemBox positions (x, y) – Phase 7."""
        return list(getattr(self, "_box_positions", []))

    # ── Rendering ─────────────────────────────────────────────

    def draw(self, screen: pygame.Surface,
             off_x: int, off_y: int, zoom: float = 1.0) -> None:
        for tile in self.tiles:
            tile.draw(screen, off_x, off_y, zoom)
