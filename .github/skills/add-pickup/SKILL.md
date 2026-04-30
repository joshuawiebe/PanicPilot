---
name: add-pickup
description: "Add a new pickup entity (fuel, boost, oil, item, etc.) to PanicPilot. Use when: creating custom pickups, new power-ups, status effects, collectibles. Includes class template, integration steps, and PvP/Solo handling."
argument-hint: "Name and type (e.g., 'ShieldPickup', 'SpeedTrap', 'TeleportZone')"
user-invocable: true
---

# Add a New Pickup to PanicPilot

Create a custom pickup entity (fuel, boost, oil, item, etc.) and integrate it into the game loop with full PvP and Solo support.

## When to Use

- Adding new power-ups or collectibles
- Creating special effects (oil slicks, shields, etc.)
- Implementing status effects triggered by pickups
- Designing new gameplay mechanics

## Overview

All pickups in PanicPilot follow a standard pattern:
- **State**: Position, active/inactive, per-player collection tracking
- **Collection**: `try_pickup()` or `try_trigger()` returns `True` if valid
- **PvP Support**: Tracks which players collected it; deactivates only when all have
- **Respawn**: Automatic respawn after `RESPAWN_TIME` with countdown
- **Rendering**: Visual state varies by active/collected status

## Step-by-Step Procedure

### 1. Design Your Pickup

Define these attributes:

| Attribute | Default | Example |
|-----------|---------|---------|
| **Name** | N/A | `ShieldPickup`, `SpeedTrap` |
| **RADIUS** | 15–40 px | 20 px |
| **RESPAWN_TIME** | 10–15 s | 12.0 s |
| **Effect** | Passive/active | Reduces damage, slows car |
| **Duration** (if timed) | N/A | 3.0 s |
| **Visual** | Color/shape | Blue dome, spinning indicator |

### 2. Create the Class in entities.py

Use the [class template](./assets/pickup-template.py) and adapt to your pickup:

```python
class MyNewPickup:
    RADIUS = 20
    RESPAWN_TIME = 12.0
    
    def __init__(self, x: float, y: float, pickup_id: int = 0) -> None:
        self.x = x
        self.y = y
        self.pickup_id = pickup_id
        self.active = True
        self.collected_by: set[int] = set()
        self._respawn_timer = 0.0
        self._pvp_mode = False
        self._time = 0.0  # For animations
    
    def set_pvp_mode(self, pvp: bool) -> None:
        self._pvp_mode = pvp
    
    def update(self, dt: float) -> None:
        self._time += dt
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
        
        # Deactivate based on PvP/Solo mode
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
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        r = max(3, int(self.RADIUS * zoom))
        
        if not self.active:
            # Ghost state: show respawn countdown
            pygame.draw.circle(surface, GRAY, (sx, sy), r, 1)
            secs = max(0, math.ceil(self._respawn_timer))
            if zoom >= 0.4:
                font = pygame.font.SysFont("Arial", 16, bold=True)
                lbl = font.render(str(secs), True, GRAY)
                surface.blit(lbl, (sx - lbl.get_width()//2, sy - lbl.get_height()//2))
        elif player_id in self.collected_by and self._pvp_mode:
            # PvP: Already collected by this player; show faded version
            tmp = pygame.Surface((r*2+4, r*2+4), pygame.SRCALPHA)
            pygame.draw.circle(tmp, (100, 150, 200, 70), (r+2, r+2), r)
            surface.blit(tmp, (sx-r-2, sy-r-2))
        else:
            # Active state: full-brightness version
            pygame.draw.circle(surface, BRIGHT_COLOR, (sx, sy), r)
            pygame.draw.circle(surface, OUTLINE_COLOR, (sx, sy), r, 2)
    
    def to_net_dict(self) -> dict:
        return {
            "id": self.pickup_id,
            "active": self.active,
            "timer": self._respawn_timer,
            "cby": list(self.collected_by),
        }
    
    def apply_net_dict(self, data: dict) -> None:
        self.active = bool(data.get("active", True))
        self._respawn_timer = float(data.get("timer", 0.0))
        self.collected_by = set(data.get("cby", []))
```

### 3. Update Imports in game.py

Add your class to the import list:

