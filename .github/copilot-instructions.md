---
applyTo: "**/*.py"
---

# PanicPilot Workspace Instructions

**PanicPilot** is a cooperative top-down Mario Kart–like game built in Pygame where two players must communicate: one controls the car (steering/acceleration) while the other sees the map. Both must work together to reach the destination.

## Project Architecture

### Core Systems

| System | Files | Purpose |
|--------|-------|---------|
| **Game Loop** | `game.py` | Main game state, update/draw cycle, mode handling (solo/PvP) |
| **Car Physics** | `car.py`, `car_state.py` | Vehicle movement, acceleration, friction, car classes |
| **Entity System** | `entities.py` | Pickups (fuel, boost, oil), items (boomerangs), particle effects |
| **Rendering** | `camera.py`, `hud.py`, `props.py` | Camera with zoom, UI overlay, decorative environment objects |
| **World** | `track.py`, `walls.py` | Track definition, collision detection, wall geometry |
| **Networking** | `host.py`, `client.py`, `net.py` | TCP socket communication, state sync between players |
| **Input** | `input_state.py` | Keyboard input capture and state |
| **Audio** | `sound_manager.py` | Lazy-loaded sound effects and music |
| **Config** | `settings.py` | Global constants (screen size, physics params, colors) |

### Player Roles

- **PLAYER_HOST** (ID `0`): Typically the driver in networked games; controls car
- **PLAYER_CLIENT** (ID `1`): Typically the navigator; sees map/HUD

Both roles define `player_id` throughout entities and rendering.

## Coding Conventions

### File Headers
Every file starts with a header showing its purpose and version phase:

```python
# =============================================================================
#  filename.py  –  Panic Pilot | Description (Phase X.Y)
# =============================================================================
```

Track phases across the codebase for context on what has been implemented.

### Type Hints & Imports
- Always include `from __future__ import annotations` at the top
- Use full type hints in method signatures: `def update(self, dt: float) -> None:`
- Import organized by: `stdlib` → `third-party (pygame)` → `local modules`

### Constants & Variables
- **Module-level constants**: `UPPERCASE` (e.g., `FOG_RADIUS`, `MAX_PINGS`)
- **Class attributes**: `UPPERCASE` (e.g., `FuelCanister.RADIUS`)
- **Instance attributes**: `lowercase_with_underscores`
- **Private (internal) attributes**: `_leading_underscore` (e.g., `_respawn_timer`, `_rebuild_sprite()`)

### Physics & Gameplay Constants
Found in `settings.py` and module-level constants:

```python
# Typically in settings.py or module top
FUEL_MAX = 100.0
BOOST_ACCEL = 900.0
BOOST_MAX_SPEED = 780.0
_OIL_SPIN_GRIP = 0.08  # Oil slick effect multiplier
SPEED_SCALE_NORMAL = 1.00  # Pause/slow-motion scaling
```

When modifying physics, adjust these constants rather than hardcoding values.

### Entity Pattern
All pickup/effect entities follow this structure:

```python
class Entity:
    # Class constants
    RADIUS = 10
    RESPAWN_TIME = 5.0
    
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.active = True
        self.collected_by: set[int] = set()  # PvP: track which players collected
    
    def update(self, dt: float) -> None:
        """Called each frame with delta time."""
        pass
    
    def draw(self, surface: pygame.Surface, player_id: int = PLAYER_HOST) -> None:
        """Draw self; player_id determines visual state (greyed out if collected by them)."""
        pass
    
    def try_pickup(self, player_id: int) -> bool:
        """Return True if player can collect; False if already collected by them."""
        if player_id in self.collected_by:
            return False  # Already collected by this player
        self.collected_by.add(player_id)
        return True
```

### PvP vs Solo Mode
- **PvP**: Items use `collected_by: set[int]` to track per-player collection
- **Solo**: Items are global (collected once, gone for all)
- Check `self._pvp_mode` or `obj.try_pickup(player_id)` to implement mode logic

### Comments & Documentation
- Comments are often in **German** (Deutsch) mixed with English—maintain this style
- Use `#` for inline clarifications
- Use proper German for game systems (e.g., `Auto` = car, `Treibstoff` = fuel, `Effekt` = effect)
- Phase comments document major changes: `# Phase 6.2 – Effekt-Timer` (Effect Timers)

### Car Class System
Cars have different physics based on class:

```python
# In Car.__init__
car_class: str  # "balanced", "heavy", "light" (customize as needed)
# Affects: acceleration, max_speed, turning_radius, friction
```

Update physics in `Car.apply_input()` based on `self.car_class`.

## Common Tasks

### Adding a New Pickup Entity
1. Create class in `entities.py` inheriting the Entity pattern
2. Add `RADIUS`, `RESPAWN_TIME`, physics constants as class attributes
3. Implement `update()`, `draw()`, `try_pickup()`
4. Add to `game.py` entity list in `Game.__init__()` or spawn dynamically
5. Handle collision in `game.py` update loop with `entity.try_pickup(player_id)`

