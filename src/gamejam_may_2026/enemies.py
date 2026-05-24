"""Enemy classes — GoblinRunner, GoblinArcher, Wolf, SporePlant,
StoneCrawler, VenomfangBat, CrystalTurret."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame

from gamejam_may_2026 import constants as C
from gamejam_may_2026 import sounds
from gamejam_may_2026.projectiles import EnemyProjectile

if TYPE_CHECKING:
    from gamejam_may_2026.camera import Camera
    from gamejam_may_2026.particles import ParticleSystem
    from gamejam_may_2026.player import Player
    from gamejam_may_2026.rooms import Room


# ── Base ───────────────────────────────────────────────────────────────────────


class Enemy:
    # Override in subclasses to get correct death particle colours
    _DEATH_COLOR_A: tuple[int, int, int] = C.C_GOBLIN
    _DEATH_COLOR_B: tuple[int, int, int] = C.C_LEAF_A

    def __init__(
        self,
        x: float,
        y: float,
        hp: int,
        radius: int,
        speed: float,
        coin_drop: int,
    ) -> None:
        self.x = x
        self.y = y
        self.hp = hp
        self.max_hp = hp
        self.radius = radius
        self.speed = speed
        self.coin_drop = coin_drop
        self.alive = True
        self._iframes = 0.0  # hit-stagger iframes
        self._flash = 0.0  # white-flash timer

    def _move(self, dx: float, dy: float, room: Room) -> None:
        # Sub-step to avoid large-step wall gaps and diagonal tunnelling.
        _SUBSTEP = 4.0
        steps = max(1, math.ceil(abs(dx) / _SUBSTEP))
        sdx = dx / steps
        for _ in range(steps):
            if room.is_circle_walkable(self.x + sdx, self.y, self.radius):
                self.x += sdx
            else:
                break
        steps = max(1, math.ceil(abs(dy) / _SUBSTEP))
        sdy = dy / steps
        for _ in range(steps):
            if room.is_circle_walkable(self.x, self.y + sdy, self.radius):
                self.y += sdy
            else:
                break

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        if self._iframes > 0:
            return
        self.hp -= damage
        self._iframes = 0.18
        self._flash = 0.10
        sounds.play("hit_enemy")
        particles.emit_enemy_hit(self.x, self.y)
        if self.hp <= 0:
            self.alive = False
            sounds.play("enemy_death")
            particles.emit_death(self.x, self.y, self._DEATH_COLOR_A, self._DEATH_COLOR_B)

    def _draw_body(
        self,
        surf: pygame.Surface,
        camera: Camera,
        base: tuple[int, int, int],
        dark: tuple[int, int, int],
    ) -> tuple[int, int]:
        """Draw the shared body circle and return (sx, sy) screen coords."""
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        color = (255, 255, 255) if self._flash > 0 else base
        # Shadow
        pygame.draw.circle(surf, (8, 8, 8), (sx + 2, sy + 4), self.radius - 2)
        # Body
        pygame.draw.circle(surf, color, (sx, sy), self.radius)
        # Lower shading
        if self._flash <= 0:
            pygame.draw.circle(surf, dark, (sx, sy + self.radius // 3), self.radius // 2)
        # HP bar (only when hurt)
        if self.hp < self.max_hp:
            bw = self.radius * 2
            bx, by = sx - self.radius, sy - self.radius - 8
            pygame.draw.rect(surf, (60, 0, 0), (bx, by, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, (210, 50, 50), (bx, by, fill, 4))
        return sx, sy


# ── Goblin Runner ──────────────────────────────────────────────────────────────


class GoblinRunner(Enemy):
    _DEATH_COLOR_A = C.C_GOBLIN
    _DEATH_COLOR_B = C.C_LEAF_A

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.GOBLIN_HP + (floor - 1)  # 3 / 4 / 5
        speed = C.GOBLIN_SPEED * (1.0 + (floor - 1) * 0.08)  # ~88 / 95 / 103
        super().__init__(x, y, hp=hp, radius=C.GOBLIN_RADIUS, speed=speed, coin_drop=C.GOBLIN_COIN_DROP)
        self._contact_cd = 0.0

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        _projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)
        self._contact_cd = max(0.0, self._contact_cd - dt)

        # Chase player
        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            self._move(dx / dist * self.speed * dt, dy / dist * self.speed * dt, room)

        # Contact damage
        if self._contact_cd <= 0:
            if math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
                if player.take_damage(C.GOBLIN_DAMAGE):
                    particles.emit_player_hurt(player.x, player.y)
                self._contact_cd = 0.4

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = self._draw_body(surf, camera, C.C_GOBLIN, C.C_GOBLIN_DARK)
        if self._flash <= 0:
            for ex in (-5, 5):
                pygame.draw.circle(surf, (10, 10, 10), (sx + ex, sy - 4), 3)
                pygame.draw.circle(surf, (255, 240, 50), (sx + ex, sy - 4), 1)


# ── Goblin Archer ──────────────────────────────────────────────────────────────


class GoblinArcher(Enemy):
    _DEATH_COLOR_A = C.C_GOBLIN
    _DEATH_COLOR_B = C.C_LEAF_A

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp    = round(C.ARCHER_HP * (1 + (floor - 1) * 0.18))
        speed = C.ARCHER_SPEED * (1 + (floor - 1) * 0.07)
        super().__init__(
            x, y, hp=hp, radius=C.ARCHER_RADIUS, speed=speed, coin_drop=C.ARCHER_COIN_DROP
        )
        self._shoot_cd = random.uniform(0.5, 1.8)
        self._winding = False
        self._wind_up = 0.0

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        # Maintain preferred range
        if dist < C.ARCHER_PREF_DIST * 0.7 and dist > 0:
            self._move(-dx / dist * self.speed * dt, -dy / dist * self.speed * dt, room)
        elif dist > C.ARCHER_PREF_DIST * 1.3 and dist > 0:
            self._move(dx / dist * self.speed * 0.5 * dt, dy / dist * self.speed * 0.5 * dt, room)

        # Shooting state machine
        self._shoot_cd -= dt
        if self._shoot_cd <= 0.5 and not self._winding:
            self._winding = True
            self._wind_up = 0.0

        if self._winding:
            self._wind_up += dt
            if self._wind_up >= 0.5:
                angle = math.atan2(dy, dx)
                projs.append(EnemyProjectile(self.x, self.y, angle))
                sounds.play("spore_shoot")
                self._shoot_cd = C.ARCHER_SHOOT_CD
                self._winding = False
                self._wind_up = 0.0

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        if self._winding:
            sx, sy = camera.apply_pos(self.x, self.y)
            pulse = min(255, int(self._wind_up / 0.5 * 255))
            pygame.draw.circle(surf, (pulse, pulse // 3, 0), (round(sx), round(sy)), self.radius + 8, 2)
        sx, sy = self._draw_body(surf, camera, (180, 140, 75), (120, 95, 50))
        if self._flash <= 0:
            pygame.draw.circle(surf, (10, 10, 10), (sx - 4, sy - 3), 2)
            pygame.draw.circle(surf, (10, 10, 10), (sx + 4, sy - 3), 2)


# ── Wolf ───────────────────────────────────────────────────────────────────────


class Wolf(Enemy):
    _DEATH_COLOR_A = C.C_WOLF
    _DEATH_COLOR_B = (190, 170, 155)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.WOLF_HP + (floor - 1)  # 2 / 3 / 4
        super().__init__(x, y, hp=hp, radius=C.WOLF_RADIUS, speed=C.WOLF_SPEED, coin_drop=C.WOLF_COIN_DROP)
        self._t = random.uniform(0.0, 6.28)  # phase for wobble variety
        self._lunging = False
        self._lunge_cd = random.uniform(0.5, 1.5)  # stagger first lunge
        self._lunge_dx = 0.0
        self._lunge_dy = 0.0
        self._lunge_t = 0.0
        self._contact_cd = 0.0

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        _projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)
        self._lunge_cd = max(0.0, self._lunge_cd - dt)
        self._contact_cd = max(0.0, self._contact_cd - dt)
        self._t += dt

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        if self._lunging:
            # Fly forward at high speed
            self._lunge_t -= dt
            if self._lunge_t <= 0:
                self._lunging = False
                self._lunge_cd = C.WOLF_LUNGE_CD
            else:
                self._move(
                    self._lunge_dx * C.WOLF_LUNGE_SPEED * dt,
                    self._lunge_dy * C.WOLF_LUNGE_SPEED * dt,
                    room,
                )
                angle_deg = math.degrees(math.atan2(self._lunge_dy, self._lunge_dx))
                particles.emit_wolf_lunge(self.x, self.y, angle_deg)
        else:
            # Wobbling approach — oscillate perpendicular to chase direction
            if dist > 0:
                nx, ny = dx / dist, dy / dist
                wobble = math.sin(self._t * 2.4) * 0.65
                mx = nx + (-ny * wobble)
                my = ny + (nx * wobble)
                mag = math.hypot(mx, my) or 1.0
                self._move(mx / mag * self.speed * dt, my / mag * self.speed * dt, room)

            # Trigger lunge when close enough
            if dist <= C.WOLF_LUNGE_RANGE and self._lunge_cd <= 0 and dist > 0:
                self._lunging = True
                self._lunge_t = C.WOLF_LUNGE_DUR
                self._lunge_dx = dx / dist
                self._lunge_dy = dy / dist
                sounds.play("wolf_lunge")

        # Contact damage (during both lunge and approach)
        if self._contact_cd <= 0:
            if math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
                if player.take_damage(C.GOBLIN_DAMAGE):
                    particles.emit_player_hurt(player.x, player.y)
                self._contact_cd = 0.35

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        # Lunge aura
        if self._lunging:
            sx0, sy0 = camera.apply_pos(self.x, self.y)
            pygame.draw.circle(surf, (200, 210, 255), (round(sx0), round(sy0)), self.radius + 6, 2)

        sx, sy = self._draw_body(surf, camera, C.C_WOLF, (100, 88, 76))

        if self._flash <= 0:
            # Ears (two small triangles above body)
            r = self.radius
            for ex in (-5, 5):
                ear = [
                    (sx + ex, sy - r - 7),
                    (sx + ex - 4, sy - r + 2),
                    (sx + ex + 4, sy - r + 2),
                ]
                pygame.draw.polygon(surf, C.C_WOLF, ear)
            # Yellow eyes
            for ex in (-4, 4):
                pygame.draw.circle(surf, (228, 198, 28), (sx + ex, sy - 3), 3)
                pygame.draw.circle(surf, (10, 10, 10), (sx + ex, sy - 3), 1)


# ── Spore Plant ────────────────────────────────────────────────────────────────


class SporePlant(Enemy):
    """Stationary plant that fires 4-direction spore volleys, alternating ±45°."""

    _DEATH_COLOR_A = (75, 185, 55)
    _DEATH_COLOR_B = (55, 140, 38)

    _NUM_SPOKES = 6  # decorative spines drawn on the body
    _WIND_DUR = 0.55

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.SPLANT_HP + (floor - 1) * 2  # 5 / 7 / 9
        super().__init__(x, y, hp=hp, radius=C.SPLANT_RADIUS, speed=0.0, coin_drop=C.SPLANT_COIN_DROP)
        self._shoot_cd = random.uniform(0.6, C.SPLANT_SHOOT_CD)
        self._winding = False
        self._wind_up = 0.0
        self._rotation = 0.0  # 0° or 45° alternating
        self._pulse_t = random.uniform(0.0, 6.28)

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        if self._iframes > 0:
            return
        self.hp -= damage
        self._iframes = 0.18
        self._flash = 0.10
        sounds.play("hit_enemy")
        particles.emit_enemy_hit(self.x, self.y)
        if self.hp <= 0:
            self.alive = False
            sounds.play("enemy_death")
            particles.emit_spore_death(self.x, self.y)  # special burst

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)
        self._pulse_t += dt * 2.2
        self._shoot_cd -= dt

        # Wind-up phase
        if self._shoot_cd <= self._WIND_DUR and not self._winding:
            self._winding = True
            self._wind_up = 0.0

        if self._winding:
            self._wind_up += dt
            if self._wind_up >= self._WIND_DUR:
                # Fire 4 spores at current rotation
                for i in range(4):
                    angle = math.radians(self._rotation + i * 90.0)
                    projs.append(
                        EnemyProjectile(
                            self.x,
                            self.y,
                            angle,
                            speed=C.SPORE_SPEED,
                            color=C.C_SPORE,
                            damage=C.SPORE_DAMAGE,
                            lifetime=C.SPORE_LIFETIME,
                        )
                    )
                sounds.play("spore_shoot")
                self._rotation = 45.0 if self._rotation == 0.0 else 0.0
                self._shoot_cd = C.SPLANT_SHOOT_CD
                self._winding = False
                self._wind_up = 0.0

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)

        # Pulsing outer ring
        pulse = (math.sin(self._pulse_t) + 1.0) * 0.5  # 0..1
        ring_r = self.radius + 3 + round(pulse * 4)
        ring_g = int(100 + pulse * 80)
        pygame.draw.circle(surf, (28, ring_g, 28), (sx, sy), ring_r, 2)

        # Wind-up glow
        if self._winding:
            frac = self._wind_up / self._WIND_DUR
            glow_r = self.radius + round(frac * 12)
            glow_c = (min(255, round(30 + frac * 60)), min(255, round(160 + frac * 95)), 30)
            pygame.draw.circle(surf, glow_c, (sx, sy), glow_r, 3)

        # Spines radiating out
        for i in range(self._NUM_SPOKES):
            angle = math.radians(self._rotation + i * (360 / self._NUM_SPOKES))
            ex = sx + round(math.cos(angle) * (self.radius + 9))
            ey = sy + round(math.sin(angle) * (self.radius + 9))
            pygame.draw.line(surf, (48, 145, 38), (sx, sy), (ex, ey), 2)

        # Shadow + body
        pygame.draw.circle(surf, (8, 8, 8), (sx + 2, sy + 4), self.radius - 2)
        body_col = (255, 255, 255) if self._flash > 0 else (52, 118, 42)
        pygame.draw.circle(surf, body_col, (sx, sy), self.radius)
        if self._flash <= 0:
            pygame.draw.circle(surf, (34, 82, 28), (sx, sy + self.radius // 3), self.radius // 2)

        # Centre pip
        pygame.draw.circle(surf, (28, 58, 22), (sx, sy), 4)

        # Green HP bar (different colour from goblin red)
        if self.hp < self.max_hp:
            bw = self.radius * 2
            bx, by = sx - self.radius, sy - self.radius - 9
            pygame.draw.rect(surf, (30, 0, 0), (bx, by, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, (70, 200, 55), (bx, by, fill, 4))


# ── Goblin Shaman (boss — floors 1 & 2) ──────────────────────────────────────


class GoblinShaman(Enemy):
    """Ranged boss: fires magic bolt bursts and periodically summons runners."""

    is_boss_enemy = True
    boss_name = "Goblin Shaman"

    _DEATH_COLOR_A = C.C_SHAMAN
    _DEATH_COLOR_B = (220, 160, 255)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.SHAMAN_HP if floor == 1 else C.SHAMAN_HP_F2
        super().__init__(x, y, hp=hp, radius=C.SHAMAN_RADIUS, speed=C.SHAMAN_SPEED, coin_drop=C.SHAMAN_COIN_DROP)
        self.floor = floor
        # Minion-summon queue — game.py drains this each frame
        self._summon_queue: list[Enemy] = []

        # Bolt attack
        self._bolt_cd = random.uniform(1.0, C.SHAMAN_BOLT_CD)
        self._winding = False
        self._wind_up = 0.0

        # Summon attack
        self._summon_cd = C.SHAMAN_SUMMON_CD

        # Visual
        self._bob_t = random.uniform(0.0, 6.28)
        self._staff_angle = -math.pi / 3
        self._phase2_done = False  # flag to fire phase-2 burst once

    @property
    def _phase2(self) -> bool:
        return self.hp <= self.max_hp // 2

    # Override take_hit so game.py can detect the phase-2 transition
    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        was_p2 = self._phase2
        super().take_hit(damage, particles)
        if not was_p2 and self._phase2 and self.alive:
            self.phase2_just_triggered = True
            particles.emit_shaman_phase2(self.x, self.y)
        if not self.alive:
            particles.emit_shaman_death(self.x, self.y)

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)
        self._bob_t += dt

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        # Orbit: close in if far, back off if too close
        if dist > 200 and dist > 0:
            self._move(dx / dist * self.speed * dt, dy / dist * self.speed * dt, room)
        elif dist < 120 and dist > 0:
            self._move(-dx / dist * self.speed * 0.6 * dt, -dy / dist * self.speed * 0.6 * dt, room)

        if dist > 0:
            self._staff_angle = math.atan2(dy, dx)

        # ── Bolt volley ───────────────────────────────────────────────────────
        bolt_cd = C.SHAMAN_BOLT_CD_P2 if self._phase2 else C.SHAMAN_BOLT_CD
        wind_dur = 0.35 if self._phase2 else 0.50
        self._bolt_cd -= dt

        if self._bolt_cd <= wind_dur and not self._winding:
            self._winding = True
            self._wind_up = 0.0

        if self._winding:
            self._wind_up += dt
            if self._wind_up >= wind_dur:
                num = 5 if self._phase2 else 3
                spread = math.radians(40 if self._phase2 else 25)
                base = math.atan2(dy, dx)
                step = spread * 2 / max(1, num - 1)
                for i in range(num):
                    a = base - spread + i * step
                    projs.append(
                        EnemyProjectile(
                            self.x,
                            self.y,
                            a,
                            speed=210,
                            color=C.C_SHAMAN_BOLT,
                            damage=1,
                            lifetime=2.0,
                        )
                    )
                sounds.play("spore_shoot")
                self._bolt_cd = bolt_cd
                self._winding = False
                self._wind_up = 0.0

        # ── Minion summon ─────────────────────────────────────────────────────
        summon_cd = C.SHAMAN_SUMMON_CD_P2 if self._phase2 else C.SHAMAN_SUMMON_CD
        self._summon_cd -= dt
        if self._summon_cd <= 0:
            n_pos = 3 if self._phase2 else 2
            positions = room.get_spawn_positions(n_pos, min_dist_from_centre=150.0)
            for i, pos in enumerate(positions):
                if i < 2:
                    self._summon_queue.append(GoblinRunner(*pos, floor=self.floor))
                else:
                    self._summon_queue.append(GoblinArcher(*pos))
            particles.emit_summon_flash(self.x, self.y)
            self._summon_cd = summon_cd

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)

        # Phase-2 aura (pulsing ring)
        if self._phase2:
            pulse = (math.sin(self._bob_t * 3.5) + 1) * 0.5
            ring_r = self.radius + 8 + round(pulse * 6)
            pygame.draw.circle(surf, (180, 70, 255), (sx, sy), ring_r, 2)

        # Wind-up glow
        if self._winding:
            frac = self._wind_up / (0.35 if self._phase2 else 0.50)
            glow = self.radius + round(frac * 20)
            col = (min(255, round(165 + frac * 90)), min(255, round(90 + frac * 50)), 210)
            pygame.draw.circle(surf, col, (sx, sy), glow, 3)

        # Staff arm
        sa = self._staff_angle
        sr = self.radius + 18
        ex = sx + round(math.cos(sa) * sr)
        ey = sy + round(math.sin(sa) * sr)
        pygame.draw.line(surf, (140, 100, 50), (sx, sy), (ex, ey), 3)
        pygame.draw.circle(surf, C.C_SHAMAN_BOLT, (ex, ey), 5)
        pygame.draw.circle(surf, (255, 200, 255), (ex, ey), 3)

        # Body
        body_sx, body_sy = self._draw_body(surf, camera, C.C_SHAMAN, C.C_SHAMAN_DARK)

        # Eyes
        if self._flash <= 0:
            for ex_off in (-5, 5):
                pygame.draw.circle(surf, (255, 220, 50), (body_sx + ex_off, body_sy - 4), 3)
                pygame.draw.circle(surf, (200, 80, 255), (body_sx + ex_off, body_sy - 4), 1)


# ── Ancient Tree (boss — floor 3) ─────────────────────────────────────────────


class AncientTree(Enemy):
    """Stationary floor-3 boss: alternating root volleys + fast thorn rings."""

    is_boss_enemy = True
    boss_name = "Ancient Tree"

    _DEATH_COLOR_A = (75, 185, 55)
    _DEATH_COLOR_B = (42, 88, 28)

    def __init__(self, x: float, y: float) -> None:
        super().__init__(x, y, hp=C.TREE_HP, radius=C.TREE_RADIUS, speed=0.0, coin_drop=C.TREE_COIN_DROP)

        # Root burst
        self._root_cd = C.TREE_ROOT_CD
        self._root_rot = 0.0  # alternates 0° / 45°
        self._root_winding = False
        self._root_wind_up = 0.0

        # Thorn ring
        self._thorn_cd = C.TREE_THORN_CD
        self._thorn_winding = False
        self._thorn_wind_up = 0.0

        # Visual
        self._pulse_t = random.uniform(0.0, 6.28)
        self._spin_angle = 0.0  # slowly-rotating root decorations

    @property
    def _phase2(self) -> bool:
        return self.hp <= self.max_hp // 2

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        was_p2 = self._phase2
        super().take_hit(damage, particles)
        if not was_p2 and self._phase2 and self.alive:
            self.phase2_just_triggered = True
            particles.emit_tree_phase2(self.x, self.y)
        if not self.alive:
            particles.emit_tree_death(self.x, self.y)

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)
        self._pulse_t += dt * 1.4
        self._spin_angle += dt * 18  # degrees / s  (slow spin for visuals)

        # ── Root burst ────────────────────────────────────────────────────────
        root_cd = C.TREE_ROOT_CD_P2 if self._phase2 else C.TREE_ROOT_CD
        wind_dur = 0.70
        self._root_cd -= dt

        if self._root_cd <= wind_dur and not self._root_winding:
            self._root_winding = True
            self._root_wind_up = 0.0

        if self._root_winding:
            self._root_wind_up += dt
            if self._root_wind_up >= wind_dur:
                num = 8 if self._phase2 else 4
                for i in range(num):
                    angle = math.radians(self._root_rot + i * (360.0 / num))
                    projs.append(
                        EnemyProjectile(
                            self.x,
                            self.y,
                            angle,
                            speed=C.SPORE_SPEED,
                            color=C.C_TREE_ROOT,
                            damage=1,
                            lifetime=3.5,
                        )
                    )
                sounds.play("spore_shoot")
                self._root_rot = 45.0 if self._root_rot == 0.0 else 0.0
                self._root_cd = root_cd
                self._root_winding = False
                self._root_wind_up = 0.0

        # ── Thorn ring ────────────────────────────────────────────────────────
        thorn_cd = C.TREE_THORN_CD_P2 if self._phase2 else C.TREE_THORN_CD
        wind_dur2 = 0.85
        self._thorn_cd -= dt

        if self._thorn_cd <= wind_dur2 and not self._thorn_winding:
            self._thorn_winding = True
            self._thorn_wind_up = 0.0

        if self._thorn_winding:
            self._thorn_wind_up += dt
            if self._thorn_wind_up >= wind_dur2:
                for i in range(8):
                    angle = math.radians(i * 45.0)
                    projs.append(
                        EnemyProjectile(
                            self.x,
                            self.y,
                            angle,
                            speed=290,
                            color=C.C_THORN,
                            damage=1,
                            lifetime=2.2,
                        )
                    )
                if self._phase2:
                    for i in range(8):
                        angle = math.radians(22.5 + i * 45.0)
                        projs.append(
                            EnemyProjectile(
                                self.x,
                                self.y,
                                angle,
                                speed=220,
                                color=(160, 215, 65),
                                damage=1,
                                lifetime=2.2,
                            )
                        )
                sounds.play("wolf_lunge")
                self._thorn_cd = thorn_cd
                self._thorn_winding = False
                self._thorn_wind_up = 0.0

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius
        pulse = (math.sin(self._pulse_t) + 1) * 0.5

        # Root tendrils (slowly rotating)
        for i in range(8):
            angle = math.radians(self._spin_angle + i * 45.0)
            length = r + 16 + round(pulse * 7)
            ex = sx + round(math.cos(angle) * length)
            ey = sy + round(math.sin(angle) * length)
            pygame.draw.line(surf, C.C_TREE_ROOT, (sx, sy), (ex, ey), 2)

        # Root wind-up glow
        if self._root_winding:
            frac = self._root_wind_up / 0.70
            glow_r = r + round(frac * 20)
            pygame.draw.circle(surf, C.C_TREE_ROOT, (sx, sy), glow_r, 3)

        # Thorn wind-up glow (outer ring, different colour)
        if self._thorn_winding:
            frac = self._thorn_wind_up / 0.85
            glow_r = r + round(frac * 30)
            pygame.draw.circle(surf, C.C_THORN, (sx, sy), glow_r, 2)

        # Shadow
        pygame.draw.circle(surf, (8, 8, 8), (sx + 3, sy + 6), r - 2)

        # Body
        body_col = (255, 255, 255) if self._flash > 0 else C.C_TREE
        pygame.draw.circle(surf, body_col, (sx, sy), r)
        if self._flash <= 0:
            pygame.draw.circle(surf, C.C_TREE_DARK, (sx, sy + r // 3), r // 2)
            # Bark lines
            for i in range(4):
                a = math.radians(70 + i * 50)
                lx = sx + round(math.cos(a) * r * 0.65)
                ly = sy + round(math.sin(a) * r * 0.65)
                pygame.draw.line(surf, C.C_TREE_DARK, (sx, sy), (lx, ly), 2)

        # Phase-2 outer glow ring
        if self._phase2:
            ring_r = r + 8 + round(pulse * 5)
            pygame.draw.circle(surf, (100, 200, 55), (sx, sy), ring_r, 2)


# ── Stone Crawler (floor 4+) ──────────────────────────────────────────────────


class StoneCrawler(Enemy):
    """Armoured melee chaser — first 3 arrow hits are deflected by its stone shell.
    Shell breaks after 3 deflects; resets only on room re-entry (via game.py)."""

    _DEATH_COLOR_A = C.C_CRAWLER
    _DEATH_COLOR_B = (200, 180, 155)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp    = C.CRAWLER_HP + max(0, floor - 4) * 2   # 8 / 10 / 12 …
        speed = C.CRAWLER_SPEED + max(0, floor - 4) * 5.0
        super().__init__(x, y, hp=hp, radius=C.CRAWLER_RADIUS,
                         speed=speed, coin_drop=C.CRAWLER_COIN_DROP)
        self._shell_hits   = C.CRAWLER_SHELL_HITS  # deflect charges remaining
        self._contact_cd   = 0.0
        self._deflect_flash = 0.0   # brief bright-grey flash on deflect

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        if self._iframes > 0:
            return
        if self._shell_hits > 0:
            # Shell deflects this hit — no HP lost
            self._shell_hits -= 1
            self._iframes     = 0.18
            self._deflect_flash = 0.14
            sounds.play("hit_wall")           # metallic clank
            particles.emit_enemy_hit(self.x, self.y)
            return
        super().take_hit(damage, particles)

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        _projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes       = max(0.0, self._iframes - dt)
        self._flash         = max(0.0, self._flash - dt)
        self._deflect_flash = max(0.0, self._deflect_flash - dt)
        self._contact_cd    = max(0.0, self._contact_cd - dt)

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            self._move(dx / dist * self.speed * dt, dy / dist * self.speed * dt, room)

        if self._contact_cd <= 0:
            if math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
                if player.take_damage(C.CRAWLER_DAMAGE):
                    particles.emit_player_hurt(player.x, player.y)
                self._contact_cd = 0.55

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius

        # Shell ring (visible while charges remain)
        if self._shell_hits > 0:
            shell_col = (220, 210, 195) if self._deflect_flash > 0 else (155, 142, 122)
            pygame.draw.circle(surf, shell_col, (sx, sy), r + 4, 3)
            # Small pips showing remaining charges
            for i in range(self._shell_hits):
                angle = math.radians(-90 + i * (360 / C.CRAWLER_SHELL_HITS))
                px2 = sx + round(math.cos(angle) * (r + 9))
                py2 = sy + round(math.sin(angle) * (r + 9))
                pygame.draw.circle(surf, (215, 200, 180), (px2, py2), 3)

        # Body
        if self._deflect_flash > 0:
            color = (235, 228, 215)
        elif self._flash > 0:
            color = (255, 255, 255)
        else:
            color = C.C_CRAWLER
        pygame.draw.circle(surf, (8, 8, 8), (sx + 2, sy + 4), r - 2)   # shadow
        pygame.draw.circle(surf, color, (sx, sy), r)
        if self._deflect_flash <= 0 and self._flash <= 0:
            pygame.draw.circle(surf, C.C_CRAWLER_DARK, (sx, sy + r // 3), r // 2)
            # Stone crack lines
            pygame.draw.line(surf, C.C_CRAWLER_DARK, (sx - 6, sy - 4), (sx + 2, sy + 5), 1)
            pygame.draw.line(surf, C.C_CRAWLER_DARK, (sx + 4, sy - 6), (sx + 1, sy + 3), 1)

        # HP bar
        if self.hp < self.max_hp:
            bw = r * 2
            bx2, by2 = sx - r, sy - r - 8
            pygame.draw.rect(surf, (40, 30, 15), (bx2, by2, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, (185, 162, 128), (bx2, by2, fill, 4))


# ── VenomfangBat (floor 4+) ───────────────────────────────────────────────────


class VenomfangBat(Enemy):
    """Fast arc-mover — poisons the player on contact."""

    _DEATH_COLOR_A = C.C_BAT
    _DEATH_COLOR_B = (155, 100, 210)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        speed = C.BAT_SPEED + max(0, floor - 4) * 8.0
        super().__init__(x, y, hp=C.BAT_HP, radius=C.BAT_RADIUS,
                         speed=speed, coin_drop=C.BAT_COIN_DROP)
        self._t          = random.uniform(0.0, 6.28)   # wobble phase
        self._contact_cd = 0.0

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        _projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes    = max(0.0, self._iframes - dt)
        self._flash      = max(0.0, self._flash - dt)
        self._contact_cd = max(0.0, self._contact_cd - dt)
        self._t         += dt

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            nx, ny = dx / dist, dy / dist
            # Arc wobble — perpendicular amplitude ~120 px/s
            wobble_amp = 120.0 / (self.speed or 1.0)
            wobble     = math.sin(self._t * 4.0) * wobble_amp
            mx = nx + (-ny * wobble)
            my = ny + (nx * wobble)
            mag = math.hypot(mx, my) or 1.0
            self._move(mx / mag * self.speed * dt, my / mag * self.speed * dt, room)

        if self._contact_cd <= 0:
            if math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
                if player.take_damage(1):
                    player._poison_t = C.BAT_POISON_DUR
                    particles.emit_player_hurt(player.x, player.y)
                self._contact_cd = 0.5

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius

        # Flapping wings
        if self._flash <= 0:
            wing_flap = math.sin(self._t * 9.0)
            for sign in (-1, 1):
                tip_x = sx + sign * round(r + 9 + wing_flap * 4)
                tip_y = sy - 5
                wing_pts = [(sx, sy), (tip_x, tip_y), (sx + sign * (r + 4), sy + 4)]
                pygame.draw.polygon(surf, C.C_BAT_DARK, wing_pts)

        # Shadow + body
        pygame.draw.circle(surf, (8, 8, 8), (sx + 1, sy + 3), r - 1)
        color = (255, 255, 255) if self._flash > 0 else C.C_BAT
        pygame.draw.circle(surf, color, (sx, sy), r)
        if self._flash <= 0:
            pygame.draw.circle(surf, C.C_BAT_DARK, (sx, sy + r // 3), r // 2)
            # Red eyes
            for ex in (-3, 3):
                pygame.draw.circle(surf, (220, 40, 40), (sx + ex, sy - 2), 2)

        # HP bar
        if self.hp < self.max_hp:
            bw = r * 2
            bx2, by2 = sx - r, sy - r - 7
            pygame.draw.rect(surf, (40, 0, 40), (bx2, by2, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, C.C_BAT, (bx2, by2, fill, 4))


# ── Crystal Turret (floor 5+) ─────────────────────────────────────────────────


class CrystalTurret(Enemy):
    """Stationary turret — fires rotating 3-way crystal volleys.
    Immune to arrows from the front face (±60°); takes double damage from behind.
    The red dot on the body marks the vulnerable back face."""

    _DEATH_COLOR_A = C.C_TURRET
    _DEATH_COLOR_B = (200, 240, 255)

    _WIND_DUR = 0.5

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.TURRET_HP + max(0, floor - 5) * 3   # 10 / 13 / 16 …
        super().__init__(x, y, hp=hp, radius=C.TURRET_RADIUS,
                         speed=0.0, coin_drop=C.TURRET_COIN_DROP)
        self._face_angle = random.uniform(0, math.pi * 2)
        self._shoot_cd   = random.uniform(0.5, C.TURRET_SHOOT_CD)
        self._winding    = False
        self._wind_up    = 0.0
        self._pulse_t    = random.uniform(0.0, 6.28)

    def update(
        self,
        dt: float,
        player: Player,
        room: Room,
        particles: ParticleSystem,
        projs: list[EnemyProjectile],
    ) -> None:
        if not self.alive:
            return
        self._iframes  = max(0.0, self._iframes - dt)
        self._flash    = max(0.0, self._flash - dt)
        self._pulse_t += dt * 1.8
        self._shoot_cd -= dt

        if self._shoot_cd <= self._WIND_DUR and not self._winding:
            self._winding  = True
            self._wind_up  = 0.0

        if self._winding:
            self._wind_up += dt
            if self._wind_up >= self._WIND_DUR:
                spread = math.radians(28)
                for off in (-spread, 0.0, spread):
                    projs.append(EnemyProjectile(
                        self.x, self.y,
                        self._face_angle + off,
                        speed=C.TURRET_PROJ_SPEED,
                        color=C.C_TURRET_BEAM,
                        damage=1,
                        lifetime=2.5,
                    ))
                sounds.play("spore_shoot")
                self._face_angle += math.radians(15)   # rotate for next volley
                self._shoot_cd    = C.TURRET_SHOOT_CD
                self._winding     = False
                self._wind_up     = 0.0

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius
        pulse = (math.sin(self._pulse_t) + 1.0) * 0.5

        # Pulsing outer glow ring
        ring_r = r + 3 + round(pulse * 3)
        pygame.draw.circle(surf, C.C_TURRET_DARK, (sx, sy), ring_r, 2)

        # Wind-up charge glow
        if self._winding:
            frac    = self._wind_up / self._WIND_DUR
            glow_r  = r + round(frac * 18)
            pygame.draw.circle(surf, C.C_TURRET_BEAM, (sx, sy), glow_r, 2)

        # Crystal octagon body
        _FACETS = 8
        pts = []
        for i in range(_FACETS):
            a = math.radians(i * 360 / _FACETS + 22.5)
            pts.append((sx + round(math.cos(a) * r), sy + round(math.sin(a) * r)))
        shadow_pts = [(x + 2, y + 3) for x, y in pts]
        pygame.draw.polygon(surf, (8, 8, 8), shadow_pts)
        body_col = (255, 255, 255) if self._flash > 0 else C.C_TURRET
        pygame.draw.polygon(surf, body_col, pts)
        if self._flash <= 0:
            inner = []
            for i in range(_FACETS):
                a = math.radians(i * 360 / _FACETS + 22.5)
                inner.append((sx + round(math.cos(a) * (r - 5)),
                               sy + round(math.sin(a) * (r - 5))))
            pygame.draw.polygon(surf, C.C_TURRET_DARK, inner)

        # Front-face indicator (bright spike in fire direction)
        fa    = self._face_angle
        tip_x = sx + round(math.cos(fa) * (r + 7))
        tip_y = sy + round(math.sin(fa) * (r + 7))
        pygame.draw.line(surf, C.C_TURRET_BEAM, (sx, sy), (tip_x, tip_y), 3)
        pygame.draw.circle(surf, (255, 255, 255), (tip_x, tip_y), 3)

        # Back-face vulnerability marker (red dot on opposite side)
        ba    = fa + math.pi
        bx_t  = sx + round(math.cos(ba) * (r + 5))
        by_t  = sy + round(math.sin(ba) * (r + 5))
        pygame.draw.circle(surf, (210, 55, 55), (bx_t, by_t), 4)

        # HP bar
        if self.hp < self.max_hp:
            bw = r * 2
            bx2, by2 = sx - r, sy - r - 9
            pygame.draw.rect(surf, (20, 30, 40), (bx2, by2, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, C.C_TURRET, (bx2, by2, fill, 4))
