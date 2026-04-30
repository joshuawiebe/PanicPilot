# Pickup Entity Pattern

All pickups follow this interface:

## Core Attributes

```python
class BasePickup:
    # Class constants (for all instances)
    RADIUS: int              # Collision radius in pixels (typically 15–40)
    RESPAWN_TIME: float      # Seconds before reappearing after collection
    
    # Instance state
    x: float                 # World X position
    y: float                 # World Y position
    active: bool             # True = visible/collectable; False = respawning
    collected_by: set[int]   # {PLAYER_HOST, PLAYER_CLIENT} for per-player tracking
    _respawn_timer: float    # Countdown; when reaches 0, entity reactivates
    _pvp_mode: bool          # False = solo (active for one), True = PvP (active for all)
```

## Required Methods

### `__init__(x, y, ...)`
Initialization. Must set:
- Position (`self.x`, `self.y`)
- Active state (`self.active = True`)
- Collection set (`self.collected_by = set()`)
- Respawn timer (`self._respawn_timer = 0.0`)
- PvP mode (`self._pvp_mode = False`)

```python
def __init__(self, x: float, y: float, pickup_id: int = 0) -> None:
    self.x = x
    self.y = y
    self.pickup_id = pickup_id
    self.active = True
    self.collected_by: set[int] = set()
    self._respawn_timer = 0.0
    self._pvp_mode = False
```

### `set_pvp_mode(pvp: bool) -> None`
Called by `game.py` to toggle PvP behavior. Affects deactivation logic.

```python
def set_pvp_mode(self, pvp: bool) -> None:
    self._pvp_mode = pvp
```

### `update(dt: float) -> None`
Called every frame. Handle respawn countdown.

```python
def update(self, dt: float) -> None:
    if not self.active:
        self._respawn_timer -= dt
        if self._respawn_timer <= 0:
            self.active = True
            self.collected_by.clear()
```

### `try_pickup(car_x: float, car_y: float, player_id: int) -> bool`
Called when car is nearby. Return `True` if pickup was successfully collected by this player.

Logic flow:
1. If player already collected: return `False`
2. If not active: return `False`
3. If too far away: return `False`
4. Add player to `collected_by`
5. If all players collected (PvP) or any player (solo): deactivate + set respawn timer
6. Return `True`

```python
def try_pickup(self, car_x: float, car_y: float, player_id: int) -> bool:
    # Already collected by this player?
    if player_id in self.collected_by:
        return False
    
    # Is active?
    if not self.active:
        return False
    
    # Close enough?
    dist = math.hypot(car_x - self.x, car_y - self.y)
    if dist >= self.RADIUS + 14:  # +14 for car radius
        return False
    
    # Collect
    self.collected_by.add(player_id)
    
    # Deactivate if all players collected (PvP) or any (solo)
    if self._pvp_mode:
        # PvP: deactivate only when BOTH players collected
        if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
    else:
        # Solo: deactivate immediately
        self.active = False
        self._respawn_timer = self.RESPAWN_TIME
    
    return True
```

### `draw(surface, off_x, off_y, zoom, player_id) -> None`
Called each frame to render. Visual state depends on `active` and `collected_by`.

```python
def draw(self, surface: pygame.Surface, off_x: int, off_y: int,
         zoom: float, player_id: int) -> None:
    sx = int(self.x * zoom) + off_x
    sy = int(self.y * zoom) + off_y
    r = max(3, int(self.RADIUS * zoom))
    
    if not self.active:
        # Inactive: show ghost with countdown
        pygame.draw.circle(surface, GRAY, (sx, sy), r, 1)
        secs = max(0, math.ceil(self._respawn_timer))
        if zoom >= 0.4:
            font = pygame.font.SysFont("Arial", 16, bold=True)
            lbl = font.render(str(secs), True, GRAY)
            surface.blit(lbl, (sx - lbl.get_width()//2, sy - lbl.get_height()//2))
    elif player_id in self.collected_by and self._pvp_mode:
        # PvP: Already collected by this player; faded
        tmp = pygame.Surface((r*2+4, r*2+4), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (100, 100, 100, 70), (r+2, r+2), r)
        surface.blit(tmp, (sx-r-2, sy-r-2))
    else:
        # Active: full brightness
        pygame.draw.circle(surface, BRIGHT_COLOR, (sx, sy), r)
        pygame.draw.circle(surface, OUTLINE_COLOR, (sx, sy), r, 2)
```

### `to_net_dict() -> dict`
Serialize state for networking (host → client).

```python
def to_net_dict(self) -> dict:
    return {
        "id": self.pickup_id,
        "active": self.active,
        "timer": self._respawn_timer,
        "cby": list(self.collected_by),
    }
```

### `apply_net_dict(data: dict) -> None`
Deserialize state from network (client receives from host).

```python
def apply_net_dict(self, data: dict) -> None:
    self.active = bool(data.get("active", True))
    self._respawn_timer = float(data.get("timer", 0.0))
    self.collected_by = set(data.get("cby", []))
```

## Optional Methods

### `try_trigger(...)` (for stateful pickups)
Some pickups (like BoostPad) use `try_trigger()` instead of `try_pickup()` if they need special behavior.

```python
def try_trigger(self, car_x: float, car_y: float, player_id: int) -> bool:
    # Similar logic to try_pickup
    # Often used when effect is immediate (e.g., boost)
```

## Key Differences: PvP vs Solo

### Solo Mode (`_pvp_mode = False`)
- Pickup collected once → disappears for all cars
- Both cars see identical state
- No per-player tracking needed, but `collected_by` still used

```python
# In try_pickup():
self.active = False  # Both cars see it gone immediately
```

### PvP Mode (`_pvp_mode = True`)
- Each player can collect separately
- Pickup visual: greyed out for collectors, bright for others
- Pickup only deactivates when ALL players have collected

```python
# In try_pickup():
if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
    self.active = False  # Only deactivate when both collected

# In draw():
if player_id in self.collected_by:
    # Draw faded for this player
else:
    # Draw bright for other player
```

## Example: MinimalPickup

```python
class MinimalPickup:
    RADIUS = 15
    RESPAWN_TIME = 10.0
    
    def __init__(self, x: float, y: float, pickup_id: int = 0) -> None:
        self.x = x
        self.y = y
        self.pickup_id = pickup_id
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
        if player_id in self.collected_by or not self.active:
            return False
        if math.hypot(car_x - self.x, car_y - self.y) >= self.RADIUS + 14:
            return False
        
        self.collected_by.add(player_id)
        if self._pvp_mode:
            if len(self.collected_by) == 2:
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
        color = (100, 100, 100) if not self.active else (0, 200, 0)
        pygame.draw.circle(surface, color, (sx, sy), r)
    
    def to_net_dict(self) -> dict:
        return {"active": self.active, "timer": self._respawn_timer, "cby": list(self.collected_by)}
    
    def apply_net_dict(self, data: dict) -> None:
        self.active = bool(data.get("active", True))
        self._respawn_timer = float(data.get("timer", 0.0))
        self.collected_by = set(data.get("cby", []))
```
