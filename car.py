# =============================================================================
#  car.py  –  Panic Pilot | Car physics (logic) & rendering (Phase 9)
# =============================================================================
from __future__ import annotations
import math
import pygame
from settings   import *
from car_state  import CarState

# Phase 6.2 – Effect Constants
_OIL_SPIN_GRIP     = 0.08
_BOOST_ACCEL       = 900.0
_BOOST_MAX_SPEED   = 780.0


# ─── Sprite construction ─────────────────────────────────────────────────────────

def _build_car_surface(body_color: tuple = (210, 45, 45),
                       W: int = 24, H: int = 36) -> pygame.Surface:
    """Top-down kart sprite, SRCALPHA. Size variable for classes."""
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.rect(surf, body_color, (3, 5, W - 6, H - 10), border_radius=5)
    pygame.draw.rect(surf, LIGHT_BLUE, (5, 7, W - 10, 9), border_radius=2)
    pygame.draw.line(surf, WHITE, (6, 8), (W - 7, 8), 1)
    pygame.draw.rect(surf, (90, 150, 190), (5, H - 15, W - 10, 6), border_radius=2)
    for wx, wy in [(0, 6), (W - 5, 6), (0, H - 15), (W - 5, H - 15)]:
        pygame.draw.rect(surf, (22, 22, 22), (wx, wy, 5, 9), border_radius=2)
        pygame.draw.rect(surf, (80, 80, 80), (wx + 1, wy + 1, 3, 7), border_radius=1)
    dark = tuple(max(0, c - 60) for c in body_color)
    pygame.draw.rect(surf, dark, (W // 2 - 1, 17, 2, H - 23))
    return surf

# Colors for standard class
CAR_COLOR_HOST   = (210,  45,  45)
CAR_COLOR_CLIENT = ( 30, 100, 210)


class Car:
    """
    Couples CarState with physics logic and rendering.
    car_class controls physics + sprite (Phase 9).
    """

    SPEED_DISPLAY_SCALE = 0.47

    def __init__(self, x: float, y: float, angle: float,
                 initial_fuel: float = FUEL_MAX,
                 body_color: tuple = CAR_COLOR_HOST,
                 car_class: str = "balanced") -> None:
        self.state       = CarState(x=x, y=y, angle=angle, speed=0.0, fuel=initial_fuel)
        self.car_class   = car_class
        self._body_color = body_color
        self._rebuild_sprite()
        # Phase 6.2 – Effect timers
        self.boost_timer: float = 0.0
        self.spin_timer:  float = 0.0
        # Phase 7 – Item inventory
        self.inventory: str | None = None

    def _rebuild_sprite(self) -> None:
        """Rebuilds the sprite (after class change)."""
        cs = CAR_CLASSES.get(self.car_class, CAR_CLASSES["balanced"])
        self.SPRITE_W = cs["sprite_w"]
        self.SPRITE_H = cs["sprite_h"]
        self._base_surf = _build_car_surface(self._body_color,
                                              self.SPRITE_W, self.SPRITE_H)
        self._scale_cache: dict = {}

    def set_class(self, car_class: str) -> None:
        """Changes the vehicle class and rebuilds the sprite."""
        if car_class != self.car_class and car_class in CAR_CLASSES:
            self.car_class = car_class
            self._rebuild_sprite()

    def _stats(self) -> dict:
        return CAR_CLASSES.get(self.car_class, CAR_CLASSES["balanced"])

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
        s  = self.state
        cs = self._stats()
        eff_grip = _OIL_SPIN_GRIP if self.spin_timer > 0 else grip_factor
        can_accel = s.fuel > 0
        if can_accel:
            accel      = CAR_ACCEL * cs["accel_mul"]
            boost_bonus = _BOOST_ACCEL if self.boost_timer > 0 else 0.0
            if inp.throttle: s.speed += (accel + boost_bonus) * dt * eff_grip
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
        s  = self.state
        cs = self._stats()

        if self.boost_timer > 0: self.boost_timer = max(0.0, self.boost_timer - dt)
        if self.spin_timer  > 0: self.spin_timer  = max(0.0, self.spin_timer  - dt)

        eff_grip = _OIL_SPIN_GRIP if self.spin_timer > 0 else grip_factor
        friction = CAR_FRICTION * cs["friction_mul"] * eff_grip
        if s.speed > 0: s.speed = max(0.0, s.speed - friction * dt)
        elif s.speed < 0: s.speed = min(0.0, s.speed + friction * dt)

        max_speed = CAR_MAX_SPEED * cs["speed_mul"]

        if surface == "grass":
            gf = cs["grass_factor"]
            fwd_cap = max_speed   * gf
            rev_cap = CAR_MAX_REVERSE * gf
        elif surface == "curb":
            fwd_cap = max_speed   * CURB_SPEED_FACTOR
            rev_cap = CAR_MAX_REVERSE * CURB_SPEED_FACTOR
        else:
            # Asphalt: grip_mod from class scales theme grip additively
            effective = max(0.78 if eff_grip < 1.0 else 0.2,
                            eff_grip * cs["grip_mod"])
            fwd_cap = max_speed   * min(1.0, effective)
            rev_cap = CAR_MAX_REVERSE * min(1.0, effective)

        if self.boost_timer > 0:
            fwd_cap = max(fwd_cap, _BOOST_MAX_SPEED)

        if s.speed > fwd_cap:   s.speed = fwd_cap
        elif s.speed < -rev_cap: s.speed = -rev_cap
        rad  = math.radians(s.angle)
        s.x += math.sin(rad) * s.speed * dt
        s.y -= math.cos(rad) * s.speed * dt

    # ── Rendering ───────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        s  = self.state
        sx = int(s.x * zoom) + off_x
        sy = int(s.y * zoom) + off_y
        sw = max(4, int(self.SPRITE_W * zoom))
        sh = max(4, int(self.SPRITE_H * zoom))
        key = round(zoom, 2)
        if zoom != 1.0:
            if key not in self._scale_cache:
                if len(self._scale_cache) > 8:
                    del self._scale_cache[next(iter(self._scale_cache))]
                self._scale_cache[key] = pygame.transform.scale(
                    self._base_surf, (sw, sh))
            scaled = self._scale_cache[key]
        else:
            scaled = self._base_surf
        rotated = pygame.transform.rotate(scaled, -s.angle)
        rect    = rotated.get_rect(center=(sx, sy))
        surface.blit(rotated, rect)
