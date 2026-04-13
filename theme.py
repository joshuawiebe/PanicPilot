# =============================================================================
#  theme.py  –  Panic Pilot | Biome / Design-Themen System
# =============================================================================
#
#  Jedes Theme definiert eine Farbpalette und Physik-Modifikatoren.
#  Verwendung:
#      theme = Theme.random()           # zufällig
#      theme = Theme.by_name("desert")  # explizit
#
#  Farben werden vom Track und der UI genutzt.
#  Physik-Modifikatoren (slip, grip) sind für spätere Implementierung
#  vorbereitet (z.B. Eis-Rutschen).
#
#  Neue Themen einfach zum THEMES-Dict hinzufügen.
# =============================================================================
from __future__ import annotations
import random
from dataclasses import dataclass, field


@dataclass
class Theme:
    """
    Beschreibt ein vollständiges Level-Thema.

    Attribute:
        name            – interner Bezeichner
        display_name    – Anzeigename in der UI
        # ── Farben ──────────────────────────────────────────────────────────
        grass_dark      – dunkle Gras-/Bodenfarbe
        grass_light     – helle Gras-/Bodenfarbe (Schachbrett)
        road_color      – Asphalt / Fahrbahnfarbe
        curb_a          – Randstein Farbe A
        curb_b          – Randstein Farbe B
        bg_fill         – Screen-Fill-Farbe (ganz außen, außerhalb Tiles)
        centerline      – Mittellinien-Farbe
        hud_bg          – HUD-Hintergrundfarbe
        # ── Physik-Hooks (Phase 6) ───────────────────────────────────────────
        grass_slip      – Schlupf auf Gras (0 = normal, 1 = sehr rutschig)
        road_grip       – Grip auf Asphalt (1 = normal, >1 = mehr Grip)
        # ── Generator-Hints ──────────────────────────────────────────────────
        preferred_sectors – Sektoren die in diesem Biom häufiger vorkommen
    """
    name:             str
    display_name:     str

    # Farben
    grass_dark:   tuple = (38,  90,  38)
    grass_light:  tuple = (50, 110,  45)
    road_color:   tuple = (70,  72,  78)
    curb_a:       tuple = (210, 40,  40)
    curb_b:       tuple = (230, 230, 230)
    bg_fill:      tuple = (30,  70,  30)
    centerline:   tuple = (170, 170, 170)
    hud_bg:       tuple = (8,   12,  22)

    # Physik-Hooks (Werte, bereit für Phase 6 - Implementierung folgt)
    grass_slip:   float = 0.0   # 0=normal, 1=voll-rutschig
    road_grip:    float = 1.0   # 1=normal, >1=mehr Grip

    # Generator-Bias
    preferred_sectors: list = field(default_factory=list)

    # ─── Factory-Methoden ─────────────────────────────────────────────────────

    @classmethod
    def random(cls, seed=None) -> Theme:
        """Wählt ein zufälliges Thema aus."""
        rng = random.Random(seed)
        return rng.choice(list(THEMES.values()))

    @classmethod
    def by_name(cls, name: str) -> Theme:
        """Gibt Theme per Name zurück; Fallback = Standard."""
        return THEMES.get(name, THEMES["standard"])

    def to_dict(self) -> dict:
        """Für Netzwerk-Übertragung (wird in Track.to_dict() eingebettet)."""
        return {"name": self.name}

    @classmethod
    def from_dict(cls, d: dict) -> Theme:
        return cls.by_name(d.get("name", "standard"))


# ── Themen-Registry ────────────────────────────────────────────────────────────

THEMES: dict[str, Theme] = {

    "standard": Theme(
        name             = "standard",
        display_name     = "Klassik",
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
        display_name     = "Wüste",
        grass_dark       = (170, 120,  45),   # Sand, dunkel
        grass_light      = (200, 155,  70),   # Sand, hell
        road_color       = ( 90,  80,  60),   # staubiger Asphalt
        curb_a           = (200, 150,  40),   # gelbe Randsteine
        curb_b           = (240, 200, 120),   # helles Beige
        bg_fill          = (150, 105,  35),
        centerline       = (220, 190, 100),
        hud_bg           = ( 25,  15,   5),
        grass_slip       = 0.15,              # leicht rutschiger Sand
        road_grip        = 0.9,
        preferred_sectors = ["high_speed", "mixed", "chicane"],
    ),

    "ice": Theme(
        name             = "ice",
        display_name     = "Eis & Schnee",
        grass_dark       = (160, 190, 215),   # Eis, dunkel
        grass_light      = (200, 220, 240),   # Schnee, hell
        road_color       = (120, 140, 165),   # glatter Eis-Asphalt
        curb_a           = ( 80, 120, 180),   # blaue Eisblöcke
        curb_b           = (220, 235, 255),   # weißer Schnee
        bg_fill          = (140, 170, 200),
        centerline       = ( 50, 100, 180),
        hud_bg           = (  5,  10,  25),
        grass_slip       = 0.7,               # stark rutschig – Phase 6
        road_grip        = 0.6,               # wenig Grip auf Eis – Phase 6
        preferred_sectors = ["technical", "chicane"],
    ),

    "night": Theme(
        name             = "night",
        display_name     = "Nacht",
        grass_dark       = ( 15,  30,  15),
        grass_light      = ( 20,  40,  20),
        road_color       = ( 30,  32,  38),
        curb_a           = ( 60, 100, 200),   # Neon-Blau
        curb_b           = (200,  30,  30),   # Neon-Rot
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
        grass_dark       = (180,  80, 140),   # pink-lila
        grass_light      = (220, 130, 180),
        road_color       = (120,  60, 100),
        curb_a           = (255, 100, 180),   # Pink
        curb_b           = (255, 240, 100),   # Gelb
        bg_fill          = (160,  60, 120),
        centerline       = (255, 220, 100),
        hud_bg           = ( 40,  10,  30),
        grass_slip       = 0.0,
        road_grip        = 1.2,
        preferred_sectors = ["mixed", "chicane", "high_speed"],
    ),
}
