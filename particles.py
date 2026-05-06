# =============================================================================
#  particles.py  –  Panic Pilot | Unified Particle System
# =============================================================================
from __future__ import annotations
import math
import random
import pygame
from settings import *


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "radius", "alpha_start")

    def __init__(self, x, y, vx, vy, life, color, radius, alpha_start: int = 255):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.color = color
        self.radius = radius
        self.alpha_start = alpha_start

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        self.vx *= 0.90
        self.vy *= 0.90
        return self.life > 0

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        frac = max(0.0, self.life / self.max_life)
        alpha = int(self.alpha_start * frac)
        r = max(1, int(self.radius * frac))
        tmp = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (*self.color, alpha), (r, r), r)
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        surface.blit(tmp, (sx - r, sy - r))


class ParticleSystem:
    MAX_PARTICLES = 500

    def __init__(self) -> None:
        self._particles: list[Particle] = []

    def emit_exhaust(self, x: float, y: float, angle: float, speed: float) -> None:
        if len(self._particles) >= self.MAX_PARTICLES or abs(speed) < 20:
            return
        rad = math.radians(angle)
        bvx = -math.sin(rad) * speed * 0.15
        bvy = math.cos(rad) * speed * 0.15
        for _ in range(2):
            s = 30
            c = random.choice([(160, 160, 160), (130, 130, 130), (100, 100, 100)])
            self._particles.append(Particle(
                x, y, bvx + random.uniform(-s, s), bvy + random.uniform(-s, s),
                random.uniform(0.25, 0.55), c, random.uniform(3, 6)))

    def emit_off_track(self, x: float, y: float) -> None:
        if len(self._particles) >= self.MAX_PARTICLES:
            return
        for _ in range(3):
            a = random.uniform(0, math.pi * 2)
            sp = random.uniform(20, 80)
            c = random.choice([(34, 100, 34), (60, 130, 40), (90, 70, 20)])
            self._particles.append(Particle(
                x + random.uniform(-8, 8), y + random.uniform(-8, 8),
                math.cos(a) * sp, math.sin(a) * sp,
                random.uniform(0.2, 0.5), c, random.uniform(2, 5)))

    def emit_pickup(self, x: float, y: float) -> None:
        if len(self._particles) >= self.MAX_PARTICLES:
            return
        for _ in range(18):
            a = random.uniform(0, math.pi * 2)
            sp = random.uniform(40, 160)
            c = random.choice([YELLOW, ORANGE, (255, 200, 50)])
            self._particles.append(Particle(
                x, y, math.cos(a) * sp, math.sin(a) * sp,
                random.uniform(0.4, 0.9), c, random.uniform(3, 7)))

    def emit_boost_sparks(self, x: float, y: float) -> None:
        if len(self._particles) >= self.MAX_PARTICLES:
            return
        cols = [(255, 230, 50), (255, 200, 0), (255, 255, 180), (255, 160, 0)]
        for _ in range(24):
            a = random.uniform(0, math.pi * 2)
            sp = random.uniform(70, 220)
            self._particles.append(Particle(
                x + random.uniform(-6, 6), y + random.uniform(-6, 6),
                math.cos(a) * sp, math.sin(a) * sp,
                random.uniform(0.35, 0.8), random.choice(cols),
                random.uniform(3, 7), alpha_start=230))

    def emit_dust(self, x: float, y: float,
                  angle: float, speed: float,
                  surface_type: str = "grass") -> None:
        if abs(speed) < 25 or len(self._particles) >= self.MAX_PARTICLES:
            return
        if surface_type == "ice":
            cols = [(200, 225, 255), (180, 210, 240), (220, 235, 255)]
        elif surface_type == "desert":
            cols = [(200, 170, 90), (185, 155, 75), (215, 190, 110)]
        else:
            cols = [(155, 135, 95), (130, 110, 78), (100, 90, 60)]

        rad = math.radians(angle)
        bvx = -math.sin(rad) * abs(speed) * 0.14
        bvy = math.cos(rad) * abs(speed) * 0.14
        for _ in range(2):
            s = random.uniform(18, 55)
            self._particles.append(Particle(
                x + random.uniform(-10, 10), y + random.uniform(-10, 10),
                bvx + random.uniform(-s, s), bvy + random.uniform(-s, s),
                random.uniform(0.18, 0.48), random.choice(cols),
                random.uniform(2, 5), alpha_start=170))

    def update(self, dt: float) -> None:
        self._particles = [p for p in self._particles if p.update(dt)]

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        for p in self._particles:
            p.draw(surface, off_x, off_y, zoom)