```python
from entities import (
    FuelCanister,
    BoostPad,
    OilSlick,
    ItemBox,
    MyNewPickup,  # <-- Add here
    GreenBoomerang,
    RedBoomerang,
    EntityParticleSystem,
    PLAYER_HOST,
    PLAYER_CLIENT,
    BOOMERANG_SPEED,
)
```

### 4. Initialize in Game.__init__()

Add instances to `self.entities`:

```python
def _init_game_objects(self) -> None:
    # ... existing code ...
    
    # Initialize entities
    self.entities = [
        FuelCanister(400, 300, canister_id=0),
        BoostPad(600, 200, angle=0, pad_id=0),
        MyNewPickup(500, 500, pickup_id=0),  # <-- Add your pickup
        # ... more pickups ...
    ]
    
    # Set PvP mode for all entities
    pvp = self.mode == 3
    for entity in self.entities:
        entity.set_pvp_mode(pvp)
```

### 5. Handle Collision in Game.update()

Detect when the car hits your pickup:

```python
def update(self, dt: float) -> None:
    # ... existing code ...
    
    # Collision detection
    for car in self.cars:
        for entity in self.entities:
            if isinstance(entity, MyNewPickup):
                if entity.try_pickup(car.x, car.y, car._player_id):
                    # Apply pickup effect here
                    self._apply_effect_my_pickup(car, entity)
```

### 6. Implement the Effect

Add a helper method to apply the pickup's effect:

```python
def _apply_effect_my_pickup(self, car: Car, pickup: MyNewPickup) -> None:
    """Apply MyNewPickup effect to the car."""
    car.some_status_timer = SOME_DURATION
    # Example: car.shield_timer = 5.0
    # Or: car.state.fuel = min(FUEL_MAX, car.state.fuel + 20)
    
    # Optional: Play sound
    if _SM is not None:
        _SM.play_sound("pickup_effect")
    
    # Optional: Emit particles
    self._entity_particles.emit_boost_sparks(car.x, car.y)
```

### 7. Update Car Physics (If Status Effect)

If your pickup applies a status effect (slowdown, shield, etc.), modify `car.py`:

```python
class Car:
    def __init__(self, ...):
        # ... existing code ...
        self.shield_timer: float = 0.0  # Example: shield effect
    
    def update(self, dt: float, ...):
        # Update status timers
        if self.shield_timer > 0:
            self.shield_timer -= dt
            # Apply logic (e.g., reduce damage, draw shield visually)
    
    def draw(self, ...):
        # ... existing code ...
        
        # Draw shield if active
        if self.shield_timer > 0:
            pygame.draw.circle(surface, LIGHT_BLUE, (screen_x, screen_y), r+5, 2)
```

### 8. Test Both Game Modes

Run the game and verify:

- **Solo Mode** (Mode 1): Pickup collected once, disappears for all cars
- **PvP Mode** (Mode 3): Pickup only disappears when both players collect it; greyed out for collectors
- **Respawn**: After `RESPAWN_TIME`, pickup reactivates with countdown visible
- **Networking**: Host and Client see the same state; use `to_net_dict()` / `apply_net_dict()`

## Checklist

Use this checklist when adding a new pickup:

- [ ] Class created in `entities.py` with full interface (init, update, try_pickup, draw, to_net_dict, apply_net_dict)
- [ ] Constants defined (RADIUS, RESPAWN_TIME, effect constants)
- [ ] Imported in `game.py`
- [ ] Instantiated in `Game._init_game_objects()`
- [ ] PvP mode set via `entity.set_pvp_mode()`
- [ ] Collision detection in `Game.update()`
- [ ] Effect handler method created (if active effect)
- [ ] Car status timer added (if effect modifies car behavior)
- [ ] Tested in Solo mode
- [ ] Tested in PvP mode
- [ ] Verified respawn countdown
- [ ] Tested with pause/resume
- [ ] Confirmed networking sync (host ↔ client)

## References

- [Entity Pattern](./assets/entity-pattern.md) — Detailed pattern explanation
- [Pickup Template](./assets/pickup-template.py) — Copy-paste template
- [Common Effects](./assets/common-effects.md) — Pre-built effect implementations
- [Debugging Tips](./assets/debugging.md) — Troubleshooting guide

## Examples

See `entities.py` for real implementations:
- **FuelCanister**: Simple respawning pickup with bobbing animation
- **BoostPad**: Timed effect with visual rotation
- **OilSlick**: Status effect that modifies car physics
- **ItemBox**: Random reward mechanism
