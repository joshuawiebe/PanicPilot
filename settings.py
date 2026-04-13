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
