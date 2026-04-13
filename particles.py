# =============================================================================
#  particles.py  –  Panic Pilot | Partikel-System (Phase 4.2: zoom-aware)
# =============================================================================
from __future__ import annotations
import math
import random
import pygame
from settings import *


class Particle:
    __slots__ = ("x","y","vx","vy","life","max_life","color","radius")

    def __init__(self, x,y,vx,vy,life,color,radius):
        self.x=x; self.y=y; self.vx=vx; self.vy=vy
        self.life=life; self.max_life=life; self.color=color; self.radius=radius

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt; self.y += self.vy * dt
        self.life -= dt; self.vx *= 0.92; self.vy *= 0.92
        return self.life > 0

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        """screen_x = world_x * zoom + off_x  (off_x already zoom-adjusted)"""
        alpha = max(0, int(255 * (self.life / self.max_life)))
        r     = max(1, int(self.radius * (self.life / self.max_life)))
        tmp   = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (*self.color, alpha), (r, r), r)
        sx = int(self.x * zoom) + off_x
        sy = int(self.y * zoom) + off_y
        surface.blit(tmp, (sx - r, sy - r))


class ParticleSystem:
    def __init__(self) -> None:
        self._particles: list[Particle] = []

    def emit_exhaust(self, x,y,angle,speed):
        if len(self._particles) >= MAX_PARTICLES or abs(speed) < 20:
            return
        rad = math.radians(angle)
        bvx = -math.sin(rad)*speed*0.15; bvy = math.cos(rad)*speed*0.15
        for _ in range(2):
            s = 30; c = random.choice([(160,160,160),(130,130,130),(100,100,100)])
            self._particles.append(Particle(
                x,y, bvx+random.uniform(-s,s), bvy+random.uniform(-s,s),
                random.uniform(0.25,0.55), c, random.uniform(3,6)))

    def emit_off_track(self, x,y):
        if len(self._particles) >= MAX_PARTICLES:
            return
        for _ in range(3):
            a = random.uniform(0,math.pi*2); sp = random.uniform(20,80)
            c = random.choice([(34,100,34),(60,130,40),(90,70,20)])
            self._particles.append(Particle(
                x+random.uniform(-8,8), y+random.uniform(-8,8),
                math.cos(a)*sp, math.sin(a)*sp, random.uniform(0.2,0.5), c, random.uniform(2,5)))

    def emit_pickup(self, x,y):
        for _ in range(18):
            a = random.uniform(0,math.pi*2); sp = random.uniform(40,160)
            c = random.choice([YELLOW,ORANGE,(255,200,50)])
            self._particles.append(Particle(
                x,y, math.cos(a)*sp, math.sin(a)*sp,
                random.uniform(0.4,0.9), c, random.uniform(3,7)))

    def update(self, dt: float) -> None:
        self._particles = [p for p in self._particles if p.update(dt)]

    def draw(self, surface: pygame.Surface,
             off_x: int = 0, off_y: int = 0, zoom: float = 1.0) -> None:
        for p in self._particles:
            p.draw(surface, off_x, off_y, zoom)
