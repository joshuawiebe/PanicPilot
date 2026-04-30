---
applyTo: "car.py"
---

# car.py Instructions

**car.py** handles vehicle physics, state management, and rendering. Each car is an instance of the `Car` class which couples a mutable `CarState` with physics logic and sprite rendering.

## Core Architecture

### CarState (car_state.py)
Immutable-ish position/velocity data:
```python
class CarState:
    x: float       # World X position
    y: float       # World Y position
    angle: float   # Heading (degrees)
    speed: float   # Current speed (px/s, signed; + = fwd, - = rev)
    fuel: float    # Remaining fuel (0 to FUEL_MAX)
```

### Car Class
Wraps CarState and adds physics state:
```python
class Car:
    state: CarState        # Position/velocity
    car_class: str         # "balanced", "heavy", "light" → affects physics
    boost_timer: float     # > 0 when boosting (enables BOOST_ACCEL + MAX_SPEED)
    spin_timer: float      # > 0 when spinning (oil slick effect)
    inventory: str | None  # Current item (e.g., "boomerang")
```

## Car Physics

### Classes & Stats
Each car class has multipliers in `CAR_CLASSES` (settings.py):

```python
CAR_CLASSES = {
    "balanced": {
        "accel_mul": 1.0,      # Default acceleration multiplier
        "speed_mul": 1.0,      # Max speed multiplier
        "friction_mul": 1.0,   # Friction multiplier
        "grip_mod": 1.0,       # Grip modifier
        "grass_factor": 0.6,   # Speed on grass
        "sprite_w": 24,        # Sprite width
        "sprite_h": 36,        # Sprite height
        "color_host": (210, 45, 45),
        "color_client": (30, 100, 210),
    },
    # "heavy" and "light" also defined similarly
}
```

### Input Application (apply_input)
```python
def apply_input(self, inp: InputState, dt: float, grip_factor: float = 1.0) -> None:
    1. Check fuel; if 0, disable acceleration
    2. If throttle: speed += (CAR_ACCEL + boost_bonus) * dt * grip_factor
    3. If brake: speed -= CAR_BRAKE_DECEL * dt
    4. At low speeds: reduce steering responsiveness
    5. Apply steering: angle += steer_speed * dt * (fwd ? 1 : -1)
    6. Clamp angle to 0–360°
```

**Key Constants** (module-level):
- `_OIL_SPIN_GRIP = 0.08`: Grip multiplier when spin_timer > 0
- `_BOOST_ACCEL = 900.0`: Bonus acceleration during boost
- `_BOOST_MAX_SPEED = 780.0`: Max speed during boost

### Physics Update (update)
```python
def update(self, dt: float, surface: str = "asphalt", grip_factor: float = 1.0) -> None:
    1. Update timers (reduce boost_timer, spin_timer)
    2. Apply friction: speed → 0 based on surface grip
    3. Clamp speed to max (varies by surface & boost):
       - asphalt: normal max_speed (or _BOOST_MAX_SPEED if boosting)
       - grass: max_speed * grass_factor
       - curb: max_speed * CURB_SPEED_FACTOR
    4. Move car: x += speed * cos(angle) * dt
                 y += speed * sin(angle) * dt
    5. Process fuel: fuel -= FUEL_CONSUMPTION_RATE * dt (if moving fast)
```

**Key Constants** (settings.py):
- `CAR_ACCEL = 200.0`
- `CAR_BRAKE_DECEL = 300.0`
- `CAR_FRICTION = 150.0`
- `CAR_MAX_SPEED = 500.0`
- `CAR_MAX_REVERSE = 200.0`
- `CAR_STEER_SPEED = 360.0` (deg/s)
- `CAR_STEER_SPEED_LOW = 60.0` (deg/s at low speed)
- `CAR_STEER_CUTOFF = 100.0` (threshold for low-speed steering)

## Rendering

