# Debugging Tips for Pickup Development

Common issues and how to troubleshoot them:

## Issue: Pickup not collecting

**Symptom**: Car passes through pickup; `try_pickup()` never returns True

**Checklist**:
1. Is the pickup initialized in `Game._init_game_objects()`?
   ```python
   self.entities.append(MyPickup(x, y))
   ```

2. Is the pickup's PvP mode set?
   ```python
   entity.set_pvp_mode(self.mode == 3)
   ```

3. Is collision detection being called in `Game.update()`?
   ```python
   if entity.try_pickup(car.x, car.y, player_id):
       # Handle effect
   ```

4. Is the pickup's RADIUS reasonable?
   - Too small: car must hit exact center
   - Too large: pickup detects from too far away
   - Try: `RADIUS = 20` (similar to FuelCanister at 13)

5. Add debug output:
   ```python
   # In Game.update()
   for entity in self.entities:
       if isinstance(entity, MyPickup):
           dist = math.hypot(car.x - entity.x, car.y - entity.y)
           threshold = entity.RADIUS + car.get_radius()
           print(f"MyPickup: dist={dist:.1f}, threshold={threshold:.1f}, active={entity.active}")
   ```

## Issue: Pickup only disappears for one player in PvP

**Symptom**: In PvP mode, pickup disappears after first player collects (solo behavior)

**Fix**: Check `_pvp_mode` logic in `try_pickup()`:

```python
def try_pickup(self, ...):
    # WRONG (solo behavior):
    self.active = False
    self._respawn_timer = self.RESPAWN_TIME
    
    # CORRECT (PvP aware):
    if self._pvp_mode:
        if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
    else:
        self.active = False
        self._respawn_timer = self.RESPAWN_TIME
```

**Debug**:
```python
print(f"PvP mode: {entity._pvp_mode}, collected_by: {entity.collected_by}")
```

## Issue: Pickup not visible / missing from map

**Symptom**: Pickup doesn't appear on screen

**Checklist**:
1. Is the pickup's position within the track bounds?
   ```python
   print(f"Pickup at: ({entity.x}, {entity.y})")
   ```

2. Is `draw()` being called?
   - Add debug print in `draw()` method:
     ```python
     def draw(self, ...):
         print(f"Drawing {self.__class__.__name__} at ({self.x}, {self.y})")
     ```

3. Check camera zoom/offset:
   - If zoom is very high or low, pickup might be off-screen
   - Compare `camera_x`, `camera_y`, `zoom` vs entity position

4. Check Z-order (draw order in `Game.draw()`):
   - Entities drawn before HUD? Before fog?
   - Try drawing directly to test visibility:
     ```python
     pygame.draw.circle(self.screen, (255, 0, 0), (100, 100), 10)
     ```

## Issue: Pickup respawn countdown not showing

**Symptom**: Pickup goes invisible; no countdown timer appears

**Fix**: Check `_draw_ghost()` in `draw()` method:

```python
def draw(self, ...):
    if not self.active:
        self._draw_ghost(surface, sx, sy, r)  # ← Is this being called?
```

Add debug:
```python
def _draw_ghost(self, surface, sx, sy, r):
    print(f"Drawing ghost. Respawn timer: {self._respawn_timer}")
    secs = max(0, math.ceil(self._respawn_timer))
    pygame.draw.circle(surface, GRAY, (sx, sy), r, 1)
    pygame.draw.text(surface, str(secs), (sx, sy))
```

## Issue: Pickup effect not applying

**Symptom**: Car collects pickup but nothing happens

**Checklist**:
1. Is the effect handler being called?
   ```python
   if entity.try_pickup(car.x, car.y, player_id):
       print(f"Pickup collected! Applying effect...")
       self._apply_effect_my_pickup(car, entity)
   ```

2. Does the effect handler exist?
   ```python
   def _apply_effect_my_pickup(self, car, entity):
       print(f"Effect applied to car at ({car.x}, {car.y})")
   ```

3. Is the car's status timer being updated?
   ```python
   # In Car.update():
   if self.status_timer > 0:
       self.status_timer -= dt
       print(f"Status timer: {self.status_timer}")
   ```

