---
applyTo: "entities.py"
---

# entities.py Instructions

**entities.py** defines all pickups, items, and effects: FuelCanister, BoostPad, OilSlick, ItemBox, Boomerangs, and particle systems. It implements the PvP-aware collection model where items can be per-player or global.

## Core Entity Pattern

All entities follow this interface:

```python
class Entity:
    RADIUS: int              # Collision radius (px)
    RESPAWN_TIME: float      # Seconds before respawning after collected
    
    def __init__(self, x: float, y: float, ...) -> None:
        self.x: float = x
        self.y: float = y
        self.active: bool = True  # Visible/collectable
        self.collected_by: set[int] = set()  # {PLAYER_HOST, PLAYER_CLIENT} or empty
        self._respawn_timer: float = 0.0
        self._pvp_mode: bool = False
    
    def set_pvp_mode(self, pvp: bool) -> None:
        """Toggle PvP mode; affects collection behavior."""
        self._pvp_mode = pvp
    
    def update(self, dt: float) -> None:
        """Called each frame; handle respawn timer."""
        pass
    
    def try_pickup(self, car_x: float, car_y: float, player_id: int) -> bool:
        """Attempt collision. Return True if successfully collected by this player."""
        # Check distance, active state, collection status
        # Add player_id to collected_by if valid
        # Deactivate if both players collected (PvP) or any player (solo)
        pass
    
    def draw(self, surface: pygame.Surface, off_x: int, off_y: int, 
             zoom: float, player_id: int) -> None:
        """Render; visual state depends on active/collected_by/player_id."""
        pass
    
    def to_net_dict(self) -> dict:
        """Serialize for networking."""
        pass
    
    def apply_net_dict(self, data: dict) -> None:
        """Deserialize from network."""
        pass
```

## Collection Model (PvP vs Solo)

### PvP Mode (`_pvp_mode = True`)
- Each entity tracks `collected_by: set[int]`
- `try_pickup()` returns False if **this player** already collected it
- Entity **deactivates** only when **both** players have collected it
- Visual: Item appears greyed out to a player who collected it, bright for the other

### Solo Mode (`_pvp_mode = False`)
- Entity **deactivates** when **any** player collects it
- All players see the same collection state immediately

```python
# In entity update/collection:
if self._pvp_mode:
    # PvP: needs both players
    if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
        self.active = False
        self._respawn_timer = self.RESPAWN_TIME
else:
    # Solo: needs one player
    self.active = False
    self._respawn_timer = self.RESPAWN_TIME
```

## Built-in Entities

### FuelCanister
```python
RADIUS = 13
RESPAWN_TIME = 12.0
BOB_SPEED = 2.0        # Bobbing animation frequency
BOB_AMOUNT = 2         # Bobbing amplitude (pixels)

try_pickup(car_x, car_y, player_id) -> bool
    # Restores FUEL_ADD to car.state.fuel
    # Visual: Orange glowing square with "F" label
    # Inactive: Dimmed grey circle with respawn countdown
```

### BoostPad
```python
RADIUS = 30
BOOST_SPEED = 300.0    # Velocity boost (px/s additive)
BOOST_ACCEL = 900.0    # Acceleration bonus during boost
BOOST_DURATION = 1.5   # Duration of boost effect (seconds)
BOOST_MAX_SPEED = 780.0
RESPAWN_TIME = 10.0

try_trigger(car_x, car_y, player_id) -> bool
    # Activates: car.boost_timer = BOOST_DURATION
    # Effect: Higher acceleration + top speed for duration
    # Visual: Rotating yellow/orange stripe at self.angle
    # Inactive: Dimmed grey stripe with countdown
```

### OilSlick
```python
RADIUS = 40
DURATION = 3.0       # How long the oil persists
RESPAWN_TIME = 8.0

try_hit(car_x, car_y, player_id) -> bool
    # Activates: car.spin_timer = SPIN_EFFECT_DURATION
    # Effect: Reduces grip (eff_grip = _OIL_SPIN_GRIP = 0.08)
    # Visual: Dark semi-transparent blob
    # Decays: Fades over DURATION seconds
    # Inactive: Invisible/ghost state with countdown
```

### ItemBox
```python
RADIUS = 16
RESPAWN_TIME = 15.0

try_pickup(car_x, car_y, player_id) -> bool
    # Awards random item: GreenBoomerang or RedBoomerang
    # Visual: Spinning question-mark box
    # Inactive: Dimmed grey box with countdown
```

### Boomerangs (GreenBoomerang, RedBoomerang)
```python
GREEN_BOOMERANG_DMG = 40.0   # Damage when hitting car
RED_BOOMERANG_DMG = 60.0
BOOMERANG_SPEED = 400.0       # Velocity (px/s)
BOOMERANG_RETURN_TIME = 5.0   # Time before returning to thrower

try_hit(car_x, car_y) -> bool
    # Hits if car within RADIUS
    # Damage: Reduces car.state.fuel by GREEN/RED_DMG
    # Returns: Boomerang flies back to thrower; disappears on impact
    # Visual: Green/red curved projectile with spin animation
```

