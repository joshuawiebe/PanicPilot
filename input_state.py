# =============================================================================
#  input_state.py  –  Panic Pilot | Eingabe-Zustand (Phase 9)
# =============================================================================
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import json


@dataclass
class InputState:
    throttle:     bool  = False
    brake:        bool  = False
    steer_left:   bool  = False
    steer_right:  bool  = False
    ping_pos:     Optional[tuple] = None
    use_item:     bool  = False   # SPACE
    cycle_class:  bool  = False   # C – Fahrzeugklasse wechseln

    @classmethod
    def from_keys(cls, keys) -> InputState:
        import pygame
        return cls(
            throttle    = bool(keys[pygame.K_w]),
            brake       = bool(keys[pygame.K_s]),
            steer_left  = bool(keys[pygame.K_a]),
            steer_right = bool(keys[pygame.K_d]),
            use_item    = bool(keys[pygame.K_SPACE]),
        )

    @classmethod
    def host_keys(cls, keys) -> InputState:
        import pygame
        return cls(
            steer_left  = bool(keys[pygame.K_a]),
            steer_right = bool(keys[pygame.K_d]),
            use_item    = bool(keys[pygame.K_SPACE]),
        )

    @classmethod
    def client_keys(cls, keys, ping_pos=None,
                    use_item: bool = False, cycle_class: bool = False):
        import pygame
        return cls(
            throttle    = bool(keys[pygame.K_w]),
            brake       = bool(keys[pygame.K_s]),
            ping_pos    = ping_pos,
            use_item    = use_item,
            cycle_class = cycle_class,
        )

    @classmethod
    def merge(cls, a, b):
        return cls(
            throttle    = a.throttle    or b.throttle,
            brake       = a.brake       or b.brake,
            steer_left  = a.steer_left  or b.steer_left,
            steer_right = a.steer_right or b.steer_right,
            ping_pos    = b.ping_pos if b.ping_pos is not None else a.ping_pos,
            use_item    = a.use_item    or b.use_item,
            cycle_class = a.cycle_class or b.cycle_class,
        )

    def to_dict(self) -> dict:
        d: dict = {
            "t": self.throttle, "b": self.brake,
            "l": self.steer_left, "r": self.steer_right,
        }
        if self.ping_pos is not None:
            d["p"] = [float(self.ping_pos[0]), float(self.ping_pos[1])]
        if self.use_item:    d["u"] = True
        if self.cycle_class: d["c"] = True
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict):
        raw = d.get("p")
        ping = (float(raw[0]), float(raw[1])) if raw else None
        return cls(
            throttle    = bool(d.get("t", False)),
            brake       = bool(d.get("b", False)),
            steer_left  = bool(d.get("l", False)),
            steer_right = bool(d.get("r", False)),
            ping_pos    = ping,
            use_item    = bool(d.get("u", False)),
            cycle_class = bool(d.get("c", False)),
        )

    @classmethod
    def from_json(cls, s: str):
        return cls.from_dict(json.loads(s))