4. Is the physics logic using the timer correctly?
   ```python
   # In Car.apply_input():
   if self.status_timer > 0:
       # Apply effect logic
       print(f"Status active: modifying speed")
   ```

## Issue: Networking desync (host and client see different states)

**Symptom**: Host sees pickup collected; client doesn't (or vice versa)

**Fix**: Ensure `to_net_dict()` and `apply_net_dict()` are complete:

```python
def to_net_dict(self) -> dict:
    return {
        "active": self.active,
        "timer": self._respawn_timer,
        "cby": list(self.collected_by),
        # Add custom state if needed:
        # "my_custom_state": self.custom_value,
    }

def apply_net_dict(self, data: dict) -> None:
    self.active = bool(data.get("active", True))
    self._respawn_timer = float(data.get("timer", 0.0))
    self.collected_by = set(data.get("cby", []))
    # Restore custom state:
    # self.custom_value = data.get("my_custom_state", default)
```

**Debug**:
```python
# In Game.update() after network sync:
print(f"After sync: active={entity.active}, collected_by={entity.collected_by}")
```

## Issue: PvP visual state wrong (pickup appears bright when should be faded)

**Symptom**: In PvP mode, pickup is always bright; doesn't fade for collectors

**Fix**: Check `draw()` method's player_id handling:

```python
def draw(self, ..., player_id: int):
    # WRONG (ignores player_id):
    pygame.draw.circle(surface, BRIGHT_COLOR, (sx, sy), r)
    
    # CORRECT (checks if player collected):
    if player_id in self.collected_by and self._pvp_mode:
        self._draw_faded(surface, sx, sy, r)
    else:
        self._draw_active(surface, sx, sy, r)
```

**Debug**:
```python
print(f"Draw: player_id={player_id}, collected_by={self.collected_by}, pvp={self._pvp_mode}")
```

## Issue: Game crashes when creating pickup

**Symptom**: `AttributeError` or `TypeError` when pickup exists

**Debug steps**:
1. Check import in `game.py`:
   ```python
   from entities import MyPickup, ...
   ```

2. Check initialization in `Game._init_game_objects()`:
   ```python
   pickup = MyPickup(100, 200)  # ← Does this line crash?
   pickup.set_pvp_mode(False)    # ← Or this?
   self.entities.append(pickup)  # ← Or this?
   ```

3. Add stack trace:
   ```python
   try:
       pickup = MyPickup(100, 200)
   except Exception as e:
       print(f"Pickup creation failed: {e}")
       import traceback
       traceback.print_exc()
   ```

## Quick Testing Checklist

Before committing a new pickup:

- [ ] Pickup appears visually on map
- [ ] Car can collect it (distance works)
- [ ] Solo mode: pickup disappears for all cars
- [ ] PvP mode: pickup fades for collectors, bright for others
- [ ] Pickup reappears after respawn countdown
- [ ] Effect applies to car physics (if applicable)
- [ ] Effect wears off after duration (if timed)
- [ ] Pause/resume works without breaking pickup
- [ ] Network sync: host and client see same state
- [ ] No crashes on rapid collection (spam-clicking pickup)

## Performance Tips

- Avoid creating new objects in `draw()` every frame:
  ```python
  # BAD (recreates Font every draw):
  font = pygame.font.SysFont("Arial", 16, bold=True)
  
  # GOOD (cache font):
  if self._font is None:
      self._font = pygame.font.SysFont("Arial", 16, bold=True)
  ```

- Don't spam `print()` in tight loops (slows game):
  ```python
  # BAD:
  def draw(self, ...):
      print("Drawing...")  # Called 60 times per second!
  
  # GOOD:
  # Only print when state changes or on rare events
  ```

- Profile large entity lists:
  ```python
  import time
  start = time.time()
  for entity in self.entities:
      entity.update(dt)
  elapsed = time.time() - start
  if elapsed > 0.01:
      print(f"Entity update took {elapsed*1000:.1f}ms")
  ```
