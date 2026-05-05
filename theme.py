# =============================================================================
#  theme.py  –  Panic Pilot | Biome / Design Theme System
# =============================================================================
#
#  Each theme defines a color palette and physics modifiers.
#  Usage:
#      theme = Theme.random()           # random
#      theme = Theme.by_name("desert")  # explicit
#
#  Colors are used by track and UI.
#  Physics modifiers (slip, grip) are for future implementation
#  (e.g. ice slipping).
#
#  Simply add new themes to the THEMES dict.
# =============================================================================
from __future__ import annotations
import random
from dataclasses import dataclass, field


@dataclass
class Theme:
    """
    Describes a complete level theme.

    Attributes:
        name            – internal identifier
        display_name    – display name in UI
        # ── Colors ────────────────────────────────────────────────
        grass_dark      – dark grass/ground color
        grass_light     – light grass/ground color (checkerboard)
        road_color      – asphalt / road color
        curb_a          – curb color A
        curb_b          – curb color B
        bg_fill         – screen fill color (outermost, outside tiles)
        centerline      – centerline color
        hud_bg          – HUD background color
        # ── Physics hooks (Phase 6) ─────────────────────────────
        grass_slip      – slip on grass (0 = normal, 1 = very slippery)
        road_grip       – grip on asphalt (1 = normal, >1 = more grip)
        # ── Generator hints ───────────────────────────────────────
        preferred_sectors – sectors that appear more frequently in this biome
    """
    name:             str
    display_name:     str

    # Colors
    grass_dark:   tuple = (38,  90,  38)
    grass_light:  tuple = (50, 110,  45)
    road_color:   tuple = (70,  72,  78)
    curb_a:       tuple = (210, 40,  40)
    curb_b:       tuple = (230, 230, 230)
    bg_fill:      tuple = (30,  70,  30)
    centerline:   tuple = (170, 170, 170)
    hud_bg:       tuple = (8,   12,  22)

    # Physics hooks (values, ready for Phase 6 – implementation follows)
    grass_slip:   float = 0.0   # 0=normal, 1=fully slippery
    road_grip:    float = 1.0   # 1=normal, >1=more grip

    # Generator bias
    preferred_sectors: list = field(default_factory=list)

    # ─── Factory methods ─────────────────────────────────────────────

    @classmethod
    def random(cls, seed=None) -> Theme:
        """Selects a random theme."""
        rng = random.Random(seed)
        return rng.choice(list(THEMES.values()))

    @classmethod
    def by_name(cls, name: str) -> Theme:
        """Returns theme by name; fallback = default."""
        return THEMES.get(name, THEMES["standard"])

    def to_dict(self) -> dict:
        """For network transmission (embedded in Track.to_dict())."""
        return {"name": self.name}

    @classmethod
    def from_dict(cls, d: dict) -> Theme:
        return cls.by_name(d.get("name", "standard"))


    # ── Theme registry ────────────────────────────────────────────────────────────

THEMES: dict[str, Theme] = {

    "standard": Theme(
        name             = "standard",
        display_name     = "Classic",
        grass_dark       = ( 38,  90,  38),
        grass_light      = ( 50, 110,  45),
        road_color       = ( 70,  72,  78),
        curb_a           = (210,  40,  40),
        curb_b           = (230, 230, 230),
        bg_fill          = ( 30,  70,  30),
        centerline       = (170, 170, 170),
        hud_bg           = (  8,  12,  22),
        grass_slip       = 0.0,
        road_grip        = 1.0,
        preferred_sectors = ["high_speed", "chicane", "mixed"],
    ),

    "desert": Theme(
        name             = "desert",
        display_name     = "Desert",
        grass_dark       = (170, 120,  45),   # Sand, dark
        grass_light      = (200, 155,  70),   # Sand, light
        road_color       = ( 90,  80,  60),   # dusty asphalt
        curb_a           = (200, 150,  40),   # yellow curbs
        curb_b           = (240, 200, 120),   # light beige
        bg_fill          = (150, 105,  35),
        centerline       = (220, 190, 100),
        hud_bg           = ( 25,  15,   5),
        grass_slip       = 0.15,              # slightly slippery sand
        road_grip        = 0.9,
        preferred_sectors = ["high_speed", "mixed", "chicane"],
    ),

    "ice": Theme(
        name             = "ice",
        display_name     = "Ice & Snow",
        grass_dark       = (160, 190, 215),   # Ice, dark
        grass_light      = (200, 220, 240),   # Snow, light
        road_color       = (120, 140, 165),   # smooth ice asphalt
        curb_a           = ( 80, 120, 180),   # blue ice blocks
        curb_b           = (220, 235, 255),   # white snow
        bg_fill          = (140, 170, 200),
        centerline       = ( 50, 100, 180),
        hud_bg           = (  5,  10,  25),
        grass_slip       = 0.7,               # very slippery – Phase 6
        road_grip        = 0.6,               # little grip on ice – Phase 6
        preferred_sectors = ["technical", "chicane"],
    ),

    "night": Theme(
        name             = "night",
        display_name     = "Night",
        grass_dark       = ( 15,  30,  15),
        grass_light      = ( 20,  40,  20),
        road_color       = ( 30,  32,  38),
        curb_a           = ( 60, 100, 200),   # Neon blue
        curb_b           = (200,  30,  30),   # Neon red
        bg_fill          = ( 10,  15,  10),
        centerline       = ( 80, 140, 255),
        hud_bg           = (  5,   5,  15),
        grass_slip       = 0.1,
        road_grip        = 1.1,
        preferred_sectors = ["high_speed", "technical", "chicane"],
    ),

    "candy": Theme(
        name             = "candy",
        display_name     = "Candy Land",
        grass_dark       = (180,  80, 140),   # pink-purple
        grass_light      = (220, 130, 180),
        road_color       = (120,  60, 100),
        curb_a           = (255, 100, 180),   # Pink
        curb_b           = (255, 240, 100),   # Yellow
        bg_fill          = (160,  60, 120),
        centerline       = (255, 220, 100),
        hud_bg           = ( 40,  10,  30),
        grass_slip       = 0.0,
        road_grip        = 1.2,
        preferred_sectors = ["mixed", "chicane", "high_speed"],
    ),
}
