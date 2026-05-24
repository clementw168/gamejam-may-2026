"""Camera — handles the world→screen transform and screen shake."""

from __future__ import annotations
import random
import pygame


class Camera:
    def __init__(self) -> None:
        self.offset = pygame.Vector2(0, 0)   # world position of viewport top-left
        self._shake = 0.0
        self._sx = 0.0
        self._sy = 0.0

    # ── Shake ──────────────────────────────────────────────────────────────────
    def add_shake(self, intensity: float) -> None:
        self._shake = max(self._shake, float(intensity))

    def update(self, dt: float) -> None:
        if self._shake > 0.3:
            self._sx = random.uniform(-self._shake, self._shake)
            self._sy = random.uniform(-self._shake, self._shake)
            self._shake *= (1 - dt * 18)
        else:
            self._shake = 0.0
            self._sx = self._sy = 0.0

    # ── Transform helpers ──────────────────────────────────────────────────────
    def apply_pos(self, x: float, y: float) -> tuple[float, float]:
        """World → screen (float tuple)."""
        return (x - self.offset.x + self._sx,
                y - self.offset.y + self._sy)

    def apply_vec(self, v: pygame.Vector2) -> pygame.Vector2:
        return pygame.Vector2(v.x - self.offset.x + self._sx,
                              v.y - self.offset.y + self._sy)

    def apply_rect(self, rect: pygame.Rect) -> pygame.Rect:
        return rect.move(int(-self.offset.x + self._sx),
                         int(-self.offset.y + self._sy))

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx + self.offset.x - self._sx,
                sy + self.offset.y - self._sy)
