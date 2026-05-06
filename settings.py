# =============================================================================
#  settings.py  –  Panic Pilot | All global constants
# =============================================================================

SCREEN_W  = 1920
SCREEN_H  = 1080
FPS       = 60
TITLE     = "Panic Pilot"
FULLSCREEN = False
DISPLAY_W = 1920
DISPLAY_H = 1080
USERNAME = ""

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

# ── Vehicle Physics ──────────────────────────────────────────────────────────
CAR_ACCEL       = 300.0   # +15% compared to Phase 4
CAR_BRAKE_DECEL = 400.0
CAR_MAX_SPEED   = 500.0   # +16% (430 → 500 px/s) – faster racing
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
#  Audio Settings  –  Phase 12
# =============================================================================
#  Values: 0-100  (overridden at runtime by the settings scene)
# =============================================================================
MUSIC_VOLUME: int = 70   # Music volume (0-100)
SFX_VOLUME:   int = 80   # Effects volume (0-100)

# ── Settings persistence ──────────────────────────────────────────────────────

import os as _os
import json as _json
import tempfile as _tempfile


def _get_settings_path() -> str:
    """Return temp-directory path for user_settings.json.

    Works correctly in frozen PyInstaller builds:
      - Windows : %TEMP%\\PanicPilot\\user_settings.json
      - macOS   : /tmp/PanicPilot/user_settings.json
      - Linux   : /tmp/PanicPilot/user_settings.json
    """
    cfg_dir = _os.path.join(_tempfile.gettempdir(), "PanicPilot")
    _os.makedirs(cfg_dir, exist_ok=True)
    return _os.path.join(cfg_dir, "user_settings.json")


_SETTINGS_FILE = _get_settings_path()

# Fallback to the old location (next to the script) for migration
_OLD_SETTINGS_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                   "user_settings.json")

_PERSIST_KEYS  = ("FULLSCREEN", "MUSIC_VOLUME", "SFX_VOLUME", "DISPLAY_W", "DISPLAY_H", "USERNAME")


def _migrate_old_settings() -> None:
    """One-time migration: move settings from old location to new config dir."""
    if _os.path.exists(_SETTINGS_FILE):
        return  # Already migrated or already at new location
    if not _os.path.exists(_OLD_SETTINGS_FILE):
        return  # No old file to migrate
    try:
        with open(_OLD_SETTINGS_FILE, "r", encoding="utf-8") as src:
            data = _json.load(src)
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as dst:
            _json.dump(data, dst, indent=2)
        # Delete old file so it doesn't confuse things
        _os.remove(_OLD_SETTINGS_FILE)
    except (OSError, _json.JSONDecodeError):
        pass  # Migration failed silently; use defaults


def load_settings() -> None:
    """Load persisted user settings from user_settings.json into this module."""
    _migrate_old_settings()
    import sys
    mod = sys.modules[__name__]
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = _json.load(f)
        for key in _PERSIST_KEYS:
            if key in data:
                setattr(mod, key, data[key])
    except (FileNotFoundError, _json.JSONDecodeError, OSError):
        pass  # First run or corrupt file — use defaults


def save_settings() -> None:
    """Persist the current user settings to user_settings.json."""
    import sys
    mod = sys.modules[__name__]
    data = {key: getattr(mod, key) for key in _PERSIST_KEYS}
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2)
    except OSError:
        pass

# =============================================================================
#  Car Classes  –  Phase 9
# =============================================================================
#  Each class defines multipliers relative to the base values above.
#  grip_mod:       factor on the theme-based grip (>1 = more grip)
#  grass_factor:   overrides GRASS_SPEED_FACTOR for this class
# =============================================================================
CAR_CLASSES = {
    "balanced": {
        "display":      "Balanced",
        "color_host":   (210,  45,  45),   # Red
        "color_client": ( 30, 100, 210),   # Blue
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
        "color_client": (255, 200,  50),   # Yellow
        "accel_mul":    1.45,
        "speed_mul":    1.35,
        "friction_mul": 0.65,   # low braking effect → spins out
        "fuel_mul":     1.55,
        "grass_factor": GRASS_SPEED_FACTOR * 0.55,   # much worse on grass
        "grip_mod":     0.60,   # slippery on ice/oil
        "sprite_w":     20, "sprite_h": 42,  # narrow & long
    },
    "tank": {
        "display":      "Tank",
        "color_host":   ( 50, 160,  50),   # Green
        "color_client": ( 30, 120,  30),   # Dark green
        "accel_mul":    0.68,
        "speed_mul":    0.72,
        "friction_mul": 1.40,
        "fuel_mul":     0.75,
        "grass_factor": min(0.92, GRASS_SPEED_FACTOR * 2.3),  # Off-road king
        "grip_mod":     2.00,   # barely slippery on ice/oil
        "sprite_w":     30, "sprite_h": 32,  # wide & flat
    },
}
CLASS_ORDER = ["balanced", "speedster", "tank"]
