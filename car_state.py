# =============================================================================
#  car_state.py  –  Panic Pilot | Central Car State (Phase-2-Ready)
# =============================================================================
#
#  CarState is the single "source of truth" for all dynamic vehicle data.
#  All fields are JSON-serializable → ready for network transmission.
#
#  Usage:
#      state = CarState(x=640, y=500, angle=270.0, speed=0.0, fuel=100.0)
#      payload = state.to_json()          # → send via socket
#      state   = CarState.from_json(payload)  # ← receive & reconstruct
# =============================================================================
from __future__ import annotations
import json
from dataclasses import dataclass, asdict


@dataclass
class CarState:
    """
    All mutable vehicle data in a compact, serializable structure.

    Coordinate system:
      - angle 0   = North (screen top), clockwise positive
      - speed >0 = forward, speed <0 = backward  [px/s]
      - fuel      = 0 … FUEL_MAX
    """
    x:      float
    y:      float
    angle:  float   # degrees, 0 = North, clockwise
    speed:  float   # px/s
    fuel:   float   # 0 … FUEL_MAX

    # ─── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """All fields as simple dict (float-only, JSON-safe)."""
        return asdict(self)

    def to_json(self) -> str:
        """Compact JSON string for network transmission."""
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

    # ─── Helper methods ────────────────────────────────────────────────────────

    def copy(self) -> CarState:
        """Shallow copy for snapshot / rollback."""
        return CarState(self.x, self.y, self.angle, self.speed, self.fuel)

    def apply_dict(self, d: dict) -> None:
        """Overwrites fields from a dict (in-place, for network update)."""
        if "x"     in d: self.x     = float(d["x"])
        if "y"     in d: self.y     = float(d["y"])
        if "angle" in d: self.angle = float(d["angle"])
        if "speed" in d: self.speed = float(d["speed"])
        if "fuel"  in d: self.fuel  = float(d["fuel"])

    def __repr__(self) -> str:
        return (f"CarState(x={self.x:.1f}, y={self.y:.1f}, "
                f"angle={self.angle:.1f}°, speed={self.speed:.1f}, "
                f"fuel={self.fuel:.1f})")
