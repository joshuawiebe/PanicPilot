# =============================================================================
#  car.py  –  Panic Pilot | Auto-Physik (Logik) & Rendering (getrennt)
# =============================================================================
from __future__ import annotations
import math
import pygame
from settings   import *
from car_state  import CarState

# Phase 6.2 – Effekt-Konstanten (kein Zirkelbezug zu entities.py)
_OIL_SPIN_GRIP     = 0.08
_BOOST_ACCEL       = 900.0
_BOOST_MAX_SPEED   = 780.0


# ─── Sprite-Aufbau ────────────────────────────────────────────────────────────

def _build_car_surface(body_color: tuple = (210, 45, 45)) -> pygame.Surface:
    """Top-Down-Kart-Sprite, 24×36 px, SRCALPHA. body_color für zweites Auto."""
    W, H = 24, 36
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(surf, body_color, (3, 5, W - 6, H - 10), border_radius=5)
    pygame.draw.rect(surf, LIGHT_BLUE, (5, 7, W - 10, 9), border_radius=2)
    pygame.draw.line(surf, WHITE, (6, 8), (W - 7, 8), 1)
    pygame.draw.rect(surf, (90, 150, 190), (5, H - 15, W - 10, 6), border_radius=2)
    for wx, wy in [(0, 6), (W - 5, 6), (0, H - 15), (W - 5, H - 15)]:
        pygame.draw.rect(surf, (22, 22, 22), (wx, wy, 5, 9), border_radius=2)
        pygame.draw.rect(surf, (80, 80, 80), (wx + 1, wy + 1, 3, 7), border_radius=1)
    # Cockpit-Linie in der Körperfarbe (leicht dunkler)
    dark = tuple(max(0, c - 60) for c in body_color)
    pygame.draw.rect(surf, dark, (W // 2 - 1, 17, 2, H - 23))
    return surf

# Auto-Farben für Host (Rot) und Client (Blau)
CAR_COLOR_HOST   = (210,  45,  45)
CAR_COLOR_CLIENT = ( 30, 100, 210)


class Car:
    """
    Koppelt CarState (Daten) mit Physik-Logik und Rendering.
    body_color steuert die Karosserie-Farbe (Standard: Rot = Host).
    """

    SPEED_DISPLAY_SCALE = 0.47
    SPRITE_W = 24
    SPRITE_H = 36

    def __init__(self, x: float, y: float, angle: float,
                 initial_fuel: float = FUEL_MAX,
                 body_color: tuple = CAR_COLOR_HOST) -> None:
        self.state      = CarState(x=x, y=y, angle=angle, speed=0.0, fuel=initial_fuel)
        self._base_surf = _build_car_surface(body_color)
        # Phase 6.2 – Effekt-Timer
        self.boost_timer: float = 0.0
        self.spin_timer:  float = 0.0
        # Phase 7 – Item-Inventar (max. 1 Item)
        self.inventory: str | None = None

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def x(self) -> float:     return self.state.x
    @property
    def y(self) -> float:     return self.state.y
    @property
    def angle(self) -> float: return self.state.angle
    @property
    def speed(self) -> float: return self.state.speed

    @property
    def speed_kmh(self) -> float:
        return abs(self.state.speed) * self.SPEED_DISPLAY_SCALE

    def get_radius(self) -> int:
        return max(self.SPRITE_W, self.SPRITE_H) // 2

    # ── Input ─────────────────────────────────────────────────────────────────

    def apply_input(self, inp: "InputState", dt: float, grip_factor: float = 1.0) -> None:
        from input_state import InputState
        s = self.state
        # Öl überschreibt theme-Grip komplett
        eff_grip = _OIL_SPIN_GRIP if self.spin_timer > 0 else grip_factor
        can_accel = s.fuel > 0
        if can_accel:
            boost_bonus = _BOOST_ACCEL if self.boost_timer > 0 else 0.0
            if inp.throttle: s.speed += (CAR_ACCEL + boost_bonus) * dt * eff_grip
            if inp.brake:    s.speed -= CAR_BRAKE_DECEL * dt
        speed_abs = abs(s.speed)
        if speed_abs > 5.0:
            t     = min(1.0, speed_abs / CAR_STEER_CUTOFF)
            steer = (CAR_STEER_SPEED_LOW + t * (CAR_STEER_SPEED - CAR_STEER_SPEED_LOW)) * eff_grip
            sign  = 1 if s.speed > 0 else -1
            if inp.steer_left:  s.angle -= steer * dt * sign
            if inp.steer_right: s.angle += steer * dt * sign
        s.angle %= 360.0

    def handle_input(self, keys, dt: float) -> None:
        from input_state import InputState
        self.apply_input(InputState.from_keys(keys), dt)

    def update(self, dt: float, surface: str = "asphalt", grip_factor: float = 1.0) -> None:
        s = self.state
        # Tick Timer
        if self.boost_timer > 0: self.boost_timer = max(0.0, self.boost_timer - dt)
        if self.spin_timer  > 0: self.spin_timer  = max(0.0, self.spin_timer  - dt)

        eff_grip = _OIL_SPIN_GRIP if self.spin_timer > 0 else grip_factor
        friction = CAR_FRICTION * eff_grip
        if s.speed > 0: s.speed = max(0.0, s.speed - friction * dt)
        elif s.speed < 0: s.speed = min(0.0, s.speed + friction * dt)

        if surface == "grass":
            fwd_cap = CAR_MAX_SPEED   * GRASS_SPEED_FACTOR
            rev_cap = CAR_MAX_REVERSE * GRASS_SPEED_FACTOR
        elif surface == "curb":
            fwd_cap = CAR_MAX_SPEED   * CURB_SPEED_FACTOR
            rev_cap = CAR_MAX_REVERSE * CURB_SPEED_FACTOR
        else:
            # Ice-Tuning: floor at 0.78 so it's still fast but controllable
            capped = max(0.78 if eff_grip < 1.0 else 0.2, eff_grip)
            fwd_cap = CAR_MAX_SPEED   * capped
            rev_cap = CAR_MAX_REVERSE * capped

        if self.boost_timer > 0:
            fwd_cap = max(fwd_cap, _BOOST_MAX_SPEED)

        if s.speed > fwd_cap:   s.speed = fwd_cap
        elif s.speed < -rev_cap: s.speed = -rev_cap
        rad  = math.radians(s.angle)
        s.x += math.sin(rad) * s.speed * dt
        s.y -= math.cos(rad) * s.speed * dt

    # ── Rendering ─────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        """
        Sprite-Größe UND Position skalieren mit zoom.
        Sprite wird vor der Rotation skaliert → schrumpft beim Rauszoomen korrekt.
        """
        s  = self.state
        sx = int(s.x * zoom) + off_x
        sy = int(s.y * zoom) + off_y
        # Skalierung: Sprite mit zoom strecken bevor er rotiert wird
        sw = max(4, int(self.SPRITE_W * zoom))
        sh = max(4, int(self.SPRITE_H * zoom))
        if zoom != 1.0:
            scaled = pygame.transform.scale(self._base_surf, (sw, sh))
        else:
            scaled = self._base_surf
        rotated = pygame.transform.rotate(scaled, -s.angle)
        rect    = rotated.get_rect(center=(sx, sy))
        surface.blit(rotated, rect)