### Modifying Car Physics
1. Edit constants in `settings.py` or `car.py` module top
2. Adjust in `Car.apply_input()` based on `self.car_class`
3. Test in `game.py` with different speed scales: `SPEED_SCALE_SLOW`, `SPEED_SCALE_NORMAL`

### Networking Changes
1. Modify packet format in `net.py` (serialization)
2. Update `host.py` and `client.py` to send/receive new data
3. Sync state in `Game.update()` when receiving remote state updates
4. Test with `python host.py` and `python client.py` in separate terminals

### Camera/HUD Changes
1. Adjust zoom in `Camera.update()` with `ZOOM_MIN`, `ZOOM_MAX`
2. Modify HUD layout in `HUD.draw()`
3. Test with different `SCREEN_W` and `SCREEN_H` in `settings.py`

### Particle/Visual Effects
1. Use `EntityParticleSystem` in `entities.py` for sparkles, dust
2. Call `emit_boost_sparks()`, `emit_dust()` at appropriate events
3. Integrate with `game.py` particle rendering loop

## Important Patterns

### Delta Time Handling
All `update()` methods take `dt` (delta time in seconds):

```python
def update(self, dt: float) -> None:
    self._timer += dt  # Accumulate real time
    self.x += self.vx * dt  # Frame-rate independent movement
```

### State Synchronization (Networking)
1. **Host** authorizes physics (e.g., car position, speed)
2. **Client** receives state updates and renders
3. Avoid double-applying input: host applies locally, client receives authoritative state
4. Use `CarState` for networked car state

### Draw Order & Layers
In `game.py.draw()`, typical order is:
1. Background/Track
2. Props (decorations, lowest priority)
3. Walls
4. Entities (pickups)
5. Cars
6. Particles
7. HUD/UI (highest priority)

### Pause System
- Set `self._paused = True` in `Game` to halt `update()` calls
- Render pause overlay in `game.py.draw()`
- `speed_scale` affects `dt` application for slow-motion effects

## File Organization

```
PanicPilot/
├── .github/
│   └── copilot-instructions.md  ← You are here
├── main.py                       ← Entry point
├── game.py                       ← Game loop
├── car.py / car_state.py         ← Car physics
├── entities.py                   ← Pickups & effects
├── track.py / walls.py           ← World geometry
├── camera.py / hud.py            ← Rendering
├── host.py / client.py / net.py  ← Networking
├── input_state.py                ← Input handling
├── sound_manager.py              ← Audio
├── particles.py                  ← Particle system
├── props.py                      ← Decorative objects
├── settings.py                   ← Global config
├── theme.py                      ← Colors & style
├── requirements.txt              ← Dependencies
├── assets/sounds/                ← Audio files
└── README.md                     ← Project docs
```

## Key Settings

Found in `settings.py` or module-level constants:

| Setting | Example | Impact |
|---------|---------|--------|
| `SCREEN_W`, `SCREEN_H` | 800, 600 | Display resolution |
| `FUEL_MAX` | 100.0 | Max fuel capacity |
| `MAX_SPEED` | 500.0 | Car top speed |
| `BOOST_ACCEL` | 900.0 | Acceleration boost magnitude |
| `FOG_RADIUS` | ~68 | Map fog-of-war radius |
| `ZOOM_MIN`, `ZOOM_MAX` | 1.0, 3.0 | Camera zoom bounds |
| `PING_DURATION` | 2.5 | How long pings appear on map |
| `SPEED_SCALE_*` | 0.70, 1.00 | Slow-motion (pause) scaling |

## Best Practices

1. **Read before modifying**: Check phase comments and existing patterns to avoid conflicts
2. **Test both modes**: Verify changes work in solo and PvP modes
3. **Physics constants**: Extract magic numbers to `settings.py` or module constants
4. **Type hints**: Always use them—they help catch bugs early
5. **Collision accuracy**: Physics updates must respect `dt` for frame-rate independence
6. **Networking**: Keep `CarState` synchronized; avoid race conditions
7. **Debug with print**: Use `print()` or logging; avoid breakpoints in game loops (can freeze networking)
8. **Commit phases**: Include phase number in commit messages for traceability

## Common Gotchas

- **Forgetting `dt` scaling**: Movement should multiply `dt` to be frame-rate independent
- **PvP vs Solo confusion**: Check `_pvp_mode` or `try_pickup()` logic
- **Networking lag**: Host is authoritative; client renders remote state
- **Particle cleanup**: Ensure expired particles are removed to prevent memory leaks
- **Zoom/FOG interaction**: Map visibility depends on both camera zoom and fog radius
- **Car class inheritance**: Physics changes must account for all car classes

---

**Questions?** Refer to phase comments in files and run `python main.py` to test changes.
