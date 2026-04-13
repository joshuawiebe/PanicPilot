# =============================================================================
#  camera.py  –  Panic Pilot | Scrolling-Kamera mit Zoom (Phase 4.2)
# =============================================================================
#
#  Koordinatensystem:
#    Weltkoordinaten (wx, wy): absolute Position im Spielfeld
#    Bildschirmkoordinaten (sx, sy): Pixel auf dem Bildschirm
#
#  Konversion (mit Zoom):
#    sx = (wx - cam.x) * zoom + SCREEN_W // 2
#    sy = (wy - cam.y) * zoom + SCREEN_H // 2
#
#    s2w (für Mausklick → Weltpos):
#    wx = (sx - SCREEN_W // 2) / zoom + cam.x
#    wy = (sy - SCREEN_H // 2) / zoom + cam.y
#
#    zoom-kompatibler offset() für blit-Operationen:
#    off_x, off_y  →  screen_x = world_x * zoom + off_x
# =============================================================================
from __future__ import annotations
from settings import SCREEN_W, SCREEN_H

ZOOM_MIN     = 0.10
ZOOM_MAX     = 2.00
ZOOM_DEFAULT = 1.00
ZOOM_STEP    = 0.12   # Schrittweite pro Mausrad-Tick oder Tastendruck


class Camera:
    """
    Folgt dem Auto flüssig (exponentiell gedämpft).
    Unterstützt Zoom: Host (Driver) nutzt immer zoom=1.0,
    Navigator (Client) kann frei rein-/rauszoomen.
    """

    SMOOTH = 7.0   # Folge-Dämpfung (höher = direkter)

    def __init__(self) -> None:
        self.x    = 0.0   # Weltkoordinate der Kameramitte
        self.y    = 0.0
        self.zoom = ZOOM_DEFAULT

    # ─── Update ──────────────────────────────────────────────────────────────

    def update(self, target_x: float, target_y: float, dt: float) -> None:
        """Exponentiell gedämpfte Kamera-Verfolgung."""
        t = min(1.0, self.SMOOTH * dt)
        self.x += (target_x - self.x) * t
        self.y += (target_y - self.y) * t

    def snap(self, target_x: float, target_y: float) -> None:
        """Sofortige Kamera-Positionierung (Reset / Initialisierung)."""
        self.x = target_x
        self.y = target_y

    # ─── Zoom ────────────────────────────────────────────────────────────────

    def handle_zoom(self, delta: float) -> None:
        """
        Zoom anpassen. delta > 0 = rein, delta < 0 = raus.
        Wird von Mausrad-Events oder O/P-Tasten aufgerufen.
        """
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom + delta * ZOOM_STEP))

    # ─── Koordinaten-Konversion ───────────────────────────────────────────────

    def w2s(self, wx: float, wy: float) -> tuple[int, int]:
        """Weltkoordinaten → Bildschirmkoordinaten (berücksichtigt Zoom)."""
        sx = (wx - self.x) * self.zoom + SCREEN_W // 2
        sy = (wy - self.y) * self.zoom + SCREEN_H // 2
        return int(sx), int(sy)

    def s2w(self, sx: float, sy: float) -> tuple[float, float]:
        """
        Bildschirmkoordinaten → Weltkoordinaten (berücksichtigt Zoom).
        Kritisch für Pings: Klick bei ausgezoomter Karte landet korrekt in der Welt.
        """
        wx = (sx - SCREEN_W // 2) / self.zoom + self.x
        wy = (sy - SCREEN_H // 2) / self.zoom + self.y
        return wx, wy

    def offset(self) -> tuple[int, int]:
        """
        Kamera-Versatz für Massen-Blit-Operationen mit Zoom.
        Formel: screen_x = world_x * zoom + off_x

        Herleitung:
            screen_x = (world_x - cam.x) * zoom + SW//2
                     = world_x * zoom - cam.x * zoom + SW//2
            → off_x  = -cam.x * zoom + SW//2
        """
        off_x = int(-self.x * self.zoom + SCREEN_W // 2)
        off_y = int(-self.y * self.zoom + SCREEN_H // 2)
        return off_x, off_y
