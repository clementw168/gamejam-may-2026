"""Projectile classes — player arrows and enemy projectiles."""

from __future__ import annotations
import math
import pygame
from gamejam_may_2026 import constants as C

# forward-declare Room to avoid circular imports at type-check time
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from gamejam_may_2026.rooms import Room
    from gamejam_may_2026.camera import Camera


class Arrow:
    """Fired by the player."""

    TRAIL_INTERVAL = 0.018  # s between trail samples

    def __init__(
        self,
        x: float,
        y: float,
        angle: float,
        *,
        speed:    float | None = None,
        damage:   int   | None = None,
        lifetime: float | None = None,
        piercing: bool  = False,
    ) -> None:
        self.x = x
        self.y = y
        self.angle = angle
        self.vx = math.cos(angle) * (speed    if speed    is not None else C.ARROW_SPEED)
        self.vy = math.sin(angle) * (speed    if speed    is not None else C.ARROW_SPEED)
        self.lifetime = lifetime if lifetime is not None else C.ARROW_LIFETIME
        self.damage   = damage   if damage   is not None else C.ARROW_DAMAGE
        self.piercing = piercing
        self.hit_enemies: set[int] = set()   # id(enemy) already struck (for pierce)
        self.alive = True
        self._trail: list[tuple[float, float]] = []
        self._trail_t = 0.0

    def update(self, dt: float, room: Room) -> None:
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.alive = False
            return

        # Trail
        self._trail_t += dt
        if self._trail_t >= self.TRAIL_INTERVAL:
            self._trail_t = 0.0
            self._trail.append((self.x, self.y))
            if len(self._trail) > 6:
                self._trail.pop(0)

        self.x += self.vx * dt
        self.y += self.vy * dt

        tx = int(self.x // C.TILE_SIZE)
        ty = int(self.y // C.TILE_SIZE)
        if not (0 <= tx < C.ROOM_TILE_W and 0 <= ty < C.ROOM_TILE_H):
            self.alive = False
            return
        if room.tiles[ty][tx] == C.TILE_WALL:
            self.alive = False

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        # Trail
        n = len(self._trail)
        for i, (tx, ty) in enumerate(self._trail):
            t = (i + 1) / (n + 1)
            sx, sy = camera.apply_pos(tx, ty)
            c = int(100 * t * t)
            pygame.draw.circle(surf, (c, int(c * 0.8), 0), (round(sx), round(sy)), max(1, round(2 * t)))

        # Body line
        hw = 9
        ex = self.x + math.cos(self.angle) * hw
        ey = self.y + math.sin(self.angle) * hw
        tx2 = self.x - math.cos(self.angle) * hw
        ty2 = self.y - math.sin(self.angle) * hw
        sx_e, sy_e = camera.apply_pos(ex, ey)
        sx_t, sy_t = camera.apply_pos(tx2, ty2)
        pygame.draw.line(surf, C.C_ARROW, (round(sx_t), round(sy_t)), (round(sx_e), round(sy_e)), 3)
        pygame.draw.circle(surf, C.C_ARROW_TIP, (round(sx_e), round(sy_e)), 3)


class EnemyProjectile:
    """Generic projectile fired by enemies.

    Optional kwargs let callers customise each volley:
        speed    — override EPROJ_SPEED
        color    — RGB tuple, overrides C_ENEMY_PROJ
        damage   — override EPROJ_DAMAGE
        lifetime — override EPROJ_LIFETIME
    """

    def __init__(
        self,
        x: float,
        y: float,
        angle: float,
        *,
        speed:    float | None = None,
        color:    tuple[int, int, int] | None = None,
        damage:   int   | None = None,
        lifetime: float | None = None,
    ) -> None:
        self.x = x
        self.y = y
        self.angle = angle
        _speed = speed if speed is not None else C.EPROJ_SPEED
        self.vx = math.cos(angle) * _speed
        self.vy = math.sin(angle) * _speed
        self.lifetime = lifetime if lifetime is not None else C.EPROJ_LIFETIME
        self.damage   = damage   if damage   is not None else C.EPROJ_DAMAGE
        self.color    = color    if color    is not None else C.C_ENEMY_PROJ
        self.alive = True

    def update(self, dt: float, room: Room) -> None:
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.alive = False
            return

        self.x += self.vx * dt
        self.y += self.vy * dt

        tx = int(self.x // C.TILE_SIZE)
        ty = int(self.y // C.TILE_SIZE)
        if not (0 <= tx < C.ROOM_TILE_W and 0 <= ty < C.ROOM_TILE_H):
            self.alive = False
            return
        if room.tiles[ty][tx] == C.TILE_WALL:
            self.alive = False

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        pygame.draw.circle(surf, self.color, (sx, sy), 6)
        # Inner highlight (brighter centre)
        inner = tuple(min(255, c + 110) for c in self.color)
        pygame.draw.circle(surf, inner, (sx, sy), 3)
