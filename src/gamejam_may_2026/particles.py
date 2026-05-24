"""Lightweight particle system."""

from __future__ import annotations

import math
import random

import pygame

from gamejam_may_2026 import constants as C


class Particle:
    __slots__ = ("b", "g", "gravity", "life", "max_life", "r", "size", "vx", "vy", "x", "y")

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        color: tuple[int, int, int],
        life: float,
        size: float = 3.0,
        gravity: float = 0.0,
    ) -> None:
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.r, self.g, self.b = color
        self.life = life
        self.max_life = life
        self.size = size
        self.gravity = gravity

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        drag = 1 - dt * 4
        self.vx *= drag
        self.vy *= drag
        self.life -= dt
        return self.life > 0

    def draw(self, surf: pygame.Surface, ox: float, oy: float) -> None:
        t = self.life / self.max_life  # 1 = fresh  →  0 = fading
        sz = max(1, round(self.size * t))
        col = (int(self.r * t), int(self.g * t), int(self.b * t))
        sx = round(self.x - ox)
        sy = round(self.y - oy)
        if -sz < sx < C.SCREEN_W + sz and -sz < sy < C.SCREEN_H + sz:
            pygame.draw.circle(surf, col, (sx, sy), sz)


class ParticleSystem:
    def __init__(self) -> None:
        self._particles: list[Particle] = []

    def update(self, dt: float) -> None:
        self._particles = [p for p in self._particles if p.update(dt)]

    def draw(self, surf: pygame.Surface, ox: float = 0, oy: float = 0) -> None:
        for p in self._particles:
            p.draw(surf, ox, oy)

    # ── Primitive emitter ──────────────────────────────────────────────────────
    def emit(
        self,
        x: float,
        y: float,
        count: int,
        colors: list[tuple[int, int, int]],
        speed: float,
        angle_deg: float,
        spread_deg: float,
        lifetime: float,
        size: float = 3.0,
        gravity: float = 0.0,
    ) -> None:
        for _ in range(count):
            a = math.radians(angle_deg + random.uniform(-spread_deg, spread_deg))
            spd = random.uniform(speed * 0.5, speed * 1.5)
            lt = random.uniform(lifetime * 0.65, lifetime)
            sz = random.uniform(size * 0.6, size * 1.4)
            col = random.choice(colors)
            self._particles.append(Particle(x, y, math.cos(a) * spd, math.sin(a) * spd, col, lt, sz, gravity))

    # ── Named presets ──────────────────────────────────────────────────────────
    def emit_hit(self, x: float, y: float, angle_deg: float) -> None:
        """Sparks when a player arrow hits a wall."""
        self.emit(
            x, y, 7, [C.C_SPARK_A, C.C_SPARK_B, (255, 255, 180)], 190, angle_deg + 180, 65, 0.38, size=2.5, gravity=220
        )

    def emit_enemy_hit(self, x: float, y: float) -> None:
        """Blood/leaf particles when an arrow hits an enemy."""
        self.emit(x, y, 9, [C.C_BLOOD_A, C.C_BLOOD_B, (255, 100, 100)], 130, 0, 180, 0.45, size=3.2, gravity=100)

    def emit_death(
        self,
        x: float,
        y: float,
        color_a: tuple[int, int, int],
        color_b: tuple[int, int, int],
    ) -> None:
        """Big burst on enemy death."""
        self.emit(x, y, 14, [color_a, color_b, (255, 255, 255)], 150, 0, 180, 0.65, size=4.0, gravity=130)
        # Leaf scatter
        self.emit(x, y, 6, [C.C_LEAF_A, C.C_LEAF_B], 80, 270, 80, 0.9, size=2.5, gravity=180)

    def emit_player_hurt(self, x: float, y: float) -> None:
        self.emit(x, y, 10, [(255, 150, 150), (255, 80, 80)], 160, 270, 180, 0.55, size=3.5, gravity=120)

    def emit_dash_trail(self, x: float, y: float) -> None:
        self.emit(x, y, 4, [C.C_DASH_TRAIL, (180, 230, 255)], 40, random.uniform(0, 360), 180, 0.22, size=3.5)

    def emit_coin_pickup(self, x: float, y: float) -> None:
        self.emit(x, y, 5, [C.C_COIN, (255, 240, 100)], 100, 270, 70, 0.42, size=2.5, gravity=-60)

    def emit_wolf_lunge(self, x: float, y: float, angle_deg: float) -> None:
        """Speed-blur when wolf lunges."""
        self.emit(x, y, 8, [C.C_WOLF, (200, 185, 168), (255, 255, 255)], 70, angle_deg + 180, 40, 0.28, size=3.0)

    def emit_spore_death(self, x: float, y: float) -> None:
        """Plant explodes in a shower of spores."""
        self.emit(x, y, 16, [(75, 185, 55), (55, 140, 38), (130, 210, 90)], 135, 0, 180, 0.75, size=4.5, gravity=100)
        self.emit(x, y, 8, [(200, 240, 100), (160, 220, 60)], 60, 270, 80, 1.0, size=2.5, gravity=200)

    def emit_room_clear(self, cx: float, cy: float) -> None:
        """Celebratory burst when the last enemy dies."""
        self.emit(cx, cy, 25, [C.C_COIN, (200, 255, 150), (255, 255, 255)], 220, 0, 180, 0.9, size=4.5, gravity=80)

    def emit_shaman_phase2(self, x: float, y: float) -> None:
        """Phase-2 burst when Goblin Shaman crosses 50 % HP."""
        self.emit(x, y, 22, [(205, 100, 255), (165, 50, 200), (255, 255, 255)], 200, 0, 180, 0.75, size=4.5)

    def emit_tree_phase2(self, x: float, y: float) -> None:
        """Phase-2 burst when Ancient Tree crosses 50 % HP."""
        self.emit(x, y, 24, [(88, 55, 20), (130, 195, 55), (200, 240, 100)], 180, 0, 180, 0.85, size=5.0)
        self.emit(x, y, 10, [(255, 255, 255), (200, 240, 100)], 80, 270, 80, 1.1, size=2.5, gravity=200)

    def emit_shaman_death(self, x: float, y: float) -> None:
        self.emit(x, y, 20, [(165, 90, 210), (205, 100, 255), (255, 220, 255)], 170, 0, 180, 0.80, size=5.0)
        self.emit(x, y, 8, [(255, 200, 255), (200, 100, 255)], 90, 270, 70, 1.0, size=3.0, gravity=150)

    def emit_tree_death(self, x: float, y: float) -> None:
        self.emit(x, y, 28, [(75, 185, 55), (42, 88, 28), (130, 210, 90)], 200, 0, 180, 0.90, size=6.0, gravity=80)
        self.emit(x, y, 12, [(88, 55, 20), (130, 195, 55)], 80, 270, 80, 1.2, size=3.5, gravity=200)
        self.emit(x, y, 6, [(255, 255, 255), (200, 240, 100)], 120, 0, 180, 0.6, size=2.0)

    def emit_summon_flash(self, x: float, y: float) -> None:
        """Sparkle at the shaman position when it summons minions."""
        self.emit(x, y, 12, [(205, 100, 255), (255, 255, 255), (165, 90, 210)], 140, 0, 180, 0.50, size=3.0)

    # ── Boss phase-2 bursts ────────────────────────────────────────────────────

    def emit_warden_phase2(self, x: float, y: float) -> None:
        """Phase-2 burst when Iron Warden crosses 50 % HP."""
        self.emit(x, y, 20, [C.C_WARDEN_SPARK, C.C_WARDEN, (255, 250, 200)], 220, 0, 180, 0.70, size=4.5)
        self.emit(x, y, 10, [(160, 140, 100), (200, 170, 120)], 90, 270, 80, 0.90, size=2.5, gravity=200)

    def emit_leech_phase2(self, x: float, y: float) -> None:
        """Phase-2 burst when Abyssal Leech crosses 50 % HP."""
        self.emit(x, y, 22, [C.C_LEECH_SHOT, C.C_LEECH, (180, 240, 255)], 190, 0, 180, 0.80, size=4.5)
        self.emit(x, y, 8, [(40, 185, 210), (14, 42, 60)], 70, 0, 180, 1.00, size=3.0)

    def emit_matriarch_phase2(self, x: float, y: float) -> None:
        """Phase-2 burst when Fungal Matriarch crosses 50 % HP."""
        self.emit(x, y, 24, [C.C_MATRIARCH_SPORE, C.C_MATRIARCH, (200, 255, 120)], 180, 0, 180, 0.85, size=5.0)
        self.emit(x, y, 12, [(155, 210, 85), (220, 255, 150)], 80, 270, 80, 1.10, size=2.5, gravity=200)

    def emit_sovereign_phase2(self, x: float, y: float) -> None:
        """Phase-2 burst when Void Sovereign crosses 50 % HP — deep void explosion."""
        self.emit(x, y, 30, [C.C_SOVEREIGN_SHOT, (80, 20, 160), (200, 130, 255)], 240, 0, 180, 0.90, size=5.5)
        self.emit(x, y, 14, [C.C_SOVEREIGN, (130, 55, 255)], 100, 0, 180, 1.20, size=3.0)

    # ── Boss death bursts ──────────────────────────────────────────────────────

    def emit_warden_death(self, x: float, y: float) -> None:
        self.emit(x, y, 22, [C.C_WARDEN_SPARK, C.C_WARDEN, (255, 250, 200)], 190, 0, 180, 0.90, size=5.5, gravity=80)
        self.emit(x, y, 10, [(200, 170, 120), (130, 110, 80)], 80, 270, 70, 1.20, size=3.5, gravity=200)

    def emit_leech_death(self, x: float, y: float) -> None:
        self.emit(x, y, 26, [C.C_LEECH_SHOT, C.C_LEECH, (180, 240, 255)], 200, 0, 180, 0.95, size=6.0, gravity=80)
        self.emit(x, y, 10, [(40, 185, 210), (14, 42, 60)], 80, 270, 80, 1.20, size=3.5, gravity=200)

    def emit_matriarch_death(self, x: float, y: float) -> None:
        self.emit(
            x, y, 30, [C.C_MATRIARCH_SPORE, C.C_MATRIARCH, (200, 255, 120)], 200, 0, 180, 1.00, size=6.5, gravity=70
        )
        self.emit(x, y, 14, [(155, 210, 85), (220, 255, 150)], 80, 270, 80, 1.30, size=3.5, gravity=200)
        self.emit(x, y, 6, [(255, 255, 255), (200, 255, 150)], 120, 0, 180, 0.60, size=2.0)

    def emit_sovereign_death(self, x: float, y: float) -> None:
        self.emit(x, y, 35, [C.C_SOVEREIGN_SHOT, (80, 20, 160), (200, 130, 255)], 250, 0, 180, 1.00, size=7.0)
        self.emit(x, y, 18, [C.C_SOVEREIGN, (130, 55, 255), (255, 255, 255)], 100, 0, 180, 1.50, size=4.0)
        self.emit(x, y, 10, [(255, 255, 255), (200, 150, 255)], 60, 0, 180, 0.80, size=2.5)
