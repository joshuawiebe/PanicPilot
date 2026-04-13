# =============================================================================
#  car_state.py  –  Panic Pilot | Zentraler Auto-Zustand (Phase-2-Ready)
# =============================================================================
#
#  CarState ist der einzige „Wahrheitsträger" für alle dynamischen Fahrzeugdaten.
#  Alle Felder sind JSON-serialisierbar → bereit für Netzwerk-Übertragung.
#
#  Verwendung:
#      state = CarState(x=640, y=500, angle=270.0, speed=0.0, fuel=100.0)
#      payload = state.to_json()          # → verschicken per Socket
#      state   = CarState.from_json(payload)  # ← empfangen & rekonstruieren
# =============================================================================
from __future__ import annotations
import json
from dataclasses import dataclass, asdict


@dataclass
class CarState:
    """
    Alle veränderlichen Fahrzeugdaten in einer kompakten, serialisierbaren Struktur.

    Koordinatensystem:
      - angle 0   = Norden (Bildschirm oben), clockwise positiv
      - speed > 0 = vorwärts, speed < 0 = rückwärts  [px/s]
      - fuel      = 0 … FUEL_MAX
    """
    x:      float
    y:      float
    angle:  float   # degrees, 0 = Nord, clockwise
    speed:  float   # px/s
    fuel:   float   # 0 … FUEL_MAX

    # ─── Serialisierung ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Alle Felder als einfaches Dict (float-only, JSON-safe)."""
        return asdict(self)

    def to_json(self) -> str:
        """Kompakter JSON-String für Netzwerk-Übertragung."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> CarState:
        return cls(
            x     = float(d["x"]),
            y     = float(d["y"]),
            angle = float(d["angle"]),
            speed = float(d["speed"]),
            fuel  = float(d["fuel"]),
        )

    @classmethod
    def from_json(cls, s: str) -> CarState:
        return cls.from_dict(json.loads(s))

    # ─── Hilfsmethoden ───────────────────────────────────────────────────────

    def copy(self) -> CarState:
        """Flache Kopie für Snapshot / Rollback."""
        return CarState(self.x, self.y, self.angle, self.speed, self.fuel)

    def apply_dict(self, d: dict) -> None:
        """Überschreibt Felder aus einem Dict (in-place, für Netzwerk-Update)."""
        if "x"     in d: self.x     = float(d["x"])
        if "y"     in d: self.y     = float(d["y"])
        if "angle" in d: self.angle = float(d["angle"])
        if "speed" in d: self.speed = float(d["speed"])
        if "fuel"  in d: self.fuel  = float(d["fuel"])

    def __repr__(self) -> str:
        return (f"CarState(x={self.x:.1f}, y={self.y:.1f}, "
                f"angle={self.angle:.1f}°, speed={self.speed:.1f}, "
                f"fuel={self.fuel:.1f})")
