# =============================================================================
#  props.py  –  Panic Pilot | Dekorative Props (Phase 5.3)
# =============================================================================
#
#  Props sind rein kosmetisch – keine Kollision.
#  Neue Prop-Typen: Funktion in _PROP_DRAWERS eintragen.
#  Phase-6-Hook: PropManager.props kann Animationsdaten tragen.
# =============================================================================
from __future__ import annotations
import math, random
from typing import Optional
import pygame

PROP_TREE      = "tree"
PROP_CACTUS    = "cactus"
PROP_SNOWMAN   = "snowman"
PROP_ROCK      = "rock"
PROP_MUSHROOM  = "mushroom"
PROP_LAMPPOST  = "lamppost"
PROP_CANDY_POP = "candy_pop"

THEME_PROPS = {
    "standard": [PROP_TREE,     PROP_ROCK],
    "desert":   [PROP_CACTUS,   PROP_ROCK],
    "ice":      [PROP_SNOWMAN,  PROP_ROCK],
    "night":    [PROP_LAMPPOST, PROP_ROCK],
    "candy":    [PROP_CANDY_POP, PROP_MUSHROOM],
}
DEFAULT_PROPS = [PROP_TREE, PROP_ROCK]


# ── Zeichenfunktionen ─────────────────────────────────────────────────────────

