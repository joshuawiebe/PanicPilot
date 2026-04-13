# =============================================================================
#  input_state.py  –  Panic Pilot | Eingabe-Zustand (lokal & netzwerk)
# =============================================================================
#
#  Phase 3-Erweiterung: ping_pos
#    Navigator (Client) klickt auf die Karte → Welt-Koordinaten werden als
#    einmalige Nachricht mitgesendet und nach Empfang automatisch gecleart.
#    Format: (world_x, world_y) als float-Tupel, oder None wenn kein Ping.
#
#  Protokoll-Kompaktheit:
#    Schlüssel "p" wird nur mitgesendet wenn ping_pos nicht None ist,
#    spart Bandbreite im 60 Hz-Tick.
# =============================================================================
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import json


@dataclass
class InputState:
    throttle:    bool  = False  # W – Gas
    brake:       bool  = False  # S – Bremse
    steer_left:  bool  = False  # A – Lenken links
    steer_right: bool  = False  # D – Lenken rechts
    ping_pos: Optional[tuple] = None  # (world_x, world_y) oder None
    use_item: bool = False   # SPACE – Item aus Inventar benutzen

    # ─── Fabrik-Methoden ─────────────────────────────────────────────────────

    @classmethod
    def from_keys(cls, keys) -> InputState:
        """Alle vier Tasten aus pygame-KeyState (Solo-Modus)."""
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
        """Nur Lenkung A/D – Host im Split-Control-Modus."""
        import pygame
        return cls(
            steer_left  = bool(keys[pygame.K_a]),
            steer_right = bool(keys[pygame.K_d]),
            use_item    = bool(keys[pygame.K_SPACE]),
        )

    @classmethod
    def client_keys(cls, keys, ping_pos: Optional[tuple] = None,
                    use_item: bool = False) -> InputState:
        """Gas/Bremse W/S + optionaler Ping + Item-Nutzung – Navigator im Split-Control-Modus."""
        import pygame
        return cls(
            throttle = bool(keys[pygame.K_w]),
            brake    = bool(keys[pygame.K_s]),
            ping_pos = ping_pos,
            use_item = use_item,
        )

    @classmethod
    def merge(cls, a: InputState, b: InputState) -> InputState:
        """
        Kombiniert Host-Input (A) und Client-Input (B) zu einem vollständigen Input.
        Ping vom Client hat Vorrang; use_item wird ge-OR-t.
        """
        return cls(
            throttle    = a.throttle    or b.throttle,
            brake       = a.brake       or b.brake,
            steer_left  = a.steer_left  or b.steer_left,
            steer_right = a.steer_right or b.steer_right,
            ping_pos    = b.ping_pos if b.ping_pos is not None else a.ping_pos,
            use_item    = a.use_item or b.use_item,
        )

    # ─── Serialisierung ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Kompaktes Dict – optionale Felder nur wenn gesetzt (spart Bandbreite)."""
        d: dict = {
            "t": self.throttle,
            "b": self.brake,
            "l": self.steer_left,
            "r": self.steer_right,
        }
        if self.ping_pos is not None:
            d["p"] = [float(self.ping_pos[0]), float(self.ping_pos[1])]
        if self.use_item:
            d["u"] = True
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> InputState:
        raw_ping = d.get("p")
        ping = (float(raw_ping[0]), float(raw_ping[1])) if raw_ping else None
        return cls(
            throttle    = bool(d.get("t", False)),
            brake       = bool(d.get("b", False)),
            steer_left  = bool(d.get("l", False)),
            steer_right = bool(d.get("r", False)),
            ping_pos    = ping,
            use_item    = bool(d.get("u", False)),
        )

    @classmethod
    def from_json(cls, s: str) -> InputState:
        return cls.from_dict(json.loads(s))
