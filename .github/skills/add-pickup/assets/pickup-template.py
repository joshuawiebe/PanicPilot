# Pickup Template

Copy this template and customize for your new pickup:

```python
# =============================================================================
#  [YOUR_PICKUP_NAME]  –  Panic Pilot | Pickup (Phase X.Y)
# =============================================================================
from __future__ import annotations
import math
import pygame
from settings import *

PLAYER_HOST = 0
PLAYER_CLIENT = 1


class YourPickupName:
    """
    [Brief description of what your pickup does]
    
    Effect: [What happens when collected]
    Duration: [How long it lasts, if timed]
    Visual: [How it looks]
    """
    
    RADIUS = 20                # Collision radius (pixels)
    RESPAWN_TIME = 12.0        # Seconds before respawning
    YOR_PICKUP_CONSTANT = 1.0  # Add custom constants here
    
    def __init__(self, x: float, y: float, pickup_id: int = 0) -> None:
        self.x = x
        self.y = y
        self.pickup_id = pickup_id
        self.active = True
        self.collected_by: set[int] = set()
        self._respawn_timer = 0.0
        self._pvp_mode = False
        self._time = 0.0  # Animation timer
    
    def set_pvp_mode(self, pvp: bool) -> None:
        """Called by game.py at initialization."""
        self._pvp_mode = pvp
    
    def update(self, dt: float) -> None:
        """Called every frame."""
        self._time += dt
        
        if not self.active:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self.active = True
                self.collected_by.clear()
    
    def try_pickup(self, car_x: float, car_y: float, player_id: int) -> bool:
        """
        Attempt collection. Return True if successfully picked up by this player.
        """
        # Already collected by this player?
        if player_id in self.collected_by:
            return False
        
        # Is the pickup active?
        if not self.active:
            return False
        
        # Close enough to car?
        dist = math.hypot(car_x - self.x, car_y - self.y)
        if dist >= self.RADIUS + 14:  # +14 for car radius
            return False
        
        # Successfully collected
        self.collected_by.add(player_id)
        
        # Determine deactivation: PvP vs Solo
        if self._pvp_mode:
            # PvP: Deactivate only when BOTH players collected
            if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
                self.active = False
                self._respawn_timer = self.RESPAWN_TIME
        else:
            # Solo: Deactivate immediately
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
        
        return True
    
    def draw(self, surface: pygame.Surface, off_x: int, off_y: int,
             zoom: float, player_id: int) -> None:
        """Render the pickup. Visual state depends on active/collected status."""
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        r = max(3, int(self.RADIUS * zoom))
        
        if not self.active:
            # Inactive: Show respawn countdown
            self._draw_ghost(surface, sx, sy, r)
        elif player_id in self.collected_by and self._pvp_mode:
            # PvP: Already collected by this player; show faded
            self._draw_faded(surface, sx, sy, r)
        else:
            # Active: Full brightness
            self._draw_active(surface, sx, sy, r)
    
    def _draw_active(self, surface: pygame.Surface, sx: int, sy: int, r: int) -> None:
        """Draw active pickup at full brightness."""
        # Example: rotating square
        angle = (self._time * 180) % 360
        pygame.draw.circle(surface, BRIGHT_BLUE, (sx, sy), r)
        pygame.draw.circle(surface, WHITE, (sx, sy), r, 2)
    
    def _draw_faded(self, surface: pygame.Surface, sx: int, sy: int, r: int) -> None:
        """Draw faded version for PvP (already collected by this player)."""
        tmp = pygame.Surface((r*2+4, r*2+4), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (100, 100, 100, 70), (r+2, r+2), r)
        surface.blit(tmp, (sx-r-2, sy-r-2))
    
    def _draw_ghost(self, surface: pygame.Surface, sx: int, sy: int, r: int) -> None:
        """Draw ghost version when respawning (with countdown)."""
        pygame.draw.circle(surface, GRAY, (sx, sy), r, 1)
        secs = max(0, math.ceil(self._respawn_timer))
        font = pygame.font.SysFont("Arial", 16, bold=True)
        lbl = font.render(str(secs), True, GRAY)
        surface.blit(lbl, (sx - lbl.get_width()//2, sy - lbl.get_height()//2))
    
    # ── Networking ─────────────────────────────────────────────────────────
    
    def to_net_dict(self) -> dict:
        """Serialize for sending to client."""
        return {
            "id": self.pickup_id,
            "active": self.active,
            "timer": self._respawn_timer,
            "cby": list(self.collected_by),
        }
    
    def apply_net_dict(self, data: dict) -> None:
        """Deserialize from host."""
        self.active = bool(data.get("active", True))
        self._respawn_timer = float(data.get("timer", 0.0))
        self.collected_by = set(data.get("cby", []))
```

## Customization Points

Replace or modify these sections:

1. **RADIUS & RESPAWN_TIME**: Adjust collision and respawn behavior
2. **__init__()**: Add custom attributes (e.g., `self.duration = 3.0`)
3. **update()**: Add animation logic or effect tracking
4. **try_pickup()**: Add special collection conditions if needed
5. **_draw_active()**: Customize visual appearance (color, rotation, etc.)
6. **to_net_dict() / apply_net_dict()**: Add custom state if needed

## Integration Checklist

After copying and customizing:

1. Add to `entities.py` imports in `game.py`
2. Create instances in `Game._init_game_objects()`
3. Call `entity.set_pvp_mode()` for all entities
4. Add collision detection in `Game.update()` with `entity.try_pickup()`
5. Implement effect handler (if active effect)
6. Test in Solo and PvP modes
7. Verify networking sync
