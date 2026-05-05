# =============================================================================
#  walls.py  –  Panic Pilot | Wall and Blocked Zones System
# =============================================================================
#
#  Physics logic (world coordinates, camera-independent):
#    collides(wx, wy, radius) → bool
#    resolve(wx, wy, speed, radius) → (wx, wy, speed)
#
#  Rendering (Phase 4.2 — zoom-aware):
#    draw(surface, off_x, off_y, zoom)
#    screen_x = world_x * zoom + off_x
#    screen_y = world_y * zoom + off_y
#    sizes (width, height, radius) are also scaled with zoom.
# =============================================================================
from __future__ import annotations
import math
import pygame
from settings import SCREEN_W, SCREEN_H, WHITE, RED, GRAY


class BaseWall:
    RESTITUTION = 0.25

    def collides(self, x: float, y: float, radius: float) -> bool:
        raise NotImplementedError

    def resolve(self, x: float, y: float,
                speed: float, radius: float) -> tuple[float, float, float]:
        raise NotImplementedError

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        pass


class ScreenEdgeWall(BaseWall):
    """Screen edge (only when screen_edge=True in WallSystem). Physics in world coords."""

    def __init__(self, margin: int = 20) -> None:
        self.margin = margin

    def collides(self, x: float, y: float, radius: float) -> bool:
        m = self.margin
        return (x - radius < m or x + radius > SCREEN_W - m or
                y - radius < m or y + radius > SCREEN_H - m)

    def resolve(self, x: float, y: float,
                speed: float, radius: float) -> tuple[float, float, float]:
        m = self.margin
        bounced = False
        if x - radius < m:            x = m + radius;                bounced = True
        if x + radius > SCREEN_W - m: x = SCREEN_W - m - radius;     bounced = True
        if y - radius < m:            y = m + radius;                bounced = True
        if y + radius > SCREEN_H - m: y = SCREEN_H - m - radius;     bounced = True
        if bounced:
            speed *= -self.RESTITUTION
        return x, y, speed

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        pass   # unsichtbar


class RectWall(BaseWall):
    """Achsenparallele Rechteck-Barriere in WELTKOORDINATEN."""

    def __init__(self, x: float, y: float, w: float, h: float,
                 color: tuple = GRAY, visible: bool = True) -> None:
        # World coordinates of the wall
        self.wx      = float(x)
        self.wy      = float(y)
        self.ww      = float(w)
        self.wh      = float(h)
        self.color   = color
        self.visible = visible
        # pygame.Rect for physics only (world coords, immutable)
        self._phys_rect = pygame.Rect(int(x), int(y), int(w), int(h))

    def collides(self, x: float, y: float, radius: float) -> bool:
        cx = max(self._phys_rect.left,  min(x, self._phys_rect.right))
        cy = max(self._phys_rect.top,   min(y, self._phys_rect.bottom))
        return math.hypot(x - cx, y - cy) < radius

    def resolve(self, x: float, y: float,
                speed: float, radius: float) -> tuple[float, float, float]:
        if not self.collides(x, y, radius):
            return x, y, speed
        r   = self._phys_rect
        ol  = (x + radius) - r.left
        or_ = r.right  - (x - radius)
        ot  = (y + radius) - r.top
        ob  = r.bottom - (y - radius)
        if min(ol, or_) < min(ot, ob):
            x += -ol if ol < or_ else or_
        else:
            y += -ot if ot < ob else ob
        return x, y, speed * -self.RESTITUTION

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        if not self.visible:
            return
        # Scale world coordinates + dimensions with zoom
        sx = int(self.wx * zoom) + off_x
        sy = int(self.wy * zoom) + off_y
        sw = max(1, int(self.ww * zoom))
        sh = max(1, int(self.wh * zoom))
        pygame.draw.rect(surface, self.color, (sx, sy, sw, sh))
        pygame.draw.rect(surface, WHITE, (sx, sy, sw, sh), max(1, int(2 * zoom)))


class CircleWall(BaseWall):
    """Circular obstacle in WORLD COORDINATES."""

    def __init__(self, cx: float, cy: float, radius: float,
                 color: tuple = RED, visible: bool = True) -> None:
        self.cx      = cx
        self.cy      = cy
        self.radius  = radius
        self.color   = color
        self.visible = visible

    def collides(self, x: float, y: float, car_radius: float) -> bool:
        return math.hypot(x - self.cx, y - self.cy) < self.radius + car_radius

    def resolve(self, x: float, y: float,
                speed: float, car_radius: float) -> tuple[float, float, float]:
        dist = math.hypot(x - self.cx, y - self.cy)
        combined = self.radius + car_radius
        if dist >= combined:
            return x, y, speed
        if dist < 0.001:
            return x + combined, y, speed * -self.RESTITUTION
        nx = (x - self.cx) / dist
        ny = (y - self.cy) / dist
        return self.cx + nx * combined, self.cy + ny * combined, speed * -self.RESTITUTION

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        if not self.visible:
            return
        # Scale position and radius with zoom
        sx = int(self.cx * zoom) + off_x
        sy = int(self.cy * zoom) + off_y
        sr = max(1, int(self.radius * zoom))
        pygame.draw.circle(surface, self.color, (sx, sy), sr)
        pygame.draw.circle(surface, WHITE, (sx, sy), sr, max(1, int(2 * zoom)))


class WallSystem:
    """
    Manages all active walls in a scene.
    screen_edge=False for world-coordinate games (tile track).
    """

    def __init__(self, screen_edge: bool = True) -> None:
        self._walls: list[BaseWall] = []
        self._screen_edge: ScreenEdgeWall | None = ScreenEdgeWall() if screen_edge else None

    def add(self, wall: BaseWall) -> None:
        self._walls.append(wall)

    def clear(self) -> None:
        self._walls.clear()

    def resolve_all(self, x: float, y: float,
                    speed: float, radius: float) -> tuple[float, float, float]:
        for wall in self._walls:
            if wall.collides(x, y, radius):
                x, y, speed = wall.resolve(x, y, speed, radius)
        if self._screen_edge is not None:
            x, y, speed = self._screen_edge.resolve(x, y, speed, radius)
        return x, y, speed

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        """Draw all walls with correct zoom."""
        for wall in self._walls:
            wall.draw(surface, off_x, off_y, zoom)
        if self._screen_edge is not None:
            self._screen_edge.draw(surface, off_x, off_y, zoom)
