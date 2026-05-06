# =============================================================================
#  camera.py  –  Panic Pilot | Scrolling camera with zoom (Phase 4.2)
# =============================================================================
#
#  Coordinate system:
#    World coordinates (wx, wy): absolute position in playfield
#    Screen coordinates (sx, sy): pixels on screen
#
#  Conversion (with zoom):
#    sx = (wx - cam.x) * zoom + SCREEN_W // 2
#    sy = (wy - cam.y) * zoom + SCREEN_H // 2
#
#    s2w (for mouse click → world pos):
#    wx = (sx - SCREEN_W // 2) / zoom + cam.x
#    wy = (sy - SCREEN_H // 2) / zoom + cam.y
#
#    zoom-compatible offset() for blit operations:
#    off_x, off_y  →  screen_x = world_x * zoom + off_x
# =============================================================================
from __future__ import annotations
from settings import SCREEN_W, SCREEN_H

ZOOM_MIN     = 0.10
ZOOM_MAX     = 2.00
ZOOM_DEFAULT = 1.00
ZOOM_STEP    = 0.12   # Step size per mouse wheel tick or key press


class Camera:
    """
    Follows the car smoothly (exponentially damped).
    Supports zoom: Host (Driver) always uses zoom=1.0,
    Navigator (Client) can freely zoom in/out.
    """

    SMOOTH = 7.0   # Follow damping (higher = more direct)

    def __init__(self) -> None:
        self.x    = 0.0   # world coordinate of camera center
        self.y    = 0.0
        self.zoom = ZOOM_DEFAULT

    # ─── Update ──────────────────────────────────────────────────────────────

    def update(self, target_x: float, target_y: float, dt: float,
               target_zoom: float | None = None) -> None:
        """Exponentially damped camera tracking."""
        t = min(1.0, self.SMOOTH * dt)
        self.x += (target_x - self.x) * t
        self.y += (target_y - self.y) * t
        if target_zoom is not None:
            zt = min(1.0, 4.0 * dt)
            self.zoom += (target_zoom - self.zoom) * zt

    def snap(self, target_x: float, target_y: float) -> None:
        """Immediate camera positioning (reset / initialization)."""
        self.x = target_x
        self.y = target_y

    # ─── Zoom ────────────────────────────────────────────────────────────────

    def handle_zoom(self, delta: float) -> None:
        """
        Adjust zoom. delta > 0 = in, delta < 0 = out.
        Called by mouse wheel events or O/P keys.
        """
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom + delta * ZOOM_STEP))

    # ─── Coordinate conversion ────────────────────────────────────────────────

    def w2s(self, wx: float, wy: float) -> tuple[int, int]:
        """World coordinates → screen coordinates (accounts for zoom)."""
        sx = (wx - self.x) * self.zoom + SCREEN_W // 2
        sy = (wy - self.y) * self.zoom + SCREEN_H // 2
        return int(sx), int(sy)

    def s2w(self, sx: float, sy: float) -> tuple[float, float]:
        """
        Screen coordinates → world coordinates (accounts for zoom).
        Critical for pings: click on zoomed-out map lands correctly in the world.
        """
        wx = (sx - SCREEN_W // 2) / self.zoom + self.x
        wy = (sy - SCREEN_H // 2) / self.zoom + self.y
        return wx, wy

    def offset(self) -> tuple[int, int]:
        """
        Camera offset for mass blit operations with zoom.
        Formula: screen_x = world_x * zoom + off_x

        Derivation:
            screen_x = (world_x - cam.x) * zoom + SW//2
                     = world_x * zoom - cam.x * zoom + SW//2
            → off_x  = -cam.x * zoom + SW//2
        """
        off_x = int(-self.x * self.zoom + SCREEN_W // 2)
        off_y = int(-self.y * self.zoom + SCREEN_H // 2)
        return off_x, off_y
