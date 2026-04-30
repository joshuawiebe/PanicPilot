# Common Pickup Effects

Pre-built effect implementations to copy into your pickups or car physics:

## 1. Fuel Restoration

Restore car fuel when pickup collected.

```python
# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_fuel(self, car: Car, amount: float = 20.0) -> None:
    """Restore fuel to the car."""
    car.state.fuel = min(FUEL_MAX, car.state.fuel + amount)
    if _SM is not None:
        _SM.play_sound("pickup_fuel")
    self._entity_particles.emit_boost_sparks(car.x, car.y)
```

## 2. Speed Boost

Increase car speed temporarily.

```python
# In car.py class attribute:
self.boost_timer: float = 0.0

# In Car.apply_input():
boost_bonus = _BOOST_ACCEL if self.boost_timer > 0 else 0.0
if inp.throttle: s.speed += (accel + boost_bonus) * dt * eff_grip

# In Car.update():
if self.boost_timer > 0: self.boost_timer = max(0.0, self.boost_timer - dt)
if self.boost_timer > 0:
    max_speed = max(max_speed, _BOOST_MAX_SPEED)

# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_boost(self, car: Car, duration: float = 2.0) -> None:
    """Apply boost effect."""
    car.boost_timer = duration
    if _SM is not None:
        _SM.play_sound("pickup_boost")
    self._entity_particles.emit_boost_sparks(car.x, car.y)
```

## 3. Oil Slick (Spin/Drift)

Reduce grip and cause spinning/drifting.

```python
# In car.py class attribute:
self.spin_timer: float = 0.0

# In Car.apply_input() and Car.update():
eff_grip = _OIL_SPIN_GRIP if self.spin_timer > 0 else grip_factor

# In Car.update():
if self.spin_timer > 0: self.spin_timer = max(0.0, self.spin_timer - dt)

# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_oil(self, car: Car, duration: float = 1.5) -> None:
    """Apply oil slick effect (reduced grip)."""
    car.spin_timer = duration
    if _SM is not None:
        _SM.play_sound("pickup_oil")
    self._entity_particles.emit_dust(car.x, car.y, car.angle, car.speed, "asphalt")
```

## 4. Shield/Invincibility

Reduce damage or grant temporary invincibility.

```python
# In car.py class attribute:
self.shield_timer: float = 0.0

# In Car.update():
if self.shield_timer > 0: self.shield_timer = max(0.0, self.shield_timer - dt)

# In Car.draw():
if self.shield_timer > 0:
    # Draw shield visual
    shield_alpha = int(100 * (self.shield_timer % 0.5) / 0.5)
    pygame.draw.circle(surface, (0, 200, 255), (screen_x, screen_y), r+8, 2)

# In game.py, handle damage application:
def _apply_damage(self, car: Car, damage: float) -> None:
    """Apply damage, reduced if shield is active."""
    if car.shield_timer > 0:
        damage *= 0.5  # Half damage with shield
        car.shield_timer = 0  # Consume shield
    
    car.state.fuel = max(0, car.state.fuel - damage)

# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_shield(self, car: Car, duration: float = 5.0) -> None:
    """Apply shield/invincibility effect."""
    car.shield_timer = duration
    if _SM is not None:
        _SM.play_sound("pickup_shield")
    self._entity_particles.emit_boost_sparks(car.x, car.y)
```

## 5. Speed Trap (Reduction)

Temporarily reduce car max speed.

```python
# In car.py class attribute:
self.slow_timer: float = 0.0
self.slow_factor: float = 1.0

# In Car.update(), when capping max_speed:
slow_mul = 0.5 if self.slow_timer > 0 else 1.0
fwd_cap = max_speed * slow_mul * min(1.0, effective)

# In Car.update():
if self.slow_timer > 0: self.slow_timer = max(0.0, self.slow_timer - dt)

# In Car.draw():
if self.slow_timer > 0:
    # Draw slow visual (e.g., trails or frost)
    pygame.draw.circle(surface, (100, 150, 200), (screen_x, screen_y), r+3, 1)

# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_slow(self, car: Car, duration: float = 3.0) -> None:
    """Apply speed trap effect (reduced max speed)."""
    car.slow_timer = duration
    if _SM is not None:
        _SM.play_sound("pickup_slow")
```

## 6. Teleport

Warp car to a random safe location.