### Sprite Building
```python
def _build_car_surface(body_color: tuple, W: int, H: int) -> pygame.Surface:
    # Creates a top-down Kart sprite with:
    # - Body rect (body_color)
    # - Windshield (LIGHT_BLUE)
    # - Four wheels (dark)
    # - Center stripe (darkened body_color)
```

**Sprite dimensions** vary by car class (24x36 for balanced, larger for heavy, smaller for light).

### Drawing
```python
def draw(self, surface: pygame.Surface, camera_x: int, camera_y: int, zoom: float = 1.0) -> None:
    1. Scale sprite rotation by angle
    2. Apply camera offset: screen_x = (car.x + camera_x) * zoom
    3. Draw sprite centered at (screen_x, screen_y)
    4. Optional: draw debug hitbox circle
```

## Common Modifications

### Adjusting Car Physics
Edit `CAR_CLASSES` in `settings.py`:
```python
CAR_CLASSES["balanced"]["accel_mul"] = 1.2  # Increase acceleration
CAR_CLASSES["heavy"]["speed_mul"] = 0.9     # Reduce max speed for heavy cars
```

Or edit module-level constants:
```python
_OIL_SPIN_GRIP = 0.05  # Make oil slick grip worse
_BOOST_MAX_SPEED = 850.0  # Increase boost top speed
```

### Adding a Status Effect
```python
# In Car class:
self.some_timer: float = 0.0

# In update():
if self.some_timer > 0:
    self.some_timer -= dt
    # Apply side effect (reduced grip, lower max speed, etc.)

# Trigger externally:
car.some_timer = SOME_DURATION
```

### Changing Sprite Appearance
Edit `_build_car_surface()`:
```python
# Change body color, add decals, modify wheels, etc.
pygame.draw.rect(surf, body_color, ...)  # Body
pygame.draw.rect(surf, CUSTOM_COLOR, ...)  # Custom element
```

Or change `self._body_color` dynamically before calling `_rebuild_sprite()`.

## Properties & Accessors

| Property | Returns | Notes |
|----------|---------|-------|
| `.x`, `.y`, `.angle`, `.speed` | float | Passthrough to `self.state` |
| `.speed_kmh` | float | Display speed (scaled by `SPEED_DISPLAY_SCALE`) |
| `.get_radius()` | int | Collision radius (based on sprite dimensions) |

## State Networking

### Serialization
```python
def to_net_dict(self) -> dict:
    return self.state.to_net_dict()  # Only CarState is networked

def apply_net_dict(self, data: dict) -> None:
    self.state.apply_net_dict(data)  # Update position/velocity from remote
```

**Note**: Physics effects (boost_timer, spin_timer, inventory) are NOT automatically synced. Handle them in `game.py` or extend the dict if needed.

## Debugging Tips

- **Print position/velocity**: `print(f"Car: pos=({car.x:.1f}, {car.y:.1f}), speed={car.speed:.1f}, fuel={car.fuel:.1f}")`
- **Check timers**: `print(f"boost_timer={car.boost_timer}, spin_timer={car.spin_timer}")`
- **Verify class**: `print(f"car_class={car.car_class}, stats={car._stats()}")`
- **Inspect input**: `print(f"input: throttle={inp.throttle}, brake={inp.brake}, steer={inp.steer_left}/{inp.steer_right}")`
- **Sprite cache**: `print(f"Cached rotations: {len(car._scale_cache)}")`

## Common Gotchas

- **Forgetting dt scaling**: Movement multiplies `dt`; frame-rate independence depends on it
- **Class mismatch**: Car class string must exist in `CAR_CLASSES` or it defaults to "balanced"
- **Sprite rebuilding**: Don't call `_rebuild_sprite()` every frame; only on class change or initialization
- **Angle wrapping**: Ensure angle stays 0–360; use `angle %= 360.0`
- **Reverse steering**: When speed < 0, steering direction inverts (`sign = 1 if speed > 0 else -1`)
- **Grip factor stacking**: Both surface grip and oil slick use `eff_grip` multiplicatively; test interactions
- **Fuel consumption**: High-speed fuel burn only activates at certain speed thresholds; verify in physics loop
