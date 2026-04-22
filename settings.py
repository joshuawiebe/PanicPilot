# =============================================================================
#  settings.py  –  Panic Pilot | Alle globalen Konstanten
# =============================================================================

SCREEN_W  = 1280
SCREEN_H  = 720
FPS       = 60
TITLE     = "Panic Pilot"

BLACK       = (  0,   0,   0)
WHITE       = (255, 255, 255)
GRAY        = (100, 100, 100)
DARK_GRAY   = ( 35,  35,  35)
ROAD_GRAY   = ( 70,  72,  78)
GRASS_DARK  = ( 38,  90,  38)
GRASS_LIGHT = ( 50, 110,  45)
RED         = (200,  30,  30)
CURB_RED    = (210,  40,  40)
CURB_WHITE  = (230, 230, 230)
GREEN       = ( 50, 200,  50)
YELLOW      = (255, 220,   0)
ORANGE      = (255, 140,   0)
BLUE        = ( 30, 100, 200)
LIGHT_BLUE  = (130, 200, 255)
CYAN        = (  0, 200, 210)
HUD_BG      = (  8,  12,  22)

# ── Fahrzeug-Physik ───────────────────────────────────────────────────────────
CAR_ACCEL       = 300.0   # +15 % gegenüber Phase 4
CAR_BRAKE_DECEL = 400.0
CAR_MAX_SPEED   = 500.0   # +16 % (430 → 500 px/s) – rasanteres Rennen
CAR_MAX_REVERSE = 150.0
CAR_FRICTION    = 130.0

CAR_STEER_SPEED     = 138.0
CAR_STEER_SPEED_LOW =  58.0
CAR_STEER_CUTOFF    =  45.0

GRASS_SPEED_FACTOR = 0.40
CURB_SPEED_FACTOR  = 0.75

# ── Benzin ────────────────────────────────────────────────────────────────────
FUEL_MAX            = 100.0
FUEL_DRAIN_RATE     =   7.6    # -20 % (war 9.5) – besser spielbar im PvP
FUEL_CANISTER_VALUE =  38.0
NUM_CANISTERS       =   3

MAX_PARTICLES = 120

# =============================================================================
#  Audio-Einstellungen  –  Phase 12
# =============================================================================
#  Werte: 0-100  (werden zur Laufzeit durch die Einstellungs-Szene überschrieben)
# =============================================================================
MUSIC_VOLUME: int = 70   # Musik-Lautstärke (0-100)
SFX_VOLUME:   int = 80   # Effekt-Lautstärke (0-100)

# =============================================================================
#  Car-Klassen  –  Phase 9
# =============================================================================
#  Jede Klasse definiert Multiplikatoren relativ zu den Basis-Werten oben.
#  grip_mod:       Faktor auf den theme-basierten Grip (>1 = mehr Grip)
#  grass_factor:   Überschreibt GRASS_SPEED_FACTOR für diese Klasse
# =============================================================================
CAR_CLASSES = {
    "balanced": {
        "display":      "Balanced",
        "color_host":   (210,  45,  45),   # Rot
        "color_client": ( 30, 100, 210),   # Blau
        "accel_mul":    1.00,
        "speed_mul":    1.00,
        "friction_mul": 1.00,
        "fuel_mul":     1.00,
        "grass_factor": GRASS_SPEED_FACTOR,
        "grip_mod":     1.00,
        "sprite_w":     24, "sprite_h": 36,
    },
    "speedster": {
        "display":      "Speedster",
        "color_host":   (255, 140,   0),   # Orange
        "color_client": (255, 200,  50),   # Gelb
        "accel_mul":    1.45,
        "speed_mul":    1.35,
        "friction_mul": 0.65,   # wenig Bremswirkung → schleudert
        "fuel_mul":     1.55,
        "grass_factor": GRASS_SPEED_FACTOR * 0.55,   # viel schlechter auf Gras
        "grip_mod":     0.60,   # rutschig auf Eis/Öl
        "sprite_w":     20, "sprite_h": 42,  # schmal & lang
    },
    "tank": {
        "display":      "Tank",
        "color_host":   ( 50, 160,  50),   # Grün
        "color_client": ( 30, 120,  30),   # Dunkelgrün
        "accel_mul":    0.68,
        "speed_mul":    0.72,
        "friction_mul": 1.40,
        "fuel_mul":     0.75,
        "grass_factor": min(0.92, GRASS_SPEED_FACTOR * 2.3),  # Offroad-King
        "grip_mod":     2.00,   # kaum rutschig auf Eis/Öl
        "sprite_w":     30, "sprite_h": 32,  # breit & flach
    },
}
CLASS_ORDER = ["balanced", "speedster", "tank"]