## EntityParticleSystem

Special particle effects bound to entities:

```python
class EntityParticleSystem:
    def emit_boost_sparks(self, x: float, y: float) -> None:
        """Yellow sparks when collecting a boost pad."""
    
    def emit_dust(self, x: float, y: float, angle: float, speed: float,
                  surface_type: str = "asphalt") -> None:
        """Dust/ice clouds behind car tires.
        surface_type: "asphalt" (grey), "grass" (brown), "ice" (white)
        """
    
    def update(self, dt: float) -> None:
        """Update all particles; remove expired."""
    
    def draw(self, surface: pygame.Surface, offset_x: int, offset_y: int,
             zoom: float) -> None:
        """Draw all particles."""
```

**Usage in game.py**:
```python
# After boost pickup
entity_particles.emit_boost_sparks(car.x, car.y)

# After tire movement
entity_particles.emit_dust(car.x, car.y, car.angle, car.speed, "asphalt")
```

## Common Modifications

### Adding a New Pickup
1. **Create class** in `entities.py`:
```python
class MyPickup:
    RADIUS = 20
    RESPAWN_TIME = 10.0
    
    def __init__(self, x: float, y: float, pickup_id: int = 0):
        self.x = x
        self.y = y
        self.active = True
        self.collected_by: set[int] = set()
        self._respawn_timer = 0.0
        self._pvp_mode = False
    
    def set_pvp_mode(self, pvp: bool) -> None:
        self._pvp_mode = pvp
    
    def update(self, dt: float) -> None:
        if not self.active:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self.active = True
                self.collected_by.clear()
    
    def try_pickup(self, car_x: float, car_y: float, player_id: int) -> bool:
        if player_id in self.collected_by:
            return False
        if not self.active:
            return False
        if math.hypot(car_x - self.x, car_y - self.y) >= self.RADIUS + 14:
            return False
        self.collected_by.add(player_id)
        if self._pvp_mode:
            if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
                self.active = False
                self._respawn_timer = self.RESPAWN_TIME
        else:
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
        return True
    
    def draw(self, surface: pygame.Surface, off_x: int, off_y: int, 
             zoom: float, player_id: int) -> None:
        sx, sy = int(self.x * zoom) + off_x, int(self.y * zoom) + off_y
        r = max(3, int(self.RADIUS * zoom))
        # Draw your visual representation
        pygame.draw.rect(surface, CUSTOM_COLOR, (sx - r, sy - r, r*2, r*2))
    
    def to_net_dict(self) -> dict:
        return {"active": self.active, "timer": self._respawn_timer, "cby": list(self.collected_by)}
    
    def apply_net_dict(self, data: dict) -> None:
        self.active = bool(data.get("active", True))
        self._respawn_timer = float(data.get("timer", 0.0))
        self.collected_by = set(data.get("cby", []))
```

2. **Add to game.py**:
```python
# In Game.__init__()
self.entities.append(MyPickup(x, y, pickup_id=0))
self.entities[-1].set_pvp_mode(self.mode == 3)

# In Game.update()
for entity in self.entities:
    if isinstance(entity, MyPickup):
        if entity.try_pickup(car.x, car.y, car._player_id):
            # Handle effect
            pass
```

### Tweaking Timings
```python
# In constants at top of entities.py
RESPAWN_TIME = 15.0        # After collected
BOOST_DURATION = 2.0       # How long effect lasts
BOOMERANG_RETURN_TIME = 6.0  # Before flying back
```

### Visual Customization
Edit the `draw()` method:
```python
# Change colors, add effects, resize hitbox visualization, etc.
pygame.draw.circle(surface, CUSTOM_COLOR, (sx, sy), r)
```

## Debugging Tips

- **Check active/collected state**: `print(f"active={e.active}, collected_by={e.collected_by}")`
- **Respawn timer**: `print(f"respawn_timer={e._respawn_timer}")`
- **PvP mode**: `print(f"pvp_mode={e._pvp_mode}")`
- **Collision distance**: `print(f"dist={math.hypot(car_x - e.x, car_y - e.y)}, threshold={e.RADIUS + 14}")`
- **Visual bounds**: Draw debug rectangles around entity RADIUS during testing

## Common Gotchas

- **PvP mode not set**: After creating entity in game.py, call `entity.set_pvp_mode(self.mode == 3)` or it defaults to solo behavior
- **Respawn timer confusion**: Timer counts DOWN; when it reaches 0, entity reactivates
- **Collision radius**: `try_pickup()` uses `entity.RADIUS + car.get_radius()` for distance; adjust RADIUS if hitting is too easy/hard
- **Network desync**: Call `apply_net_dict()` on ALL entities each update, even if not directly picked up
- **Particle cleanup**: Expired particles must be removed from `EntityParticleSystem` to prevent memory leaks
- **Double-collection solo mode**: Check `self._pvp_mode` before deactivating; don't deactivate until collection is confirmed
