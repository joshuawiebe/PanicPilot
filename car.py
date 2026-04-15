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

def _build_car_surface(body_color: tuple = (210, 45, 45), sprite_width: float = 1.0) -> pygame.Surface:
    """
    Top-Down-Kart-Sprite, 28×42 px, SRCALPHA (größer für bessere Sichtbarkeit).
    body_color: Karosserie-Farbe
    sprite_width: Skalierungsfaktor für die Breite (1.0=normal, 0.80=Speedster schmal, 1.30=Tank breit)
    """
    W, H = 28, 42
    # Adjust width based on class (height stays same for speed visualization)
    W_adjusted = int(W * sprite_width)
    W_offset = (W - W_adjusted) // 2
    
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    # Body adjusts width based on class - nicer rounded corners
    pygame.draw.rect(surf, body_color, 
                     (W_offset + 3, 6, W_adjusted - 6, H - 12), border_radius=7)
    # Cockpit (windshield) - bigger
    cockpit_w = max(4, int((W_adjusted - 8) * 0.65))
    cockpit_x = W // 2 - cockpit_w // 2
    pygame.draw.rect(surf, LIGHT_BLUE, (cockpit_x, 8, cockpit_w, 11), border_radius=3)
    pygame.draw.line(surf, WHITE, (cockpit_x + 1, 9), (cockpit_x + cockpit_w - 2, 9), 2)
    # Spoiler (rear) - bigger
    pygame.draw.rect(surf, (100, 160, 200), (W_offset + 4, H - 18, W_adjusted - 8, 7), border_radius=2)
    # Wheels (adjusted for width) - bigger
    wheel_w = max(4, int(6 * sprite_width))
    wheel_h = 11
    for wx_offset in [W_offset + 2, W - W_offset - wheel_w - 2]:
        for wy in [7, H - 18]:
            pygame.draw.rect(surf, (20, 20, 20), (wx_offset, wy, wheel_w, wheel_h), border_radius=2)
            pygame.draw.rect(surf, (90, 90, 90), (wx_offset + 1, wy + 1, wheel_w - 2, wheel_h - 2), border_radius=1)
    # Cockpit-Linie in der Körperfarbe (leicht dunkler) - für Charakteristik
    dark = tuple(max(0, c - 70) for c in body_color)
    pygame.draw.rect(surf, dark, (W // 2 - 1, 20, 2, H - 28))
    # Top stripe für visuellen Unterschied nach Klasse
    stripe_color = tuple(min(255, c + 80) for c in body_color)
    pygame.draw.rect(surf, stripe_color, (W_offset + 4, 6, W_adjusted - 8, 3), border_radius=1)
    return surf

# Auto-Farben für Host (Rot) und Client (Blau)
CAR_COLOR_HOST   = (210,  45,  45)
CAR_COLOR_CLIENT = ( 30, 100, 210)


class Car:
    """
    Koppelt CarState (Daten) mit Physik-Logik und Rendering.
    Phase 9: Unterstützt verschiedene Auto-Klassen mit unterschiedlichen Physik-Parametern.
    """

    SPEED_DISPLAY_SCALE = 0.47
    SPRITE_W = 28
    SPRITE_H = 42

    def __init__(self, x: float, y: float, angle: float,
                 initial_fuel: float = FUEL_MAX,
                 body_color: tuple = CAR_COLOR_HOST,
                 car_class: str = DEFAULT_CAR_CLASS) -> None:
        self.state      = CarState(x=x, y=y, angle=angle, speed=0.0, fuel=initial_fuel)
        self.car_class  = car_class
        self._class_stats = CAR_CLASSES.get(car_class, CAR_CLASSES[DEFAULT_CAR_CLASS])
        
        # Sprite mit class-spezifischer Breite erzeugen
        sprite_width = self._class_stats.get("sprite_width", 1.0)
        self._base_surf = _build_car_surface(body_color, sprite_width=sprite_width)
        
        # Phase 6.2 – Effekt-Timer
        self.boost_timer: float = 0.0
        self.spin_timer:  float = 0.0
        # Phase 7 – Item-Inventar (max. 1 Item)
        self.inventory: str | None = None

    # ── Class-spezifische Physik ──────────────────────────────────────────────
    
    def get_max_speed(self) -> float:
        """Maximale Vorwärtsgeschwindigkeit basierend auf Klasse."""
        return self._class_stats.get("max_speed", CAR_MAX_SPEED)
    
    def get_accel(self) -> float:
        """Beschleunigungswert basierend auf Klasse."""
        return self._class_stats.get("accel", CAR_ACCEL)
    
    def get_friction(self) -> float:
        """Reibungswert basierend auf Klasse."""
        return self._class_stats.get("friction", CAR_FRICTION)
    
    def get_fuel_drain(self) -> float:
        """Benzinverbrauch-Rate basierend auf Klasse."""
        return self._class_stats.get("fuel_drain", FUEL_DRAIN_RATE)
    
    def get_grass_grip(self) -> float:
        """Grip-Multiplikator auf Gras basierend auf Klasse."""
        return self._class_stats.get("grass_grip", 1.0)
    
    def get_ice_grip(self) -> float:
        """Grip-Multiplikator auf Eis/Öl basierend auf Klasse."""
        return self._class_stats.get("ice_grip", 1.0)

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
            # Use class-specific acceleration
            class_accel = self.get_accel()
            if inp.throttle: s.speed += (class_accel + boost_bonus) * dt * eff_grip
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
        
        # Class-specific friction
        class_friction = self.get_friction()
        friction = class_friction * eff_grip
        if s.speed > 0: s.speed = max(0.0, s.speed - friction * dt)
        elif s.speed < 0: s.speed = min(0.0, s.speed + friction * dt)

        # Class-specific max speeds with terrain modifiers
        class_max_speed = self.get_max_speed()
        
        if surface == "grass":
            grass_grip = self.get_grass_grip()
            fwd_cap = class_max_speed   * GRASS_SPEED_FACTOR * grass_grip
            rev_cap = CAR_MAX_REVERSE   * GRASS_SPEED_FACTOR * grass_grip
        elif surface == "curb":
            fwd_cap = class_max_speed   * CURB_SPEED_FACTOR
            rev_cap = CAR_MAX_REVERSE   * CURB_SPEED_FACTOR
        else:
            # Ice: use class-specific ice grip
            ice_grip = self.get_ice_grip()
            # floor at 0.78 so it's still fast but controllable (modified with ice_grip)
            capped = max(0.78 * ice_grip, ice_grip * 0.2)
            fwd_cap = class_max_speed   * capped
            rev_cap = CAR_MAX_REVERSE   * capped

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
