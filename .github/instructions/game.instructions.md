---
applyTo: "game.py"
---

# game.py Instructions

**game.py** is the main game loop and orchestrator. It manages game state, all entities, networking, rendering, and player interactions across solo and multiplayer modes.

## Key Concepts

### Game Loop Structure
```python
def update(self, dt: float) -> None:
    if self._paused: return  # Skip physics if paused
    dt *= self.speed_scale   # Apply speed scaling
    
    # 1. Update input/cars
    # 2. Update entities (pickups, particles)
    # 3. Check collisions
    # 4. Sync networking (host sends state)
    # 5. Render scene

def draw(self) -> None:
    # 1. Background/track
    # 2. Props (decorations)
    # 3. Walls
    # 4. Entities (pickups)
    # 5. Cars
    # 6. Particles
    # 7. HUD/UI (topmost)
```

### Mode System
- **Mode 1**: Solo (one car, player HOST only)
- **Mode 2**: Solo with two cars (practice/training)
- **Mode 3**: PvP networked (HOST = driver, CLIENT = navigator)

Check `self.mode` to determine behavior.

### Game Objects
Core mutable collections:

| Attribute | Type | Purpose |
|-----------|------|---------|
| `self.cars` | `list[Car]` | Two cars: HOST at [0], CLIENT at [1] |
| `self.track` | `Track` | Track geometry and spawn points |
| `self.walls` | `WallSystem` | Collision walls |
| `self.entities` | `list` | Pickups (FuelCanister, BoostPad, OilSlick, ItemBox) |
| `self.particles` | `ParticleSystem` | Particle effects (sparks, dust) |
| `self.pings` | `list[list]` | Ping markers (position, player_id, timer) |
| `self._entity_particles` | `EntityParticleSystem` | Special particles from pickups |

### Game States

| State | When | Action |
|-------|------|--------|
| Countdown | Start of race | Display 3-2-1-GO countdown; block input |
| Running | Normal play | Process input, physics, collisions |
| Paused | P key pressed | Freeze physics; show overlay |
| Finished | Crossed finish | Display winner; wait for input |
| Menu/Lobby | Between races | Network handshake, car class selection |

## Common Modifications

### Adding a New Collision Check
When detecting contact between car and entity:

```python
# In Game.update()
for car in self.cars:
    for entity in self.entities:
        dx = entity.x - car.x
        dy = entity.y - car.y
        if math.hypot(dx, dy) < entity.RADIUS + car.get_radius():
            if entity.try_pickup(car.x, car.y, car._player_id):
                # Pickup successful; handle effects
                pass
```

### Spawning New Entities at Runtime
```python
# Add to self.entities
new_pickup = FuelCanister(spawn_x, spawn_y, canister_id=999)
new_pickup.set_pvp_mode(self.mode == 3)  # Sync PvP mode
self.entities.append(new_pickup)
```

### Syncing Networked State
**Host** sends state to Client:
```python
# In Game.update() after physics
if self.mode == 3:  # PvP
    state = {
        "car0": self.cars[0].state.to_net_dict(),
        "car1": self.cars[1].state.to_net_dict(),
        "entities": [e.to_net_dict() for e in self.entities],
    }
    self._net_send(state)
```

**Client** receives updates:
```python
# In Game.handle_network_update(data)
self.cars[0].state.apply_net_dict(data["car0"])
self.cars[1].state.apply_net_dict(data["car1"])
for i, e in enumerate(self.entities):
    e.apply_net_dict(data["entities"][i])
```

### Pause System
- **Toggle pause**: P key in input handling
- **Guard physics**: Check `if self._paused: return` at start of `update()`
- **Render overlay**: Call `draw_pause_overlay()` at end of `draw()`

### Camera Zoom
```python
# Zoom follows car; clipped to bounds
self.camera.update(
    self.cars[0].x, self.cars[0].y,
    SCREEN_W, SCREEN_H,
    self.track
)
# Camera returns: offset_x, offset_y, zoom_level
```

## Constants & Settings

| Constant | Purpose |
|----------|---------|
| `FOG_RADIUS` | Map visibility radius (fog-of-war) |
| `FOG_ALPHA` | Fog overlay opacity (255 = opaque) |
| `PING_DURATION` | How long pings stay visible (seconds) |
| `MAX_PINGS` | Max concurrent pings allowed |
| `SPEED_SCALE_*` | Playback speed multipliers (slow/normal/fast) |
| `COUNTDOWN_STEPS`, `COUNTDOWN_STEP_DURATION` | Pre-race countdown |

## Debugging Tips

- **Print car positions**: `print(f"Car0: {self.cars[0].x}, {self.cars[0].y}")`
- **Check entity active state**: `print([e.active for e in self.entities])`
- **Verify PvP mode**: `print(f"PvP={self.mode==3}, entities_pvp={[e._pvp_mode for e in self.entities]}")`
- **Network sync**: Add logging to `_net_send()` and `handle_network_update()`
- **Collision debug**: Draw circles around entities during testing to visualize hitboxes

## Common Gotchas

- **PvP mode not synced to entities**: After creating an entity, call `entity.set_pvp_mode(self.mode == 3)` or it won't respect per-player collection
- **Forgetting dt scaling**: Always multiply dt by `self.speed_scale` before passing to `Car.update()`
- **Collision order**: Check collisions AFTER physics update, not before
- **Pause in networking**: If paused, don't send network updates; communicate pause state instead
- **Entity cleanup**: Expired particles and inactive entities should be removed to prevent memory leaks