```python
# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_teleport(self, car: Car) -> None:
    """Teleport car to a random safe location."""
    # Find 10 random locations that aren't colliding with walls
    attempts = 0
    for _ in range(100):
        x = random.randint(100, TRACK_WIDTH - 100)
        y = random.randint(100, TRACK_HEIGHT - 100)
        
        # Check collision with walls
        if self.walls.is_colliding(x, y, car.get_radius()):
            continue
        
        # Safe location found
        car.state.x = x
        car.state.y = y
        if _SM is not None:
            _SM.play_sound("pickup_teleport")
        self._entity_particles.emit_boost_sparks(x, y)
        return
```

## 7. Radar/Map Visibility

Temporarily expand map visibility (fog radius).

```python
# In game.py class attributes:
self.expanded_radar_timer: float = 0.0
self.radar_radius_extra: float = 0.0

# In Game.update():
if self.expanded_radar_timer > 0: self.expanded_radar_timer -= dt

# In Game.draw(), when drawing fog:
radar_r = FOG_RADIUS + self.radar_radius_extra
# Use radar_r instead of FOG_RADIUS for fog calculation

# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_radar(self, car: Car, duration: float = 10.0, extra: float = 50.0) -> None:
    """Expand map visibility temporarily."""
    self.expanded_radar_timer = duration
    self.radar_radius_extra = extra
    if _SM is not None:
        _SM.play_sound("pickup_radar")
```

## 8. Direction Indicator (Ping)

Add a ping to the map at the player's current location.

```python
# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_ping(self, car: Car, player_id: int) -> None:
    """Add a ping marker on the map."""
    self.pings.append([car.x, car.y, player_id, PING_DURATION])
    if _SM is not None:
        _SM.play_sound("pickup_ping")
```

## 9. Damage (Hazard)

Deal damage to car (e.g., spike trap).

```python
# In game.py, after entity.try_trigger() or collision:
def _apply_effect_damage(self, car: Car, damage: float = 15.0) -> None:
    """Deal damage to the car."""
    car.state.fuel = max(0, car.state.fuel - damage)
    if _SM is not None:
        _SM.play_sound("impact_damage")
    
    # Optional: spawn particles
    import random
    for _ in range(5):
        angle = random.randint(0, 360)
        self._entity_particles.emit_dust(car.x, car.y, angle, car.speed, "asphalt")
```

## 10. Multi-Effect Combinations

Combine multiple effects for complex pickups:

```python
# In game.py, after pickup.try_pickup() returns True:
def _apply_effect_superboost(self, car: Car) -> None:
    """Super boost: speed + fuel + particles."""
    car.boost_timer = 3.0
    car.state.fuel = min(FUEL_MAX, car.state.fuel + 15.0)
    
    if _SM is not None:
        _SM.play_sound("pickup_superboost")
    
    # Multiple particle effects
    for _ in range(3):
        self._entity_particles.emit_boost_sparks(car.x, car.y)
    
    # Add ping
    self.pings.append([car.x, car.y, car._player_id, PING_DURATION])
```

## Pattern: Status Effect Helper

Create a generic status effect handler for reuse:

```python
# In car.py:
class StatusEffect:
    def __init__(self, name: str, duration: float, on_update=None, on_expire=None):
        self.name = name
        self.duration = duration
        self.remaining = duration
        self.on_update = on_update
        self.on_expire = on_expire
    
    def update(self, dt: float) -> bool:
        self.remaining -= dt
        if self.on_update:
            self.on_update(self.remaining)
        return self.remaining > 0

# In car.py class:
self.active_effects: list[StatusEffect] = []

# In Car.update():
self.active_effects = [e for e in self.active_effects if e.update(dt)]

# Usage in game.py:
def _apply_effect_custom(self, car: Car, name: str, duration: float) -> None:
    def on_update(remaining):
        if name == "boost":
            # Boost logic
            pass
    
    def on_expire():
        if _SM is not None:
            _SM.play_sound(f"effect_expire_{name}")
    
    effect = StatusEffect(name, duration, on_update, on_expire)
    car.active_effects.append(effect)
```

---

## Copy & Paste Examples

### Minimal Fuel Pickup Integration
```python
# In game.py update():
if isinstance(entity, FuelCanister):
    if entity.try_pickup(car.x, car.y, car._player_id):
        car.state.fuel = min(FUEL_MAX, car.state.fuel + 20.0)
        self._entity_particles.emit_boost_sparks(car.x, car.y)
```

### Minimal Damage Effect
```python
# In game.py, when boomerang hits:
if boomerang.try_hit(car.x, car.y):
    car.state.fuel = max(0, car.state.fuel - 40.0)
```

### Minimal Shield Pickup
```python
# In car.py __init__:
self.shield_timer: float = 0.0

# In game.py:
if isinstance(entity, ItemBox):
    if entity.try_pickup(car.x, car.y, car._player_id):
        car.shield_timer = 5.0
```
