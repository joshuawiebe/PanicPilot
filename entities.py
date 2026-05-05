# =============================================================================
#  entities.py  –  Panic Pilot | Pickups & Effects (Phase 6.2b)
# =============================================================================
#
#  Individual collection (PvP):
#    Each object has collected_by: set[int].
#    try_pickup / try_trigger → True if player has NOT yet collected.
#    Visually: grayed out for this player, fully visible for the other.
#    Globally inactive only when BOTH have collected (PvP) or one (solo).
#
#  draw(player_id=…):
#    PLAYER_HOST (0) / PLAYER_CLIENT (1) controls the visual status.
#
#  EntityParticleSystem:
#    emit_boost_sparks(x, y)           – yellow sparks on boost pickup
#    emit_dust(x, y, angle, speed, surface_type)  – dust/ice behind wheels
# =============================================================================
from __future__ import annotations
import math
import random
import pygame
from settings import *

PLAYER_HOST   = 0
PLAYER_CLIENT = 1


# =============================================================================
#  FuelCanister
# =============================================================================
class FuelCanister:
    RADIUS        = 13
    RESPAWN_TIME  = 12.0
    BOB_SPEED     = 2.0
    BOB_AMOUNT    = 2
    PLAYER_HOST   = PLAYER_HOST
    PLAYER_CLIENT = PLAYER_CLIENT

    def __init__(self, x: float, y: float, canister_id: int = 0) -> None:
        self.x              = x
        self.y              = y
        self.canister_id    = canister_id
        self.active         = True
        self._respawn_timer = 0.0
        self._time          = 0.0
        self._font: pygame.font.Font | None = None
        self.collected_by: set[int] = set()
        self._pvp_mode      = False

    def set_pvp_mode(self, pvp: bool) -> None:
        self._pvp_mode = pvp

    def update(self, dt: float) -> None:
        self._time += dt
        if not self.active:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self.active = True
                self.collected_by.clear()

    def try_pickup(self, car_x: float, car_y: float,
                   player_id: int = PLAYER_HOST) -> bool:
        if player_id in self.collected_by:
            return False
        if not self.active:
            return False
        if math.hypot(car_x - self.x, car_y - self.y) >= self.RADIUS + 16:
            return False
        self.collected_by.add(player_id)
        if self._pvp_mode:
            if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
                self.active = False
                self._respawn_timer = self.RESPAWN_TIME
        else:
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
        return True

    # ── Network ─────────────────────────────────────────────────────────────────

    def to_net_dict(self) -> dict:
        return {
            "id":     self.canister_id,
            "active": self.active,
            "timer":  self._respawn_timer,
            "cby":    list(self.collected_by),
        }

    def apply_net_dict(self, d: dict) -> None:
        self.active         = bool(d.get("active", True))
        self._respawn_timer = float(d.get("timer", 0.0))
        self.collected_by   = set(d.get("cby", []))

    # ── Rendering ────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0,
             player_id: int = PLAYER_HOST) -> None:
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        if not self.active:
            self._draw_ghost(surface, sx, sy, zoom)
            return
        if player_id in self.collected_by:
            self._draw_faded(surface, sx, sy, zoom)
            return
        bob = int(math.sin(self._time * self.BOB_SPEED * math.pi * 2) * self.BOB_AMOUNT)
        cx, cy = sx, sy + bob
        r = max(3, int(self.RADIUS * zoom))
        shadow = pygame.Surface((r*2+4, max(1, int(6*zoom))), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), (0, 0, r*2+4, max(1, int(6*zoom))))
        surface.blit(shadow, (cx-r-2, cy+r-2))
        body = pygame.Rect(cx-r, cy-r, r*2, r*2)
        pygame.draw.rect(surface, ORANGE, body, border_radius=max(1, int(5*zoom)))
        pygame.draw.rect(surface, YELLOW, body, max(1, int(2*zoom)),
                         border_radius=max(1, int(5*zoom)))
        gw = max(2, int(10*zoom)); gh = max(1, int(5*zoom))
        pygame.draw.rect(surface, (200, 100, 0),
                         (cx-gw//2, cy-r-gh-1, gw, gh),
                         border_radius=max(1, int(2*zoom)))
        if zoom >= 0.4:
            if self._font is None:
                self._font = pygame.font.SysFont("Arial", 16, bold=True)
            lbl = self._font.render("F", True, WHITE)
            surface.blit(lbl, (cx - lbl.get_width()//2, cy - lbl.get_height()//2))

    def _draw_faded(self, surface, cx, cy, zoom):
        r = max(3, int(self.RADIUS * zoom))
        tmp = pygame.Surface((r*2+4, r*2+4), pygame.SRCALPHA)
        pygame.draw.rect(tmp, (255, 140, 0, 70), (2, 2, r*2, r*2),
                         border_radius=max(1, int(5*zoom)))
        surface.blit(tmp, (cx-r-2, cy-r-2))

    def _draw_ghost(self, surface, cx, cy, zoom):
        r = max(3, int(self.RADIUS * zoom))
        pygame.draw.circle(surface, (100, 100, 100), (cx, cy), r, 1)
        if zoom >= 0.4:
            if self._font is None:
                self._font = pygame.font.SysFont("Arial", 16, bold=True)
            secs = max(0, math.ceil(self._respawn_timer))
            lbl = self._font.render(str(secs), True, GRAY)
            surface.blit(lbl, (cx - lbl.get_width()//2, cy - lbl.get_height()//2))


# =============================================================================
#  BoostPad
# =============================================================================
class BoostPad:
    """
    Yellow stripe – gives BOOST_DURATION seconds of boost.
    Individual: each player triggers it separately (own collected_by).
    """
    RADIUS          = 30
    BOOST_SPEED     = 300.0    # Immediate impulse (px/s added)
    BOOST_ACCEL     = 900.0    # Additional acceleration during boost_timer
    BOOST_DURATION  = 1.5
    BOOST_MAX_SPEED = 780.0
    RESPAWN_TIME    = 10.0
    PLAYER_HOST     = PLAYER_HOST
    PLAYER_CLIENT   = PLAYER_CLIENT

    def __init__(self, x: float, y: float, angle: float = 0.0, pad_id: int = 0) -> None:
        self.x              = x
        self.y              = y
        self.angle          = angle
        self.pad_id         = pad_id
        self.active         = True
        self._respawn_timer = 0.0
        self._time          = 0.0
        self._font: pygame.font.Font | None = None
        self.collected_by: set[int] = set()
        self._pvp_mode      = False

    def set_pvp_mode(self, pvp: bool) -> None:
        self._pvp_mode = pvp

    def update(self, dt: float) -> None:
        self._time += dt
        if not self.active:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self.active = True
                self.collected_by.clear()

    def try_trigger(self, car_x: float, car_y: float,
                    player_id: int = PLAYER_HOST) -> bool:
        if player_id in self.collected_by:
            return False
        if not self.active:
            return False
        if math.hypot(car_x - self.x, car_y - self.y) >= self.RADIUS + 14:
            return False
        self.collected_by.add(player_id)
        if self._pvp_mode:
            if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
                self.active = False
                self._respawn_timer = self.RESPAWN_TIME
        else:
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
        return True

    # ── Network ─────────────────────────────────────────────────────────────────

    def to_net_dict(self) -> dict:
        return {
            "id":     self.pad_id,
            "active": self.active,
            "timer":  self._respawn_timer,
            "cby":    list(self.collected_by),
        }

    def apply_net_dict(self, d: dict) -> None:
        self.active         = bool(d.get("active", True))
        self._respawn_timer = float(d.get("timer", 0.0))
        self.collected_by   = set(d.get("cby", []))

    # ── Rendering ────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0,
             player_id: int = PLAYER_HOST) -> None:
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        r  = max(4, int(self.RADIUS * zoom))

        if not self.active:
            self._draw_ghost(surface, sx, sy, r, zoom)
            return
        if player_id in self.collected_by:
            self._draw_faded(surface, sx, sy, r, zoom)
            return

        # Pulsierender Glow
        pulse  = 0.7 + 0.3 * math.sin(self._time * 4.0)
        glow_r = int(r * 1.6 * pulse)
        glow   = pygame.Surface((glow_r*2+4, glow_r*2+4), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (255, 220, 0, 50), (0, 0, glow_r*2+4, glow_r*2+4))
        surface.blit(glow, (sx - glow_r - 2, sy - glow_r - 2))

        # Haupt-Streifen
        pad_w = max(8, int(r * 2.2))
        pad_h = max(4, int(r * 0.55))
        pad_surf = pygame.Surface((pad_w, pad_h), pygame.SRCALPHA)
        pygame.draw.rect(pad_surf, (255, 215, 0),
                         (0, 0, pad_w, pad_h), border_radius=max(1, pad_h//2))
        pygame.draw.rect(pad_surf, (255, 255, 120),
                         (0, 0, pad_w, pad_h), max(1, int(2*zoom)),
                         border_radius=max(1, pad_h//2))
        rotated = pygame.transform.rotate(pad_surf, -self.angle)
        surface.blit(rotated,
                     (sx - rotated.get_width()//2, sy - rotated.get_height()//2))

        if zoom >= 0.45:
            if self._font is None:
                self._font = pygame.font.SysFont("Arial", 13, bold=True)
            lbl = self._font.render("▶▶", True, (255, 255, 80))
            rl  = pygame.transform.rotate(lbl, -self.angle)
            surface.blit(rl, (sx - rl.get_width()//2, sy - rl.get_height()//2))

    def _draw_faded(self, surface, sx, sy, r, zoom):
        tmp = pygame.Surface((r*2+4, r*2+4), pygame.SRCALPHA)
        pygame.draw.rect(tmp, (200, 180, 0, 55), (2, 2, r*2, r*2),
                         border_radius=max(1, int(5*zoom)))
        surface.blit(tmp, (sx-r-2, sy-r-2))

    def _draw_ghost(self, surface, sx, sy, r, zoom):
        pygame.draw.circle(surface, (80, 80, 20), (sx, sy), r, max(1, int(2*zoom)))
        if zoom >= 0.4:
            if self._font is None:
                self._font = pygame.font.SysFont("Arial", 13, bold=True)
            secs = max(0, math.ceil(self._respawn_timer))
            lbl  = self._font.render(str(secs), True, (100, 100, 40))
            surface.blit(lbl, (sx - lbl.get_width()//2, sy - lbl.get_height()//2))


# =============================================================================
#  OilSlick
# =============================================================================
class OilSlick:
    """
    Oil slick – reduces grip_factor for SPIN_DURATION seconds.
    Individual: each player triggers the effect separately.
    """
    RADIUS        = 28
    SPIN_GRIP     = 0.08
    SPIN_DURATION = 2.0
    RESPAWN_TIME  = 15.0
    PLAYER_HOST   = PLAYER_HOST
    PLAYER_CLIENT = PLAYER_CLIENT

    def __init__(self, x: float, y: float, slick_id: int = 0) -> None:
        self.x              = x
        self.y              = y
        self.slick_id       = slick_id
        self.active         = True
        self._respawn_timer = 0.0
        self._time          = 0.0
        self.collected_by: set[int] = set()
        self._pvp_mode      = False

    def set_pvp_mode(self, pvp: bool) -> None:
        self._pvp_mode = pvp

    def update(self, dt: float) -> None:
        self._time += dt
        if not self.active:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self.active = True
                self.collected_by.clear()

    def try_trigger(self, car_x: float, car_y: float,
                    player_id: int = PLAYER_HOST) -> bool:
        if player_id in self.collected_by:
            return False
        if not self.active:
            return False
        if math.hypot(car_x - self.x, car_y - self.y) >= self.RADIUS + 14:
            return False
        self.collected_by.add(player_id)
        if self._pvp_mode:
            if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
                self.active = False
                self._respawn_timer = self.RESPAWN_TIME
        else:
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
        return True

    # ── Network ─────────────────────────────────────────────────────────────────

    def to_net_dict(self) -> dict:
        return {
            "id":     self.slick_id,
            "x":      self.x,
            "y":      self.y,
            "active": self.active,
            "timer":  self._respawn_timer,
            "cby":    list(self.collected_by),
        }

    def apply_net_dict(self, d: dict) -> None:
        # Position nur übernehmen wenn explizit gesendet (dynamisch abgelegte Ölflecken)
        if "x" in d: self.x = float(d["x"])
        if "y" in d: self.y = float(d["y"])
        self.active         = bool(d.get("active", True))
        self._respawn_timer = float(d.get("timer", 0.0))
        self.collected_by   = set(d.get("cby", []))

    # ── Rendering ────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0,
             player_id: int = PLAYER_HOST) -> None:
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        r  = max(3, int(self.RADIUS * zoom))

        if not self.active:
            self._draw_ghost(surface, sx, sy, r)
            return
        if player_id in self.collected_by:
            self._draw_faded(surface, sx, sy, r)
            return

        wobble = 0.85 + 0.15 * math.sin(self._time * 0.7)
        for rx_f, ry_f, alpha, col in [
            (1.0,  0.55, 210, (15,  15,  15)),
            (0.72, 0.40, 220, (25,  22,  10)),
            (0.42, 0.25, 190, (40,  35,  10)),
        ]:
            ew = max(2, int(r * 2 * rx_f * wobble))
            eh = max(1, int(r * 2 * ry_f))
            tmp = pygame.Surface((ew, eh), pygame.SRCALPHA)
            pygame.draw.ellipse(tmp, (*col, alpha), (0, 0, ew, eh))
            surface.blit(tmp, (sx - ew//2, sy - eh//2))

        if zoom >= 0.4:
            hl_r = max(2, int(r * 0.25))
            hl   = pygame.Surface((hl_r*2, hl_r*2), pygame.SRCALPHA)
            pygame.draw.circle(hl, (80, 80, 70, 130), (hl_r, hl_r), hl_r)
            surface.blit(hl, (sx - int(r*0.3) - hl_r, sy - int(r*0.3) - hl_r))

    def _draw_faded(self, surface, sx, sy, r):
        tmp = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.ellipse(tmp, (20, 20, 10, 45), (0, 0, r*2, r*2))
        surface.blit(tmp, (sx - r, sy - r))

    def _draw_ghost(self, surface, sx, sy, r):
        pygame.draw.circle(surface, (30, 30, 30), (sx, sy), r, 1)


# =============================================================================
#  EntityParticleSystem  –  Phase 6.2b
# =============================================================================
class _EParticle:
    __slots__ = ("x","y","vx","vy","life","max_life","color","radius","alpha_start")

    def __init__(self, x, y, vx, vy, life, color, radius, alpha_start=255):
        self.x = x; self.y = y
        self.vx = vx; self.vy = vy
        self.life = life; self.max_life = life
        self.color = color; self.radius = radius
        self.alpha_start = alpha_start

    def update(self, dt: float) -> bool:
        self.x  += self.vx * dt
        self.y  += self.vy * dt
        self.vx *= 0.88
        self.vy *= 0.88
        self.life -= dt
        return self.life > 0

    def draw(self, surface: pygame.Surface, off_x: int, off_y: int, zoom: float) -> None:
        frac  = max(0.0, self.life / self.max_life)
        alpha = int(self.alpha_start * frac)
        r     = max(1, int(self.radius * frac))
        tmp   = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (*self.color, alpha), (r, r), r)
        surface.blit(tmp, (int(self.x * zoom) + off_x - r,
                           int(self.y * zoom) + off_y - r))


class EntityParticleSystem:
    """
    Particle effects for boost sparks and surface dust.

    Integration in game.py / client.py:
        self.entity_particles = EntityParticleSystem()
        # in update():
        self.entity_particles.emit_boost_sparks(b.x, b.y)   # after boost pickup
        self.entity_particles.emit_dust(s.x, s.y, s.angle, s.speed, surf)
        self.entity_particles.update(dt)
        # in draw_world():
        self.entity_particles.draw(surface, off_x, off_y, zoom)
    """
    MAX = 250

    def __init__(self) -> None:
        self._p: list[_EParticle] = []

    # ── Emitter ──────────────────────────────────────────────────────────────

    def emit_boost_sparks(self, x: float, y: float) -> None:
        """Yellow-white spark burst on boost pickup."""
        cols = [(255, 230, 50), (255, 200, 0), (255, 255, 180), (255, 160, 0)]
        for _ in range(24):
            a  = random.uniform(0, math.pi * 2)
            sp = random.uniform(70, 220)
            self._p.append(_EParticle(
                x + random.uniform(-6, 6),
                y + random.uniform(-6, 6),
                math.cos(a) * sp, math.sin(a) * sp,
                random.uniform(0.35, 0.8),
                random.choice(cols),
                random.uniform(3, 7),
                alpha_start=230,
            ))

    def emit_dust(self, x: float, y: float,
                  angle: float, speed: float,
                  surface_type: str = "grass") -> None:
        """
        Small particles behind the rear wheels.
        Called per frame – has internal rate limiter.
        surface_type: "ice" → ice crystals (light blue)
                      "desert" → sand (brown-yellow)
                      "grass"  → dirt (brown-green)
        """
        if abs(speed) < 25 or len(self._p) >= self.MAX:
            return
        if surface_type == "ice":
            cols = [(200, 225, 255), (180, 210, 240), (220, 235, 255)]
        elif surface_type == "desert":
            cols = [(200, 170, 90),  (185, 155, 75),  (215, 190, 110)]
        else:
            cols = [(155, 135, 95),  (130, 110, 78),  (100, 90, 60)]

        rad = math.radians(angle)
        bvx = -math.sin(rad) * abs(speed) * 0.14
        bvy =  math.cos(rad) * abs(speed) * 0.14
        for _ in range(2):
            s = random.uniform(18, 55)
            self._p.append(_EParticle(
                x + random.uniform(-10, 10),
                y + random.uniform(-10, 10),
                bvx + random.uniform(-s, s),
                bvy + random.uniform(-s, s),
                random.uniform(0.18, 0.48),
                random.choice(cols),
                random.uniform(2, 5),
                alpha_start=170,
            ))

    # ── Update / Draw ─────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self._p = [p for p in self._p if p.update(dt)]

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        for p in self._p:
            p.draw(surface, off_x, off_y, zoom)


# =============================================================================
#  ItemBox  –  Phase 7
# =============================================================================
#  Pulsating purple/blue "?" square. When collected, gives a random
#  item from ITEMS_POOL. Individual collected_by logic like BoostPad.
# =============================================================================

ITEMS_POOL = [
    "pocket_boost", "pocket_boost",   # 2× more frequent
    "oil_drop",
    "green_boomerang",
    "red_boomerang",
]


class ItemBox:
    RADIUS       = 22
    RESPAWN_TIME = 20.0
    PLAYER_HOST   = PLAYER_HOST
    PLAYER_CLIENT = PLAYER_CLIENT

    def __init__(self, x: float, y: float, box_id: int = 0) -> None:
        self.x              = x
        self.y              = y
        self.box_id         = box_id
        self.active         = True
        self._respawn_timer = 0.0
        self._time          = 0.0
        self._font: pygame.font.Font | None = None
        self.collected_by: set[int] = set()
        self._pvp_mode      = False

    def set_pvp_mode(self, pvp: bool) -> None:
        self._pvp_mode = pvp

    def update(self, dt: float) -> None:
        self._time += dt
        if not self.active:
            self._respawn_timer -= dt
            if self._respawn_timer <= 0:
                self.active = True
                self.collected_by.clear()

    def try_pickup(self, car_x: float, car_y: float,
                   player_id: int = PLAYER_HOST) -> str | None:
        """
        Returns the rolled item (e.g. 'pocket_boost') or None.
        Prevents double pickup via collected_by.
        """
        if player_id in self.collected_by or not self.active:
            return None
        if math.hypot(car_x - self.x, car_y - self.y) >= self.RADIUS + 14:
            return None
        self.collected_by.add(player_id)
        if self._pvp_mode:
            if PLAYER_HOST in self.collected_by and PLAYER_CLIENT in self.collected_by:
                self.active = False
                self._respawn_timer = self.RESPAWN_TIME
        else:
            self.active = False
            self._respawn_timer = self.RESPAWN_TIME
        # Roll – deterministic enough for host-authority model
        import random
        return random.choice(ITEMS_POOL)

    # ── Network ─────────────────────────────────────────────────────────────────

    def to_net_dict(self) -> dict:
        return {
            "id":     self.box_id,
            "active": self.active,
            "timer":  self._respawn_timer,
            "cby":    list(self.collected_by),
        }

    def apply_net_dict(self, d: dict) -> None:
        self.active         = bool(d.get("active", True))
        self._respawn_timer = float(d.get("timer", 0.0))
        self.collected_by   = set(d.get("cby", []))

    # ── Rendering ────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0,
             player_id: int = PLAYER_HOST) -> None:
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        r  = max(4, int(self.RADIUS * zoom))

        if not self.active:
            self._draw_ghost(surface, sx, sy, r, zoom)
            return
        if player_id in self.collected_by:
            self._draw_faded(surface, sx, sy, r, zoom)
            return

        # Rotation over time
        angle  = self._time * 45.0   # 45°/s slow rotation
        pulse  = 0.75 + 0.25 * math.sin(self._time * 3.5)

        # Outer glow (purple)
        glow_r = int(r * 1.7 * pulse)
        glow   = pygame.Surface((glow_r*2+4, glow_r*2+4), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (160, 80, 255, 45), (0, 0, glow_r*2+4, glow_r*2+4))
        surface.blit(glow, (sx - glow_r - 2, sy - glow_r - 2))

        # Quadrat (rotiert)
        box_s  = max(8, int(r * 1.6))
        box_sf = pygame.Surface((box_s, box_s), pygame.SRCALPHA)
        # Gradient effect: two rectangles
        pygame.draw.rect(box_sf, (120, 40, 220),
                         (0, 0, box_s, box_s), border_radius=max(2, box_s//6))
        pygame.draw.rect(box_sf, (200, 130, 255),
                         (0, 0, box_s, box_s), max(1, int(2*zoom)),
                         border_radius=max(2, box_s//6))
        # Inneres Highlight
        hl = box_s // 4
        pygame.draw.rect(box_sf, (220, 180, 255, 120),
                         (hl//2, hl//2, box_s - hl, box_s // 3),
                         border_radius=max(1, box_s//8))
        rotated = pygame.transform.rotate(box_sf, angle % 360)
        surface.blit(rotated, (sx - rotated.get_width()//2,
                               sy - rotated.get_height()//2))

        # "?" Label
        if zoom >= 0.4:
            if self._font is None:
                self._font = pygame.font.SysFont("Arial", max(10, int(16*zoom)),
                                                  bold=True)
            lbl = self._font.render("?", True, (255, 240, 255))
            surface.blit(lbl, (sx - lbl.get_width()//2,
                               sy - lbl.get_height()//2))

    def _draw_faded(self, surface, sx, sy, r, zoom):
        tmp = pygame.Surface((r*2+4, r*2+4), pygame.SRCALPHA)
        pygame.draw.rect(tmp, (120, 40, 220, 50),
                         (2, 2, r*2, r*2), border_radius=max(2, r//3))
        surface.blit(tmp, (sx-r-2, sy-r-2))

    def _draw_ghost(self, surface, sx, sy, r, zoom):
        pygame.draw.rect(surface, (60, 30, 90),
                         (sx-r, sy-r, r*2, r*2),
                         max(1, int(2*zoom)),
                         border_radius=max(2, r//3))
        if zoom >= 0.4:
            if self._font is None:
                self._font = pygame.font.SysFont("Arial", max(10, int(14*zoom)),
                                                  bold=True)
            secs = max(0, math.ceil(self._respawn_timer))
            lbl  = self._font.render(str(secs), True, (100, 60, 140))
            surface.blit(lbl, (sx - lbl.get_width()//2,
                               sy - lbl.get_height()//2))


# =============================================================================
#  Boomerangs  –  Phase 8
# =============================================================================
#
#  GreenBoomerang: flies straight in launch direction, bounces off tile
#    outer walls (max MAX_BOUNCES bounces), hits enemy cars → spin.
#  RedBoomerang: "smart" – moves with slight homing angle
#    toward the nearest opponent.
#
#  Both: owner_id prevents self-damage.
#        to_net_dict / apply_net_dict for network sync.
# =============================================================================

BOOMERANG_SPEED     = 620.0   # px/s
BOOMERANG_LIFETIME  = 4.5     # Seconds until self-destruction
BOOMERANG_RADIUS    = 10
MAX_BOUNCES         = 4       # GreenBoomerang max bounces


class GreenBoomerang:
    """Flies straight, bounces off walls, triggers spin_timer on hit."""

    def __init__(self, x: float, y: float, angle: float,
                 owner_id: int, brang_id: int = 0) -> None:
        self.x        = x
        self.y        = y
        self.angle    = float(angle)   # Grad, Fahrtrichtung
        self.owner_id = owner_id
        self.brang_id = brang_id
        self.active   = True
        self._life    = BOOMERANG_LIFETIME
        self._bounces = 0
        self._rot     = 0.0   # visuelle Rotation
        # Geschwindigkeitsvektor
        rad = math.radians(self.angle)
        self.vx = math.sin(rad) * BOOMERANG_SPEED
        self.vy = -math.cos(rad) * BOOMERANG_SPEED

    def update(self, dt: float, track) -> None:
        if not self.active:
            return
        self._life -= dt
        self._rot  = (self._rot + 360 * dt) % 360
        if self._life <= 0:
            self.active = False
            return

        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt

        # Wall bounce: check if new tile is available
        # Simplified: if no tile found (outside all tiles) → bounce
        on_track = any(t.surface_at(nx, ny) is not None for t in track.tiles)
        if not on_track:
            if self._bounces >= MAX_BOUNCES:
                self.active = False
                return
            self._bounces += 1
            # Recoil: reverse direction
            # Calculate which axis is blocked
            on_x = any(t.surface_at(nx, self.y) is not None for t in track.tiles)
            on_y = any(t.surface_at(self.x, ny) is not None for t in track.tiles)
            if not on_x:
                self.vx = -self.vx
            if not on_y:
                self.vy = -self.vy
            # Neuberechnung nach Bounce
            nx = self.x + self.vx * dt
            ny = self.y + self.vy * dt
            # Fallback: bleib an alter Position
            if not any(t.surface_at(nx, ny) is not None for t in track.tiles):
                nx, ny = self.x, self.y

        self.x, self.y = nx, ny

    def check_hit(self, car_x: float, car_y: float,
                  car_player_id: int) -> bool:
        """Returns True if the projectile hits an enemy car."""
        if not self.active or car_player_id == self.owner_id:
            return False
        if math.hypot(car_x - self.x, car_y - self.y) < BOOMERANG_RADIUS + 18:
            self.active = False
            return True
        return False

    # ── Network ─────────────────────────────────────────────────────────────────

    def to_net_dict(self) -> dict:
        return {
            "id":    self.brang_id,
            "kind":  "green",
            "x":     self.x, "y": self.y,
            "vx":    self.vx, "vy": self.vy,
            "angle": self.angle,
            "owner": self.owner_id,
            "active": self.active,
            "life":  self._life,
        }

    def apply_net_dict(self, d: dict) -> None:
        self.x      = float(d["x"]);    self.y   = float(d["y"])
        self.vx     = float(d["vx"]);   self.vy  = float(d["vy"])
        self.angle  = float(d["angle"])
        self.active = bool(d["active"]); self._life = float(d["life"])

    # ── Rendering ────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        if not self.active:
            return
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        r  = max(4, int(BOOMERANG_RADIUS * zoom))

        # Rotating triangle (green)
        pts = []
        for i in range(3):
            a = math.radians(self._rot + i * 120)
            pts.append((sx + math.cos(a) * r, sy + math.sin(a) * r))
        pygame.draw.polygon(surface, (50, 220, 80), pts)
        pygame.draw.polygon(surface, (180, 255, 180), pts, max(1, int(2*zoom)))

        # Glow
        glow = pygame.Surface((r*4, r*4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (80, 255, 100, 60), (r*2, r*2), r*2)
        surface.blit(glow, (sx - r*2, sy - r*2))


class RedBoomerang:
    """
    Smart projectile: steers slightly toward the nearest enemy car.
    Uses simplified steering correction per frame.
    """
    STEER_STRENGTH = 140.0   # Degrees/s maximum course correction

    def __init__(self, x: float, y: float, angle: float,
                 owner_id: int, brang_id: int = 0) -> None:
        self.x        = x
        self.y        = y
        self.angle    = float(angle)
        self.owner_id = owner_id
        self.brang_id = brang_id
        self.active   = True
        self._life    = BOOMERANG_LIFETIME
        self._rot     = 0.0

    def _vel(self):
        rad = math.radians(self.angle)
        return math.sin(rad) * BOOMERANG_SPEED, -math.cos(rad) * BOOMERANG_SPEED

    def update(self, dt: float, track, target_x: float | None,
               target_y: float | None) -> None:
        if not self.active:
            return
        self._life -= dt
        self._rot   = (self._rot + 360 * dt) % 360
        if self._life <= 0:
            self.active = False
            return

        # Lenkung zum Ziel
        if target_x is not None and target_y is not None:
            dx = target_x - self.x
            dy = target_y - self.y
            dist = math.hypot(dx, dy)
            if dist > 1:
                desired_angle = math.degrees(math.atan2(dx, -dy)) % 360
                diff = (desired_angle - self.angle + 360) % 360
                if diff > 180: diff -= 360
                correction = max(-self.STEER_STRENGTH * dt,
                                 min(self.STEER_STRENGTH * dt, diff))
                self.angle = (self.angle + correction) % 360

        vx, vy = self._vel()
        nx = self.x + vx * dt
        ny = self.y + vy * dt

        on_track = any(t.surface_at(nx, ny) is not None for t in track.tiles)
        if on_track:
            self.x, self.y = nx, ny
        else:
            self.active = False

    def check_hit(self, car_x: float, car_y: float,
                  car_player_id: int) -> bool:
        if not self.active or car_player_id == self.owner_id:
            return False
        if math.hypot(car_x - self.x, car_y - self.y) < BOOMERANG_RADIUS + 18:
            self.active = False
            return True
        return False

    # ── Network ─────────────────────────────────────────────────────────────────

    def to_net_dict(self) -> dict:
        return {
            "id":    self.brang_id,
            "kind":  "red",
            "x":     self.x,  "y":     self.y,
            "angle": self.angle,
            "owner": self.owner_id,
            "active": self.active,
            "life":  self._life,
        }

    def apply_net_dict(self, d: dict) -> None:
        self.x      = float(d["x"]);    self.y     = float(d["y"])
        self.angle  = float(d["angle"]); self.active = bool(d["active"])
        self._life  = float(d["life"])

    # ── Rendering ────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        if not self.active:
            return
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        r  = max(4, int(BOOMERANG_RADIUS * zoom))

        # Rotierendes Rhombus (rot)
        pts = []
        for i in range(4):
            a  = math.radians(self._rot + i * 90)
            rr = r if i % 2 == 0 else r * 0.6
            pts.append((sx + math.cos(a) * rr, sy + math.sin(a) * rr))
        pygame.draw.polygon(surface, (230, 50, 50), pts)
        pygame.draw.polygon(surface, (255, 180, 180), pts, max(1, int(2*zoom)))

        glow = pygame.Surface((r*4, r*4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 80, 80, 60), (r*2, r*2), r*2)
        surface.blit(glow, (sx - r*2, sy - r*2))