def _draw_tree(s, cx, cy, r):
    tw = max(4, r//3); th = max(6, r//2)
    pygame.draw.rect(s, (100,60,20), (cx-tw//2, cy+r//2-th//2, tw, th))
    for i, sc in enumerate([1.0, 0.75, 0.55]):
        g = (20+i*15, 100+i*10, 20+i*5)
        pts = [(cx, cy-r+i*r//3), (cx+int(r*sc), cy+i*r//4), (cx-int(r*sc), cy+i*r//4)]
        pygame.draw.polygon(s, g, pts)

def _draw_cactus(s, cx, cy, r):
    w = max(4, r//4); h = r; g = (50,140,40)
    pygame.draw.rect(s, g, (cx-w//2, cy-h//2, w, h), border_radius=3)
    pygame.draw.rect(s, g, (cx-w//2-w, cy-h//4, w, h//2), border_radius=3)
    pygame.draw.rect(s, g, (cx-w-w//2, cy-h//2, w, h//3), border_radius=3)
    pygame.draw.rect(s, g, (cx+w//2, cy-h//4, w, h//2), border_radius=3)
    pygame.draw.rect(s, g, (cx+w//2, cy-h//2, w, h//3), border_radius=3)

def _draw_snowman(s, cx, cy, r):
    rb = max(5, r*2//3); rt = max(4, r//2)
    pygame.draw.circle(s, (240,240,255), (cx, cy+rb//2), rb)
    pygame.draw.circle(s, (240,240,255), (cx, cy-rt), rt)
    pygame.draw.polygon(s, (255,140,0), [(cx,cy-rt),(cx+rt//2,cy-rt+3),(cx,cy-rt+2)])
    for ex in [-rt//3, rt//3]:
        pygame.draw.circle(s, (30,30,30), (cx+ex, cy-rt-rt//4), max(1,rt//5))
    for i in range(3):
        pygame.draw.circle(s, (30,30,30), (cx, cy+i*rb//3), max(1,rb//8))

def _draw_rock(s, cx, cy, r):
    pts = [(cx+math.cos(2*math.pi*i/7)*r*(0.6+0.4*((i*17)%10)/10),
            cy+math.sin(2*math.pi*i/7)*r*(0.6+0.4*((i*17)%10)/10)) for i in range(7)]
    pygame.draw.polygon(s, (110,105,100), pts)
    pygame.draw.polygon(s, (140,135,130), pts, 2)

def _draw_mushroom(s, cx, cy, r):
    sw = max(3,r//3); sh = max(4,r//2)
    pygame.draw.rect(s, (255,220,180), (cx-sw//2, cy, sw, sh), border_radius=2)
    pygame.draw.ellipse(s, (220,40,100), (cx-r, cy-r//2, r*2, r))
    for px, py in [(-r//3,-r//3),(r//3,-r//3),(0,-r//6)]:
        pygame.draw.circle(s, (255,255,255), (cx+px,cy+py), max(2,r//6))

def _draw_lamppost(s, cx, cy, r):
    pygame.draw.rect(s, (70,70,80), (cx-2, cy-r, 4, r), border_radius=2)
    pygame.draw.rect(s, (70,70,80), (cx-2, cy-r, r//2, 3))
    pygame.draw.circle(s, (255,240,180), (cx+r//2, cy-r), max(2,r//4))
    glow = pygame.Surface((r*2,r*2), pygame.SRCALPHA)
    pygame.draw.circle(glow, (255,240,140,40), (r,r), r)
    s.blit(glow, (cx+r//2-r, cy-r-r))

def _draw_candy_pop(s, cx, cy, r):
    pygame.draw.rect(s, (200,160,220), (cx-2, cy-r//2, 4, r), border_radius=2)
    for i, col in enumerate([(100,200,255),(255,220,50),(255,80,180)]):
        pygame.draw.circle(s, col, (cx, cy-r//2), max(2, r-i*r//4))

_PROP_DRAWERS = {
    PROP_TREE: _draw_tree, PROP_CACTUS: _draw_cactus,
    PROP_SNOWMAN: _draw_snowman, PROP_ROCK: _draw_rock,
    PROP_MUSHROOM: _draw_mushroom, PROP_LAMPPOST: _draw_lamppost,
    PROP_CANDY_POP: _draw_candy_pop,
}


class Prop:
    __slots__ = ("wx","wy","radius","prop_type","_surf")
    def __init__(self, wx, wy, radius, prop_type):
        self.wx=wx; self.wy=wy; self.radius=radius; self.prop_type=prop_type
        self._surf: Optional[pygame.Surface] = None

    def _build(self):
        sz = self.radius*2+8
        s  = pygame.Surface((sz,sz), pygame.SRCALPHA)
        _PROP_DRAWERS.get(self.prop_type, _draw_tree)(s, sz//2, sz//2, self.radius)
        self._surf = s

    def draw(self, screen, off_x, off_y, zoom=1.0):
        if self._surf is None: self._build()
        from settings import SCREEN_W, SCREEN_H
        sx = int(self.wx*zoom)+off_x; sy = int(self.wy*zoom)+off_y
        r  = int(self.radius*zoom)
        if sx+r<0 or sx-r>SCREEN_W or sy+r<0 or sy-r>SCREEN_H: return
        if zoom==1.0:
            screen.blit(self._surf, (sx-self.radius-4, sy-self.radius-4))
        else:
            sz = max(4, int((self.radius*2+8)*zoom))
            screen.blit(pygame.transform.scale(self._surf,(sz,sz)), (sx-sz//2, sy-sz//2))


class PropManager:
    """Dekorative Props – rein kosmetisch, keine Kollision."""
    def __init__(self): self._props: list[Prop] = []

    @classmethod
    def generate(cls, track, theme=None, seed=None) -> "PropManager":
        from track import TILE_SIZE
        rng = random.Random(seed)
        theme_name = getattr(theme,"name","standard") if theme else "standard"
        ptypes = THEME_PROPS.get(theme_name, DEFAULT_PROPS)
        pm = cls()
        if not track.tiles: return pm
        occupied = {(int(t.world_x//TILE_SIZE), int(t.world_y//TILE_SIZE)) for t in track.tiles}
        min_gx = min(int(t.world_x//TILE_SIZE) for t in track.tiles)
        max_gx = max(int(t.world_x//TILE_SIZE) for t in track.tiles)
        min_gy = min(int(t.world_y//TILE_SIZE) for t in track.tiles)
        max_gy = max(int(t.world_y//TILE_SIZE) for t in track.tiles)
        # Props auf freien Tiles
        for gx in range(min_gx-1, max_gx+2):
            for gy in range(min_gy-1, max_gy+2):
                if (gx,gy) in occupied: continue
                for _ in range(rng.randint(3,5)):
                    wx = (gx+rng.uniform(0.1,0.9))*TILE_SIZE
                    wy = (gy+rng.uniform(0.1,0.9))*TILE_SIZE
                    pm._props.append(Prop(wx,wy,rng.randint(12,26),rng.choice(ptypes)))
        # Props auf Gras-Streifen innerhalb Tiles
        for tile in track.tiles:
            T = TILE_SIZE
            for _ in range(rng.randint(2,4)):
                wx = tile.world_x + rng.uniform(0,T)
                wy = tile.world_y + rng.uniform(0,T)
                if track.surface_at(wx,wy) == "grass":
                    pm._props.append(Prop(wx,wy,rng.randint(8,18),rng.choice(ptypes)))
        return pm

    def draw(self, screen, off_x, off_y, zoom=1.0):
        for p in self._props: p.draw(screen, off_x, off_y, zoom)
