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
        # Status effect timers
        self._poison_t: float = 0.0
        self._slow_t: float = 0.0
        self._burn_t: float = 0.0
        self._stun_t: float = 0.0
        self._bleed_t: float = 0.0
        self._dot_tick: float = 0.0

    def tick_status(self, dt: float, particles: ParticleSystem) -> bool:
        """Tick all status timers. Returns True if stunned (caller skips movement/attacks)."""
        self._poison_t = max(0.0, self._poison_t - dt)
        self._slow_t = max(0.0, self._slow_t - dt)
        self._burn_t = max(0.0, self._burn_t - dt)
        self._stun_t = max(0.0, self._stun_t - dt)
        self._bleed_t = max(0.0, self._bleed_t - dt)
        if self._poison_t > 0 or self._burn_t > 0 or self._bleed_t > 0:
            self._dot_tick += dt
            if self._dot_tick >= 0.5:
                self._dot_tick = 0.0
                dmg = (
                    (1 if self._poison_t > 0 else 0) + (1 if self._burn_t > 0 else 0) + (1 if self._bleed_t > 0 else 0)
                )
                self.hp -= dmg
                if self.hp <= 0:
                    self.alive = False
                    sounds.play("enemy_death")
                    particles.emit_death(self.x, self.y, self._DEATH_COLOR_A, self._DEATH_COLOR_B)
        return self._stun_t > 0

    def _draw_status_rings(self, surf: pygame.Surface, sx: int, sy: int) -> None:
        """Draw coloured status-effect rings around (sx, sy)."""
        t = pygame.time.get_ticks()
        if self._poison_t > 0:
            pulse = (math.sin(t * 0.007) + 1.0) * 0.5
            pygame.draw.circle(surf, (45, 205, 60), (sx, sy), self.radius + 4 + round(pulse * 2), 2)
        if self._slow_t > 0:
            pygame.draw.circle(surf, (150, 200, 255), (sx, sy), self.radius + 4, 2)
        if self._burn_t > 0 and int(t * 0.008) % 2:
            pygame.draw.circle(surf, (255, 140, 30), (sx, sy), self.radius + 4, 2)
        if self._stun_t > 0:
            pygame.draw.circle(surf, (255, 240, 50), (sx, sy), self.radius + 5, 2)
        if self._bleed_t > 0:
            pygame.draw.circle(surf, (140, 10, 10), (sx, sy), self.radius + 3, 2)

    def _move(self, dx: float, dy: float, room: Room) -> None:
        # Slow status: reduce movement to 40 %
        if self._slow_t > 0:
            dx *= 0.4
            dy *= 0.4
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

    def _steer_toward(self, tx: float, ty: float, room: Room) -> tuple[float, float]:
        """8-direction wall-aware steering toward (tx, ty). Returns (vx, vy) at self.speed."""
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy) or 1.0
        goal = (dx / dist, dy / dist)
        best_score, best_dir = -2.0, goal
        probe_r = self.radius * 2
        for i in range(8):
            angle = i * math.pi / 4
            d = (math.cos(angle), math.sin(angle))
            probe_x = self.x + d[0] * probe_r
            probe_y = self.y + d[1] * probe_r
            tc = int(probe_x // C.TILE_SIZE)
            tr = int(probe_y // C.TILE_SIZE)
            wall = (0 <= tc < C.ROOM_TILE_W and 0 <= tr < C.ROOM_TILE_H
                    and room.tiles[tr][tc] == C.TILE_WALL)
            score = d[0] * goal[0] + d[1] * goal[1] - (1.0 if wall else 0.0)
            if score > best_score:
                best_score, best_dir = score, d
        return best_dir[0] * self.speed, best_dir[1] * self.speed

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
        self._draw_status_rings(surf, sx, sy)
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
        if self.tick_status(dt, particles):
            return

        # Chase player with wall-aware steering
        if math.hypot(player.x - self.x, player.y - self.y) > 0:
            vx, vy = self._steer_toward(player.x, player.y, room)
            self._move(vx * dt, vy * dt, room)

        # Contact damage
        if self._contact_cd <= 0 and math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
            if player.take_damage(C.GOBLIN_DAMAGE):
                particles.emit_player_hurt(player.x, player.y)
            self._contact_cd = 0.4

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = self._draw_body(surf, camera, C.C_GOBLIN, C.C_GOBLIN_DARK)
        if self._flash <= 0:
            r = self.radius
            # Pointy goblin ears
            for ex in (-7, 7):
                ear = [
                    (sx + ex, sy - r - 6),
                    (sx + ex - 3, sy - r + 3),
                    (sx + ex + 3, sy - r + 3),
                ]
                pygame.draw.polygon(surf, C.C_GOBLIN, ear)
                pygame.draw.polygon(surf, C.C_GOBLIN_DARK, ear, 1)
            # Eyes
            for ex in (-5, 5):
                pygame.draw.circle(surf, (10, 10, 10), (sx + ex, sy - 4), 3)
                pygame.draw.circle(surf, (255, 240, 50), (sx + ex, sy - 4), 1)
            # Angry brows (angled inward toward nose)
            pygame.draw.line(surf, (20, 20, 10), (sx - 8, sy - 9), (sx - 2, sy - 7), 2)
            pygame.draw.line(surf, (20, 20, 10), (sx + 2, sy - 7), (sx + 8, sy - 9), 2)


# ── Goblin Archer ──────────────────────────────────────────────────────────────


class GoblinArcher(Enemy):
    _DEATH_COLOR_A = C.C_GOBLIN
    _DEATH_COLOR_B = C.C_LEAF_A

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = round(C.ARCHER_HP * (1 + (floor - 1) * 0.18))
        speed = C.ARCHER_SPEED * (1 + (floor - 1) * 0.07)
        super().__init__(x, y, hp=hp, radius=C.ARCHER_RADIUS, speed=speed, coin_drop=C.ARCHER_COIN_DROP)
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
        if self.tick_status(dt, particles):
            return

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
            r = self.radius
            # Bow on the left side (arc + string)
            bow_cx = sx - r - 4
            bow_rect = pygame.Rect(bow_cx - 6, sy - 11, 12, 22)
            pygame.draw.arc(surf, (115, 78, 35), bow_rect, -math.pi / 2, math.pi / 2, 2)
            pygame.draw.line(surf, (195, 170, 120), (bow_cx, sy - 11), (bow_cx, sy + 11), 1)
            # Arrow nocked across body
            pygame.draw.line(surf, (160, 130, 85), (bow_cx + 1, sy), (sx + r + 4, sy), 1)
            # Arrowhead tip
            tip_x = sx + r + 4
            pygame.draw.polygon(surf, (185, 155, 90), [
                (tip_x + 4, sy), (tip_x, sy - 2), (tip_x, sy + 2)])
            # Eyes
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
        if self.tick_status(dt, particles):
            return

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
            # Wobbling approach — steer toward player (wall-aware), oscillate perp
            if dist > 0:
                vx, vy = self._steer_toward(player.x, player.y, room)
                nx, ny = vx / (self.speed or 1.0), vy / (self.speed or 1.0)
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
        if self._contact_cd <= 0 and math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
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
        if self.tick_status(dt, particles):
            return

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
        self._draw_status_rings(surf, sx, sy)


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
        if self.tick_status(dt, particles):
            return

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
        if self.tick_status(dt, particles):
            return

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
        self._draw_status_rings(surf, sx, sy)


# ── Stone Crawler (floor 4+) ──────────────────────────────────────────────────


class StoneCrawler(Enemy):
    """Armoured melee chaser — first 3 arrow hits are deflected by its stone shell.
    Shell breaks after 3 deflects; resets only on room re-entry (via game.py)."""

    _DEATH_COLOR_A = C.C_CRAWLER
    _DEATH_COLOR_B = (200, 180, 155)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.CRAWLER_HP + max(0, floor - 4) * 2  # 8 / 10 / 12 …
        speed = C.CRAWLER_SPEED + max(0, floor - 4) * 5.0
        super().__init__(x, y, hp=hp, radius=C.CRAWLER_RADIUS, speed=speed, coin_drop=C.CRAWLER_COIN_DROP)
        self._shell_hits = C.CRAWLER_SHELL_HITS  # deflect charges remaining
        self._contact_cd = 0.0
        self._deflect_flash = 0.0  # brief bright-grey flash on deflect

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        if self._iframes > 0:
            return
        if self._shell_hits > 0:
            # Shell deflects this hit — no HP lost
            self._shell_hits -= 1
            self._iframes = 0.18
            self._deflect_flash = 0.14
            sounds.play("hit_wall")  # metallic clank
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
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)
        self._deflect_flash = max(0.0, self._deflect_flash - dt)
        self._contact_cd = max(0.0, self._contact_cd - dt)
        if self.tick_status(dt, particles):
            return

        if math.hypot(player.x - self.x, player.y - self.y) > 0:
            vx, vy = self._steer_toward(player.x, player.y, room)
            self._move(vx * dt, vy * dt, room)

        if self._contact_cd <= 0 and math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
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
        pygame.draw.circle(surf, (8, 8, 8), (sx + 2, sy + 4), r - 2)  # shadow
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
        self._draw_status_rings(surf, sx, sy)


# ── VenomfangBat (floor 4+) ───────────────────────────────────────────────────


class VenomfangBat(Enemy):
    """Fast arc-mover — deals contact damage."""

    _DEATH_COLOR_A = C.C_BAT
    _DEATH_COLOR_B = (155, 100, 210)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        speed = C.BAT_SPEED + max(0, floor - 4) * 8.0
        super().__init__(x, y, hp=C.BAT_HP, radius=C.BAT_RADIUS, speed=speed, coin_drop=C.BAT_COIN_DROP)
        self._t = random.uniform(0.0, 6.28)  # wobble phase
        self._contact_cd = 0.0
        self._wander_angle = random.uniform(0.0, math.pi * 2)
        self._wander_t = 0.0

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
        self._t += dt
        if self.tick_status(dt, particles):
            return

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            # Erratic wander direction shifts every 0.6 s
            self._wander_t += dt
            if self._wander_t > 0.6:
                self._wander_t = 0.0
                self._wander_angle += random.uniform(-math.pi / 2, math.pi / 2)
            # Wall-aware base direction blended 70 % toward player, 30 % wander
            vx, vy = self._steer_toward(player.x, player.y, room)
            nx = vx / (self.speed or 1.0) * 0.7 + math.cos(self._wander_angle) * 0.3
            ny = vy / (self.speed or 1.0) * 0.7 + math.sin(self._wander_angle) * 0.3
            # Arc wobble — perpendicular amplitude ~120 px/s
            wobble_amp = 120.0 / (self.speed or 1.0)
            wobble = math.sin(self._t * 4.0) * wobble_amp
            mx = nx + (-ny * wobble)
            my = ny + (nx * wobble)
            mag = math.hypot(mx, my) or 1.0
            self._move(mx / mag * self.speed * dt, my / mag * self.speed * dt, room)

        if self._contact_cd <= 0 and math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
            if player.take_damage(1):
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
        self._draw_status_rings(surf, sx, sy)


# ── Crystal Turret (floor 5+) ─────────────────────────────────────────────────


class CrystalTurret(Enemy):
    """Stationary turret — fires rotating 3-way crystal volleys.
    Immune to arrows from the front face (±60°); takes double damage from behind.
    The red dot on the body marks the vulnerable back face."""

    _DEATH_COLOR_A = C.C_TURRET
    _DEATH_COLOR_B = (200, 240, 255)

    _WIND_DUR = 0.5

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.TURRET_HP + max(0, floor - 5) * 3  # 10 / 13 / 16 …
        super().__init__(x, y, hp=hp, radius=C.TURRET_RADIUS, speed=0.0, coin_drop=C.TURRET_COIN_DROP)
        self._face_angle = random.uniform(0, math.pi * 2)
        self._shoot_cd = random.uniform(0.5, C.TURRET_SHOOT_CD)
        self._winding = False
        self._wind_up = 0.0
        self._pulse_t = random.uniform(0.0, 6.28)

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
        self._pulse_t += dt * 1.8
        self._shoot_cd -= dt
        if self.tick_status(dt, particles):
            return

        if self._shoot_cd <= self._WIND_DUR and not self._winding:
            self._winding = True
            self._wind_up = 0.0

        if self._winding:
            self._wind_up += dt
            if self._wind_up >= self._WIND_DUR:
                spread = math.radians(28)
                for off in (-spread, 0.0, spread):
                    projs.append(
                        EnemyProjectile(
                            self.x,
                            self.y,
                            self._face_angle + off,
                            speed=C.TURRET_PROJ_SPEED,
                            color=C.C_TURRET_BEAM,
                            damage=1,
                            lifetime=2.5,
                        )
                    )
                sounds.play("spore_shoot")
                self._face_angle += math.radians(15)  # rotate for next volley
                self._shoot_cd = C.TURRET_SHOOT_CD
                self._winding = False
                self._wind_up = 0.0

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
            frac = self._wind_up / self._WIND_DUR
            glow_r = r + round(frac * 18)
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
                inner.append((sx + round(math.cos(a) * (r - 5)), sy + round(math.sin(a) * (r - 5))))
            pygame.draw.polygon(surf, C.C_TURRET_DARK, inner)

        # Front-face indicator (bright spike in fire direction)
        fa = self._face_angle
        tip_x = sx + round(math.cos(fa) * (r + 7))
        tip_y = sy + round(math.sin(fa) * (r + 7))
        pygame.draw.line(surf, C.C_TURRET_BEAM, (sx, sy), (tip_x, tip_y), 3)
        pygame.draw.circle(surf, (255, 255, 255), (tip_x, tip_y), 3)

        # Back-face vulnerability marker (red dot on opposite side)
        ba = fa + math.pi
        bx_t = sx + round(math.cos(ba) * (r + 5))
        by_t = sy + round(math.sin(ba) * (r + 5))
        pygame.draw.circle(surf, (210, 55, 55), (bx_t, by_t), 4)

        # HP bar
        if self.hp < self.max_hp:
            bw = r * 2
            bx2, by2 = sx - r, sy - r - 9
            pygame.draw.rect(surf, (20, 30, 40), (bx2, by2, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, C.C_TURRET, (bx2, by2, fill, 4))
        self._draw_status_rings(surf, sx, sy)


# ── Shadow Wraith (floor 5+) ──────────────────────────────────────────────────


class ShadowWraith(Enemy):
    """Teleporting caster — blinks to a far tile every 4 s, fires homing shot pairs."""

    _DEATH_COLOR_A = C.C_WRAITH
    _DEATH_COLOR_B = (155, 80, 240)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        super().__init__(x, y, hp=C.WRAITH_HP, radius=C.WRAITH_RADIUS, speed=0.0, coin_drop=C.WRAITH_COIN_DROP)
        self._teleport_cd = random.uniform(1.0, C.WRAITH_TELEPORT_CD)
        self._shoot_cd = random.uniform(0.5, C.WRAITH_SHOOT_CD)
        self._blink_t = 0.0  # post-teleport flash timer
        self._pulse_t = random.uniform(0.0, 6.28)

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
        self._blink_t = max(0.0, self._blink_t - dt)
        self._pulse_t += dt * 2.0
        if self.tick_status(dt, particles):
            return

        # ── Teleport ──────────────────────────────────────────────────────────
        self._teleport_cd -= dt
        if self._teleport_cd <= 0:
            candidates: list[tuple[float, float]] = []
            ts = C.TILE_SIZE
            for ty in range(1, C.ROOM_TILE_H - 1):
                for tx in range(1, C.ROOM_TILE_W - 1):
                    if room.tiles[ty][tx] == C.TILE_FLOOR:
                        wx = tx * ts + ts // 2
                        wy = ty * ts + ts // 2
                        if math.hypot(wx - player.x, wy - player.y) > C.WRAITH_TELEPORT_DIST:
                            candidates.append((float(wx), float(wy)))
            if candidates:
                self.x, self.y = random.choice(candidates)
                self._blink_t = 0.38
                particles.emit_enemy_hit(self.x, self.y)
            self._teleport_cd = C.WRAITH_TELEPORT_CD

        # ── Homing shots ──────────────────────────────────────────────────────
        self._shoot_cd -= dt
        if self._shoot_cd <= 0:
            dx = player.x - self.x
            dy = player.y - self.y
            base_a = math.atan2(dy, dx)
            for off in (-math.radians(30), math.radians(30)):
                ep = EnemyProjectile(
                    self.x,
                    self.y,
                    base_a + off,
                    speed=175,
                    color=C.C_WRAITH_SHOT,
                    damage=1,
                    lifetime=4.5,
                )
                ep.homing = True  # game.py will steer this each frame
                projs.append(ep)
            self._shoot_cd = C.WRAITH_SHOOT_CD

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius
        pulse = (math.sin(self._pulse_t) + 1.0) * 0.5

        # Post-teleport blink halo
        if self._blink_t > 0:
            a = int(self._blink_t / 0.38 * 200)
            ring_r = r + 10
            blink = pygame.Surface((ring_r * 2, ring_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(blink, (180, 100, 255, a), (ring_r, ring_r), ring_r)
            surf.blit(blink, (sx - ring_r, sy - ring_r))

        # Pulsing outer ring
        ring_r = r + 3 + round(pulse * 4)
        pygame.draw.circle(surf, C.C_WRAITH_DARK, (sx, sy), ring_r, 2)

        # Shadow + body
        pygame.draw.circle(surf, (8, 8, 8), (sx + 1, sy + 3), r - 1)
        color = (255, 255, 255) if self._flash > 0 else C.C_WRAITH
        pygame.draw.circle(surf, color, (sx, sy), r)
        if self._flash <= 0:
            pygame.draw.circle(surf, C.C_WRAITH_DARK, (sx, sy + r // 3), r // 2)
            # Glowing eyes
            for ex in (-4, 4):
                pygame.draw.circle(surf, (160, 60, 255), (sx + ex, sy - 3), 3)
                pygame.draw.circle(surf, (225, 185, 255), (sx + ex, sy - 3), 1)
            # Ghost wisps dangling below the body
            for i, ox in enumerate((-5, 0, 5)):
                for j in range(1, 5):
                    wy = sy + r - 2 + j * 3
                    wx = sx + ox + round(math.sin(self._pulse_t * 1.4 + i * 1.3 + j * 0.6) * 2)
                    wisp_size = max(1, 3 - j)
                    wisp_alpha = int(100 - j * 20)
                    wisp_col = (max(0, 55 - j * 10), max(0, 25 - j * 5), max(0, 95 - j * 18))
                    pygame.draw.circle(surf, wisp_col, (wx, wy), wisp_size)

        # HP bar
        if self.hp < self.max_hp:
            bw = r * 2
            bx2, by2 = sx - r, sy - r - 7
            pygame.draw.rect(surf, (20, 5, 40), (bx2, by2, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, C.C_WRAITH_SHOT, (bx2, by2, fill, 4))
        self._draw_status_rings(surf, sx, sy)


# ── Bone Archer (floor 6+) ────────────────────────────────────────────────────


class BoneArcher(Enemy):
    """Ranged skeleton — fires a 3-way spread; every 4th shot is a slow heavy spike."""

    _DEATH_COLOR_A = C.C_BONE
    _DEATH_COLOR_B = (240, 225, 200)

    _WIND_DUR = 0.4
    _PREF_DIST = 240.0

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.BONE_ARCHER_HP + max(0, floor - 6) * 2
        super().__init__(
            x, y, hp=hp, radius=C.BONE_ARCHER_RADIUS, speed=C.BONE_ARCHER_SPEED, coin_drop=C.BONE_ARCHER_COIN_DROP
        )
        self._shoot_cd = random.uniform(0.5, C.BONE_ARCHER_SHOOT_CD)
        self._shot_count = 0
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
        if self.tick_status(dt, particles):
            return

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        # Maintain preferred range
        if dist < self._PREF_DIST * 0.7 and dist > 0:
            self._move(-dx / dist * self.speed * dt, -dy / dist * self.speed * dt, room)
        elif dist > self._PREF_DIST * 1.3 and dist > 0:
            self._move(dx / dist * self.speed * 0.6 * dt, dy / dist * self.speed * 0.6 * dt, room)

        self._shoot_cd -= dt
        if self._shoot_cd <= self._WIND_DUR and not self._winding:
            self._winding = True
            self._wind_up = 0.0

        if self._winding:
            self._wind_up += dt
            if self._wind_up >= self._WIND_DUR:
                self._shot_count += 1
                base_a = math.atan2(dy, dx)
                if self._shot_count % 4 == 0:
                    # Heavy bone spike — single slow projectile, 2 damage
                    projs.append(
                        EnemyProjectile(
                            self.x,
                            self.y,
                            base_a,
                            speed=140,
                            color=C.C_BONE_SPIKE,
                            damage=2,
                            lifetime=3.5,
                        )
                    )
                else:
                    # Standard 3-way spread
                    spread = math.radians(20)
                    for off in (-spread, 0.0, spread):
                        projs.append(
                            EnemyProjectile(
                                self.x,
                                self.y,
                                base_a + off,
                                speed=195,
                                color=C.C_BONE,
                                damage=1,
                                lifetime=2.2,
                            )
                        )
                sounds.play("spore_shoot")
                self._shoot_cd = C.BONE_ARCHER_SHOOT_CD
                self._winding = False
                self._wind_up = 0.0

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        if self._winding:
            sx0, sy0 = camera.apply_pos(self.x, self.y)
            frac = min(1.0, self._wind_up / self._WIND_DUR)
            pulse = min(255, int(frac * 255))
            is_spike = (self._shot_count + 1) % 4 == 0
            col = (255, 255, 255) if not is_spike else (255, 230, 180)
            pygame.draw.circle(
                surf,
                (pulse, int(pulse * col[1] / 255), int(pulse * col[2] / 255)),
                (round(sx0), round(sy0)),
                self.radius + 7,
                2,
            )

        sx, sy = self._draw_body(surf, camera, C.C_BONE, C.C_BONE_DARK)
        if self._flash <= 0:
            # Dark hollow eye sockets
            for ex in (-4, 4):
                pygame.draw.circle(surf, (10, 10, 10), (sx + ex, sy - 3), 3)
                pygame.draw.circle(surf, (200, 185, 155), (sx + ex, sy - 3), 1)
            # Cheekbone cracks
            pygame.draw.line(surf, C.C_BONE_DARK, (sx - 8, sy + 1), (sx - 4, sy + 5), 1)
            pygame.draw.line(surf, C.C_BONE_DARK, (sx + 4, sy + 5), (sx + 8, sy + 1), 1)
            # Teeth (small bars across the lower face)
            for tx in (-4, -1, 2, 5):
                pygame.draw.rect(surf, (228, 215, 195), (sx + tx, sy + 4, 2, 4))


# ── Magma Slug (floor 6+) ─────────────────────────────────────────────────────


class MagmaSlug(Enemy):
    """Slow armoured melee chaser — leaves a trail of burn patches every 0.5 s.
    game.py drains `_patch_queue` each frame and creates BurnPatch objects."""

    _DEATH_COLOR_A = C.C_SLUG
    _DEATH_COLOR_B = (240, 130, 40)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        hp = C.SLUG_HP + max(0, floor - 6) * 3
        super().__init__(x, y, hp=hp, radius=C.SLUG_RADIUS, speed=C.SLUG_SPEED, coin_drop=C.SLUG_COIN_DROP)
        self._contact_cd = 0.0
        self._drop_cd = C.SLUG_DROP_CD
        self._patch_queue: list[tuple[float, float]] = []  # drained by game.py
        self._pulse_t = random.uniform(0.0, 6.28)

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
        self._pulse_t += dt * 2.5
        if self.tick_status(dt, particles):
            return

        if math.hypot(player.x - self.x, player.y - self.y) > 0:
            vx, vy = self._steer_toward(player.x, player.y, room)
            self._move(vx * dt, vy * dt, room)

        if self._contact_cd <= 0 and math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
            if player.take_damage(C.SLUG_DAMAGE):
                particles.emit_player_hurt(player.x, player.y)
            self._contact_cd = 0.6

        # Queue a burn patch at current position
        self._drop_cd = max(0.0, self._drop_cd - dt)
        if self._drop_cd <= 0:
            self._patch_queue.append((self.x, self.y))
            self._drop_cd = C.SLUG_DROP_CD

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius
        pulse = (math.sin(self._pulse_t) + 1.0) * 0.5

        # Lava glow halo
        gr = r + 4 + round(pulse * 4)
        gc = (min(255, 185 + round(pulse * 40)), min(255, 65 + round(pulse * 35)), 12)
        pygame.draw.circle(surf, gc, (sx, sy), gr, 3)

        # Antennae (drawn before body so body overlaps base)
        if self._flash <= 0:
            ant_tip_col = (min(255, 240 + round(pulse * 15)), min(255, 100 + round(pulse * 55)), 10)
            for ax, tilt in ((-5, -3), (5, 3)):
                # Stalk
                pygame.draw.line(surf, C.C_SLUG_DARK,
                                 (sx + ax, sy - r + 3),
                                 (sx + ax + tilt, sy - r - 7), 2)
                # Glowing tip ball
                pygame.draw.circle(surf, ant_tip_col, (sx + ax + tilt, sy - r - 7), 3)
                pygame.draw.circle(surf, C.C_SLUG_DARK, (sx + ax + tilt, sy - r - 7), 3, 1)

        # Shadow + body
        pygame.draw.circle(surf, (8, 8, 8), (sx + 3, sy + 5), r - 2)
        color = (255, 255, 255) if self._flash > 0 else C.C_SLUG
        pygame.draw.circle(surf, color, (sx, sy), r)
        if self._flash <= 0:
            pygame.draw.circle(surf, C.C_SLUG_DARK, (sx, sy + r // 3), r // 2)
            # Animated lava cracks
            for i in range(3):
                a = math.radians(55 + i * 90 + self._pulse_t * 8)
                lx = sx + round(math.cos(a) * r * 0.6)
                ly = sy + round(math.sin(a) * r * 0.6)
                cc = (min(255, 230 + round(pulse * 25)), min(255, 85 + round(pulse * 40)), 8)
                pygame.draw.line(surf, cc, (sx, sy), (lx, ly), 1)

        # HP bar
        if self.hp < self.max_hp:
            bw = r * 2
            bx2, by2 = sx - r, sy - r - 8
            pygame.draw.rect(surf, (40, 10, 0), (bx2, by2, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, C.C_SLUG, (bx2, by2, fill, 4))
        self._draw_status_rings(surf, sx, sy)


# ── Void Shrieker (floor 7) ───────────────────────────────────────────────────


class VoidShrieker(Enemy):
    """Fast erratic screamer — explodes into a 8-way ring of projectiles on death.
    Signals game.py via `_hit_shake = True` whenever it deals contact damage."""

    _DEATH_COLOR_A = C.C_SHRIEKER
    _DEATH_COLOR_B = (165, 55, 255)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        super().__init__(
            x, y, hp=C.SHRIEKER_HP, radius=C.SHRIEKER_RADIUS, speed=C.SHRIEKER_SPEED, coin_drop=C.SHRIEKER_COIN_DROP
        )
        self._t = random.uniform(0.0, 6.28)
        self._contact_cd = 0.0
        self._hit_shake = False  # game.py reads and clears this
        self._death_projs: list[EnemyProjectile] = []
        self._wander_angle = random.uniform(0.0, math.pi * 2)
        self._wander_t = 0.0

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        super().take_hit(damage, particles)
        if not self.alive:
            # Death burst: 8 EnemyProjectiles in a full ring
            for i in range(8):
                a = math.radians(i * 45.0)
                self._death_projs.append(
                    EnemyProjectile(
                        self.x,
                        self.y,
                        a,
                        speed=195,
                        color=C.C_VOID_SHOT,
                        damage=1,
                        lifetime=2.2,
                    )
                )

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
        self._t += dt
        if self.tick_status(dt, particles):
            return

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            # Erratic wander direction shifts every 0.6 s
            self._wander_t += dt
            if self._wander_t > 0.6:
                self._wander_t = 0.0
                self._wander_angle += random.uniform(-math.pi / 2, math.pi / 2)
            # Wall-aware base direction blended 70 % toward player, 30 % wander
            vx, vy = self._steer_toward(player.x, player.y, room)
            nx = vx / (self.speed or 1.0) * 0.7 + math.cos(self._wander_angle) * 0.3
            ny = vy / (self.speed or 1.0) * 0.7 + math.sin(self._wander_angle) * 0.3
            wobble = math.sin(self._t * 5.5) * 0.55
            mx = nx + (-ny * wobble)
            my = ny + (nx * wobble)
            mag = math.hypot(mx, my) or 1.0
            self._move(mx / mag * self.speed * dt, my / mag * self.speed * dt, room)

        if self._contact_cd <= 0 and math.hypot(player.x - self.x, player.y - self.y) < self.radius + player.radius:
            if player.take_damage(1):
                particles.emit_player_hurt(player.x, player.y)
                self._hit_shake = True  # game.py reads this to shake camera
            self._contact_cd = 0.4

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius

        # Void ripple ring (animated)
        ripple_r = r + 4 + round(abs(math.sin(self._t * 6.0)) * 5)
        pygame.draw.circle(surf, C.C_SHRIEKER, (sx, sy), ripple_r, 1)

        # Shadow + body
        pygame.draw.circle(surf, (8, 8, 8), (sx + 1, sy + 2), r - 1)
        color = (255, 255, 255) if self._flash > 0 else C.C_SHRIEKER
        pygame.draw.circle(surf, color, (sx, sy), r)
        if self._flash <= 0:
            pygame.draw.circle(surf, C.C_SHRIEKER_DARK, (sx, sy + r // 3), r // 2)
            # Void eyes (bright pulsing purple)
            eye_glow = int(140 + abs(math.sin(self._t * 4.0)) * 80)
            for ex in (-4, 4):
                pygame.draw.circle(surf, (eye_glow, 30, 230), (sx + ex, sy - 4), 3)
                pygame.draw.circle(surf, (230, 200, 255), (sx + ex, sy - 4), 1)
            # Large screaming void mouth
            pygame.draw.ellipse(surf, (8, 0, 18), (sx - 5, sy + 1, 10, 7))
            # Inner void depth
            pygame.draw.ellipse(surf, (0, 0, 5), (sx - 3, sy + 2, 6, 5))

        # HP bar
        if self.hp < self.max_hp:
            bw = r * 2
            bx2, by2 = sx - r, sy - r - 6
            pygame.draw.rect(surf, (20, 5, 35), (bx2, by2, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, C.C_SHRIEKER, (bx2, by2, fill, 4))
        self._draw_status_rings(surf, sx, sy)


# ── Spore Elder (floor 5+ elite) ─────────────────────────────────────────────


class SporeElder(SporePlant):
    """Elite SporePlant — simultaneous 8-way volleys + periodic random spore clouds."""

    _DEATH_COLOR_A = (100, 210, 70)
    _DEATH_COLOR_B = (60, 155, 45)
    _NUM_SPOKES = 8

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        super().__init__(x, y, floor=floor)
        # Override HP and coin drop
        self.hp = 18 + max(0, floor - 5) * 3
        self.max_hp = self.hp
        self.coin_drop = 2
        self._cloud_cd: float = random.uniform(4.0, 7.0)

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
        self._cloud_cd -= dt
        if self.tick_status(dt, particles):
            return

        # Random spore cloud every 7 s
        if self._cloud_cd <= 0:
            for _ in range(6):
                a = random.uniform(0.0, math.pi * 2)
                projs.append(
                    EnemyProjectile(
                        self.x, self.y, a,
                        speed=80, color=(120, 215, 90),
                        damage=C.SPORE_DAMAGE, lifetime=5.0,
                    )
                )
            self._cloud_cd = 7.0

        # Wind-up then fire 8-way (both 0° and 45° simultaneously)
        if self._shoot_cd <= self._WIND_DUR and not self._winding:
            self._winding = True
            self._wind_up = 0.0

        if self._winding:
            self._wind_up += dt
            if self._wind_up >= self._WIND_DUR:
                for rot in (0.0, 45.0):
                    for i in range(4):
                        angle = math.radians(rot + i * 90.0)
                        projs.append(
                            EnemyProjectile(
                                self.x, self.y, angle,
                                speed=C.SPORE_SPEED, color=(120, 215, 90),
                                damage=C.SPORE_DAMAGE, lifetime=C.SPORE_LIFETIME,
                            )
                        )
                sounds.play("spore_shoot")
                self._shoot_cd = C.SPLANT_SHOOT_CD
                self._winding = False
                self._wind_up = 0.0

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        """Distinguished from SporePlant: larger outer ring, crown thorns, brighter palette."""
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)

        # Slower, brighter pulse
        pulse = (math.sin(self._pulse_t * 0.9) + 1.0) * 0.5

        # Outer aura ring (extra wide)
        aura_r = self.radius + 8 + round(pulse * 7)
        aura_g = int(130 + pulse * 100)
        pygame.draw.circle(surf, (30, aura_g, 30), (sx, sy), aura_r, 2)

        # Secondary inner ring
        inner_ring_r = self.radius + 3 + round(pulse * 3)
        pygame.draw.circle(surf, (60, 200, 55), (sx, sy), inner_ring_r, 1)

        # Wind-up glow
        if self._winding:
            frac = self._wind_up / self._WIND_DUR
            glow_r = self.radius + round(frac * 16)
            glow_c = (min(255, 40 + round(frac * 80)), min(255, 200 + round(frac * 55)), 50)
            pygame.draw.circle(surf, glow_c, (sx, sy), glow_r, 3)

        # 8 crown-like spines (alternating long/short)
        for i in range(self._NUM_SPOKES):
            angle = math.radians(self._rotation + i * (360 / self._NUM_SPOKES))
            length = self.radius + (13 if i % 2 == 0 else 8)
            ex = sx + round(math.cos(angle) * length)
            ey = sy + round(math.sin(angle) * length)
            col = (55, 185, 48) if i % 2 == 0 else (38, 145, 32)
            pygame.draw.line(surf, col, (sx, sy), (ex, ey), 2)
            # Thorn tip for long spines
            if i % 2 == 0:
                pygame.draw.circle(surf, (80, 215, 60), (ex, ey), 2)

        # Shadow + body (brighter green than regular SporePlant)
        pygame.draw.circle(surf, (8, 8, 8), (sx + 2, sy + 4), self.radius - 2)
        body_col = (255, 255, 255) if self._flash > 0 else (65, 155, 48)
        pygame.draw.circle(surf, body_col, (sx, sy), self.radius)
        if self._flash <= 0:
            pygame.draw.circle(surf, (40, 105, 30), (sx, sy + self.radius // 3), self.radius // 2)

        # Glowing centre pip (brighter than SporePlant)
        pip_col = (min(255, 80 + round(pulse * 80)), min(255, 200 + round(pulse * 55)), 40)
        pygame.draw.circle(surf, pip_col, (sx, sy), 5)
        pygame.draw.circle(surf, (35, 80, 25), (sx, sy), 5, 1)

        # HP bar (green tint)
        if self.hp < self.max_hp:
            bw = self.radius * 2
            bx, by = sx - self.radius, sy - self.radius - 10
            pygame.draw.rect(surf, (20, 0, 0), (bx, by, bw, 4))
            fill = round(bw * self.hp / self.max_hp)
            pygame.draw.rect(surf, (80, 220, 60), (bx, by, fill, 4))
        self._draw_status_rings(surf, sx, sy)


# ── Iron Warden (floor 4 boss) ────────────────────────────────────────────────


class IronWarden(Enemy):
    """Floor-4 boss — armoured knight: stomp AoE, shrapnel burst, P2 charge dash."""

    is_boss_enemy = True
    boss_name = "Iron Warden"
    _phase2_shake = 14

    _DEATH_COLOR_A = C.C_WARDEN
    _DEATH_COLOR_B = (220, 185, 80)

    def __init__(self, x: float, y: float) -> None:
        super().__init__(
            x, y, hp=C.WARDEN_HP, radius=C.WARDEN_RADIUS,
            speed=C.WARDEN_SPEED, coin_drop=C.WARDEN_COIN_DROP,
        )
        self._summon_queue: list[Enemy] = []

        # Stomp
        self._stomp_cd: float = C.WARDEN_STOMP_CD
        self._stomp_winding: bool = False
        self._stomp_wind_up: float = 0.0
        self._stomp_target: tuple[float, float] | None = None
        self._stomp_ring_t: float = 0.0   # brief impact ring

        # Shrapnel
        self._shrapnel_cd: float = C.WARDEN_SHRAPNEL_CD
        self._shrapnel_winding: bool = False
        self._shrapnel_wind_up: float = 0.0

        # Charge (P2 only)
        self._charge_cd: float = C.WARDEN_CHARGE_CD
        self._charge_telegraph_t: float = 0.0  # counts DOWN from 1.5
        self._charge_dir: tuple[float, float] = (1.0, 0.0)
        self._charging: bool = False
        self._charge_timer: float = 0.0

        # Contact damage
        self._contact_cd: float = 0.0

        # Visual
        self._bob_t: float = random.uniform(0.0, 6.28)

    @property
    def _phase2(self) -> bool:
        return self.hp <= self.max_hp // 2

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        was_p2 = self._phase2
        super().take_hit(damage, particles)
        if not was_p2 and self._phase2 and self.alive:
            self.phase2_just_triggered = True
            particles.emit_warden_phase2(self.x, self.y)
        if not self.alive:
            particles.emit_warden_death(self.x, self.y)

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
        self._contact_cd = max(0.0, self._contact_cd - dt)
        if self.tick_status(dt, particles):
            return

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        # ── Charge (P2 only) ─────────────────────────────────────────────────
        if self._phase2:
            if not self._charging and self._charge_telegraph_t <= 0:
                self._charge_cd -= dt
            if self._charge_cd <= 0 and not self._charging and not self._stomp_winding and not self._shrapnel_winding:
                # Begin telegraph
                self._charge_cd = C.WARDEN_CHARGE_CD
                self._charge_telegraph_t = 1.5
                if dist > 0:
                    self._charge_dir = (dx / dist, dy / dist)

            if self._charge_telegraph_t > 0 and not self._charging:
                self._charge_telegraph_t -= dt
                if self._charge_telegraph_t <= 0:
                    self._charging = True
                    self._charge_timer = 0.25

            if self._charging:
                self._charge_timer -= dt
                self._move(self._charge_dir[0] * 400.0 * dt, self._charge_dir[1] * 400.0 * dt, room)
                if self._charge_timer <= 0:
                    self._charging = False

        # ── Stomp ─────────────────────────────────────────────────────────────
        stomp_cd = 2.0 if self._phase2 else C.WARDEN_STOMP_CD
        _STOMP_WIND = 1.0
        if not self._charging:
            self._stomp_cd -= dt

        if self._stomp_cd <= _STOMP_WIND and not self._stomp_winding and not self._charging:
            self._stomp_winding = True
            self._stomp_wind_up = 0.0
            self._stomp_target = (player.x, player.y)

        if self._stomp_winding:
            self._stomp_wind_up += dt
            if self._stomp_wind_up >= _STOMP_WIND:
                # Resolve: damage if player near target
                self._stomp_ring_t = 0.35
                if self._stomp_target:
                    tx, ty = self._stomp_target
                    if math.hypot(player.x - tx, player.y - ty) < 60 and player.take_damage(1):
                        particles.emit_player_hurt(player.x, player.y)
                sounds.play("wolf_lunge")
                self._stomp_cd = stomp_cd
                self._stomp_winding = False
                self._stomp_wind_up = 0.0

        self._stomp_ring_t = max(0.0, self._stomp_ring_t - dt)

        # ── Shrapnel ─────────────────────────────────────────────────────────
        _SHRAP_WIND = 0.5
        if not self._charging:
            self._shrapnel_cd -= dt

        if self._shrapnel_cd <= _SHRAP_WIND and not self._shrapnel_winding and not self._charging:
            self._shrapnel_winding = True
            self._shrapnel_wind_up = 0.0

        if self._shrapnel_winding:
            self._shrapnel_wind_up += dt
            if self._shrapnel_wind_up >= _SHRAP_WIND:
                if self._phase2:
                    # 8-way ring
                    for i in range(8):
                        a = math.radians(i * 45.0)
                        projs.append(EnemyProjectile(
                            self.x, self.y, a,
                            speed=260, color=C.C_WARDEN_SPARK, damage=1, lifetime=2.0,
                        ))
                else:
                    # 4-way semicone toward player
                    base_a = math.atan2(dy, dx)
                    spread = math.radians(30)
                    step = spread * 2 / 3
                    for i in range(4):
                        a = base_a - spread + i * step
                        projs.append(EnemyProjectile(
                            self.x, self.y, a,
                            speed=260, color=C.C_WARDEN_SPARK, damage=1, lifetime=2.0,
                        ))
                sounds.play("spore_shoot")
                self._shrapnel_cd = C.WARDEN_SHRAPNEL_CD
                self._shrapnel_winding = False
                self._shrapnel_wind_up = 0.0

        # ── Patrol toward player ──────────────────────────────────────────────
        if not self._charging and not self._stomp_winding and dist > 0:
            self._move(dx / dist * self.speed * dt, dy / dist * self.speed * dt, room)

        # ── Contact damage ────────────────────────────────────────────────────
        if self._contact_cd <= 0 and dist < self.radius + player.radius:
            if player.take_damage(1):
                particles.emit_player_hurt(player.x, player.y)
            self._contact_cd = 0.8

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius

        # Stomp telegraph ring (expands during wind-up to show the danger zone)
        if self._stomp_winding and self._stomp_target:
            tx2, ty2 = self._stomp_target
            stx, sty = camera.apply_pos(tx2, ty2)
            frac = self._stomp_wind_up / 1.0
            ring_r = 10 + round(frac * 50)
            pygame.draw.circle(surf, (220, 185, 80), (round(stx), round(sty)), ring_r, 3)

        # Stomp impact ring (brief flash)
        if self._stomp_ring_t > 0 and self._stomp_target:
            tx2, ty2 = self._stomp_target
            stx, sty = camera.apply_pos(tx2, ty2)
            frac = 1.0 - self._stomp_ring_t / 0.35
            ring_r = 10 + round(frac * 55)
            alpha = int((1.0 - frac) * 200)
            ring_surf = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (220, 185, 80, alpha),
                               (ring_r + 2, ring_r + 2), ring_r, 3)
            surf.blit(ring_surf, (round(stx) - ring_r - 2, round(sty) - ring_r - 2))

        # Charge telegraph arrow
        if self._charge_telegraph_t > 0 and not self._charging:
            progress = 1.0 - self._charge_telegraph_t / 1.5
            arrow_len = 40 + round(progress * 60)
            ex2 = sx + round(self._charge_dir[0] * arrow_len)
            ey2 = sy + round(self._charge_dir[1] * arrow_len)
            pygame.draw.line(surf, (255, 80, 30), (sx, sy), (ex2, ey2), 4)
            pygame.draw.circle(surf, (255, 80, 30), (ex2, ey2), 6)

        # Phase-2 aura
        if self._phase2:
            pulse = (math.sin(self._bob_t * 4.0) + 1) * 0.5
            pygame.draw.circle(surf, C.C_WARDEN_SPARK, (sx, sy), r + 6 + round(pulse * 5), 2)

        # Shrapnel wind-up glow
        if self._shrapnel_winding:
            frac2 = self._shrapnel_wind_up / 0.5
            pygame.draw.circle(surf, C.C_WARDEN_SPARK, (sx, sy), r + round(frac2 * 12), 2)

        # Body
        body_sx, body_sy = self._draw_body(surf, camera, C.C_WARDEN, C.C_WARDEN_DARK)

        # Armour bolt details
        if self._flash <= 0:
            for ox2, oy2 in ((-7, -7), (7, -7), (-7, 7), (7, 7)):
                pygame.draw.circle(surf, C.C_WARDEN_SPARK, (body_sx + ox2, body_sy + oy2), 3)
            pygame.draw.circle(surf, C.C_WARDEN_DARK, (body_sx, body_sy), r // 2, 2)


# ── Abyssal Leech (floor 5 boss) ─────────────────────────────────────────────


class AbyssalLeech(Enemy):
    """Floor-5 boss — stationary caster (P1), slow mover (P2);
    fires homing tendrils that heal it on player contact + 6-way void burst."""

    is_boss_enemy = True
    boss_name = "Abyssal Leech"
    _phase2_shake = 14

    _DEATH_COLOR_A = C.C_LEECH
    _DEATH_COLOR_B = (40, 185, 210)

    def __init__(self, x: float, y: float) -> None:
        super().__init__(
            x, y, hp=C.LEECH_HP, radius=C.LEECH_RADIUS,
            speed=0.0, coin_drop=C.LEECH_COIN_DROP,
        )
        self._summon_queue: list[Enemy] = []

        self._tendril_cd: float = C.LEECH_TENDRIL_CD
        self._burst_cd: float = C.LEECH_BURST_CD

        self._bob_t: float = random.uniform(0.0, 6.28)

    @property
    def _phase2(self) -> bool:
        return self.hp <= self.max_hp // 2

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        was_p2 = self._phase2
        super().take_hit(damage, particles)
        if not was_p2 and self._phase2 and self.alive:
            self.phase2_just_triggered = True
            self.speed = C.LEECH_SPEED_P2   # begin moving in P2
            particles.emit_leech_phase2(self.x, self.y)
        if not self.alive:
            particles.emit_leech_death(self.x, self.y)

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
        if self.tick_status(dt, particles):
            return

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        # Phase 2: slow movement toward player
        if self._phase2 and dist > self.radius + 5 and dist > 0:
            self._move(dx / dist * C.LEECH_SPEED_P2 * dt, dy / dist * C.LEECH_SPEED_P2 * dt, room)

        # ── Leeching Tendrils ─────────────────────────────────────────────────
        self._tendril_cd -= dt
        if self._tendril_cd <= 0:
            count = 6 if self._phase2 else 3
            base_a = math.atan2(dy, dx) if dist > 0 else 0.0
            half = (count - 1) / 2.0
            for i in range(count):
                a = base_a + (i - half) * math.radians(30)
                ep = EnemyProjectile(
                    self.x, self.y, a,
                    speed=165, color=C.C_LEECH_SHOT, damage=1, lifetime=4.0,
                )
                ep.homing = True      # game.py steers toward player each frame
                ep.leech_owner = self  # game.py heals self when this hits
                projs.append(ep)
            sounds.play("spore_shoot")
            self._tendril_cd = C.LEECH_TENDRIL_CD

        # ── Void Burst ────────────────────────────────────────────────────────
        burst_cd = 2.5 if self._phase2 else C.LEECH_BURST_CD
        self._burst_cd -= dt
        if self._burst_cd <= 0:
            base_a2 = math.atan2(dy, dx) if dist > 0 else 0.0
            for i in range(6):
                a = base_a2 + math.radians(i * 60)
                projs.append(EnemyProjectile(
                    self.x, self.y, a,
                    speed=200, color=C.C_LEECH_SHOT, damage=1, lifetime=2.5,
                ))
            sounds.play("spore_shoot")
            self._burst_cd = burst_cd

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius
        pulse = (math.sin(self._bob_t * 2.5) + 1.0) * 0.5

        # Outer pulsing ring
        ring_r = r + 4 + round(pulse * 6)
        pygame.draw.circle(surf, C.C_LEECH_SHOT, (sx, sy), ring_r, 2)

        # Phase-2 second ring
        if self._phase2:
            ring_r2 = r + 10 + round(pulse * 9)
            pygame.draw.circle(surf, C.C_LEECH, (sx, sy), ring_r2, 1)

        # Body
        body_sx, body_sy = self._draw_body(surf, camera, C.C_LEECH, C.C_LEECH_DARK)

        # Maw / mouth detail
        if self._flash <= 0:
            pygame.draw.ellipse(surf, C.C_LEECH_SHOT,
                                (body_sx - 10, body_sy - 5, 20, 12))
            pygame.draw.ellipse(surf, C.C_LEECH_DARK,
                                (body_sx - 7, body_sy - 3, 14, 8))
            # Teeth
            for tooth_x in (-5, 0, 5):
                pygame.draw.line(surf, C.C_LEECH_SHOT,
                                 (body_sx + tooth_x, body_sy - 3),
                                 (body_sx + tooth_x, body_sy + 2), 2)


# ── Fungal Matriarch (floor 6 boss) ──────────────────────────────────────────


class FungalMatriarch(Enemy):
    """Floor-6 boss — stationary spore caster; summons Spore Elders;
    passive spore cloud damages player within 80 px."""

    is_boss_enemy = True
    boss_name = "Fungal Matriarch"
    _phase2_shake = 14
    _spore_cloud_passive = True   # game.py reads this to apply aura DoT

    _DEATH_COLOR_A = C.C_MATRIARCH
    _DEATH_COLOR_B = (155, 210, 85)

    def __init__(self, x: float, y: float, *, floor: int = 1) -> None:
        super().__init__(
            x, y, hp=C.MATRIARCH_HP, radius=C.MATRIARCH_RADIUS,
            speed=0.0, coin_drop=C.MATRIARCH_COIN_DROP,
        )
        self.floor = floor
        self._summon_queue: list[Enemy] = []

        self._spore_cd: float = C.MATRIARCH_SPORE_CD
        self._spore_winding: bool = False
        self._spore_wind_up: float = 0.0

        self._summon_cd: float = C.MATRIARCH_SUMMON_CD
        self._summon_counter: int = 0   # alternates SporeElder / VenomfangBat in P2

        self._pulse_t: float = random.uniform(0.0, 6.28)

    @property
    def _phase2(self) -> bool:
        return self.hp <= self.max_hp // 2

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        was_p2 = self._phase2
        super().take_hit(damage, particles)
        if not was_p2 and self._phase2 and self.alive:
            self.phase2_just_triggered = True
            particles.emit_matriarch_phase2(self.x, self.y)
        if not self.alive:
            particles.emit_matriarch_death(self.x, self.y)

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
        self._pulse_t += dt * 1.8
        if self.tick_status(dt, particles):
            return

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        # ── Spore Volley (5-way fan) ──────────────────────────────────────────
        spore_cd = 1.5 if self._phase2 else C.MATRIARCH_SPORE_CD
        _WIND_DUR = 0.65
        self._spore_cd -= dt

        if self._spore_cd <= _WIND_DUR and not self._spore_winding:
            self._spore_winding = True
            self._spore_wind_up = 0.0

        if self._spore_winding:
            self._spore_wind_up += dt
            if self._spore_wind_up >= _WIND_DUR:
                base_a = math.atan2(dy, dx) if dist > 0 else 0.0
                for i in range(5):
                    a = base_a + math.radians(-32 + i * 16)
                    projs.append(EnemyProjectile(
                        self.x, self.y, a,
                        speed=C.SPORE_SPEED, color=C.C_MATRIARCH_SPORE,
                        damage=1, lifetime=C.SPORE_LIFETIME + 0.5,
                    ))
                sounds.play("spore_shoot")
                self._spore_cd = spore_cd
                self._spore_winding = False
                self._spore_wind_up = 0.0

        # ── Summon ────────────────────────────────────────────────────────────
        summon_cd = 6.0 if self._phase2 else C.MATRIARCH_SUMMON_CD
        self._summon_cd -= dt
        if self._summon_cd <= 0:
            positions = room.get_spawn_positions(1, min_dist_from_centre=160.0)
            if positions:
                pos = positions[0]
                if self._phase2:
                    if self._summon_counter % 2 == 0:
                        self._summon_queue.append(SporeElder(*pos, floor=self.floor))
                    else:
                        self._summon_queue.append(VenomfangBat(*pos, floor=self.floor))
                    self._summon_counter += 1
                else:
                    self._summon_queue.append(SporeElder(*pos, floor=self.floor))
            particles.emit_summon_flash(self.x, self.y)
            self._summon_cd = summon_cd

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius
        pulse = (math.sin(self._pulse_t) + 1.0) * 0.5

        # Spore aura pulsing ring
        ring_r = r + 5 + round(pulse * 8)
        ring_col = (int(80 + pulse * 55), int(145 + pulse * 60), 45)
        pygame.draw.circle(surf, ring_col, (sx, sy), ring_r, 2)

        # Phase-2 extra ring
        if self._phase2:
            ring_r2 = r + 14 + round(pulse * 10)
            pygame.draw.circle(surf, C.C_MATRIARCH_SPORE, (sx, sy), ring_r2, 1)

        # Wind-up glow
        if self._spore_winding:
            frac = self._spore_wind_up / 0.65
            glow_r = r + round(frac * 18)
            pygame.draw.circle(surf, C.C_MATRIARCH_SPORE, (sx, sy), glow_r, 3)

        # Spines radiating out
        for i in range(10):
            angle = math.radians(i * 36.0 + self._pulse_t * 10)
            ex = sx + round(math.cos(angle) * (r + 12))
            ey = sy + round(math.sin(angle) * (r + 12))
            pygame.draw.line(surf, C.C_MATRIARCH, (sx, sy), (ex, ey), 2)

        # Body
        body_sx, body_sy = self._draw_body(surf, camera, C.C_MATRIARCH, C.C_MATRIARCH_DARK)

        # Centre mushroom cap detail
        if self._flash <= 0:
            pygame.draw.circle(surf, C.C_MATRIARCH_SPORE, (body_sx, body_sy - 4), r // 3)
            pygame.draw.circle(surf, C.C_MATRIARCH_DARK, (body_sx, body_sy - 4), r // 3, 2)


# ── Void Sovereign (floor 7 boss) ────────────────────────────────────────────


class VoidSovereign(Enemy):
    """Floor-7 boss — hunter of the void: burst attacks, summons shriekers,
    P2 activates a shrinking void field that crushes the player's arena."""

    is_boss_enemy = True
    boss_name = "Void Sovereign"
    _phase2_shake = 18
    is_void_sovereign = True   # game.py reads this to apply void-field clamp + draw

    _DEATH_COLOR_A = (80, 20, 160)
    _DEATH_COLOR_B = (130, 55, 255)

    def __init__(self, x: float, y: float) -> None:
        super().__init__(
            x, y, hp=C.SOVEREIGN_HP, radius=C.SOVEREIGN_RADIUS,
            speed=C.SOVEREIGN_SPEED, coin_drop=C.SOVEREIGN_COIN_DROP,
        )
        self._summon_queue: list[Enemy] = []

        self._burst_cd: float = C.SOVEREIGN_BURST_CD
        self._burst_winding: bool = False
        self._burst_wind_up: float = 0.0

        self._summon_cd: float = C.SOVEREIGN_SUMMON_CD

        # Void field (P2): margin grows from 0 up to SOVEREIGN_VOID_MAX
        self._void_margin: float = 0.0

        self._bob_t: float = random.uniform(0.0, 6.28)
        self._contact_cd: float = 0.0

    @property
    def _phase2(self) -> bool:
        return self.hp <= self.max_hp // 2

    def take_hit(self, damage: int, particles: ParticleSystem) -> None:
        was_p2 = self._phase2
        super().take_hit(damage, particles)
        if not was_p2 and self._phase2 and self.alive:
            self.phase2_just_triggered = True
            particles.emit_sovereign_phase2(self.x, self.y)
        if not self.alive:
            particles.emit_sovereign_death(self.x, self.y)

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
        self._contact_cd = max(0.0, self._contact_cd - dt)
        if self.tick_status(dt, particles):
            return

        dx = player.x - self.x
        dy = player.y - self.y
        dist = math.hypot(dx, dy)

        # ── Void field expansion (P2) ─────────────────────────────────────────
        if self._phase2:
            self._void_margin = min(
                C.SOVEREIGN_VOID_MAX,
                self._void_margin + C.SOVEREIGN_VOID_GROW * dt,
            )

        # ── Movement ─────────────────────────────────────────────────────────
        if not self._burst_winding and dist > 0:
            self._move(dx / dist * self.speed * dt, dy / dist * self.speed * dt, room)

        # ── Void Burst ────────────────────────────────────────────────────────
        burst_cd = 1.0 if self._phase2 else C.SOVEREIGN_BURST_CD
        _BURST_WIND = 0.45
        self._burst_cd -= dt

        if self._burst_cd <= _BURST_WIND and not self._burst_winding:
            self._burst_winding = True
            self._burst_wind_up = 0.0

        if self._burst_winding:
            self._burst_wind_up += dt
            if self._burst_wind_up >= _BURST_WIND:
                base_a = math.atan2(dy, dx) if dist > 0 else 0.0
                if self._phase2:
                    # 8-way full ring
                    for i in range(8):
                        a = math.radians(i * 45.0)
                        projs.append(EnemyProjectile(
                            self.x, self.y, a,
                            speed=235, color=C.C_SOVEREIGN_SHOT, damage=1, lifetime=2.2,
                        ))
                else:
                    # 5-way fan toward player
                    for i in range(5):
                        a = base_a + math.radians(-28 + i * 14)
                        projs.append(EnemyProjectile(
                            self.x, self.y, a,
                            speed=235, color=C.C_SOVEREIGN_SHOT, damage=1, lifetime=2.2,
                        ))
                sounds.play("spore_shoot")
                self._burst_cd = burst_cd
                self._burst_winding = False
                self._burst_wind_up = 0.0

        # ── Summon ────────────────────────────────────────────────────────────
        self._summon_cd -= dt
        if self._summon_cd <= 0:
            positions = room.get_spawn_positions(2, min_dist_from_centre=180.0)
            for pos in positions:
                if self._phase2:
                    self._summon_queue.append(VoidShrieker(*pos))
                else:
                    self._summon_queue.append(ShadowWraith(*pos))
            particles.emit_summon_flash(self.x, self.y)
            self._summon_cd = C.SOVEREIGN_SUMMON_CD

        # ── Contact damage ────────────────────────────────────────────────────
        if self._contact_cd <= 0 and dist < self.radius + player.radius:
            if player.take_damage(1):
                particles.emit_player_hurt(player.x, player.y)
            self._contact_cd = 0.8

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        r = self.radius
        pulse = (math.sin(self._bob_t * 3.0) + 1.0) * 0.5

        # Void corona rings
        for ring_off, ring_col in ((6, C.C_SOVEREIGN_SHOT), (12, C.C_SOVEREIGN)):
            ring_r = r + ring_off + round(pulse * 4)
            pygame.draw.circle(surf, ring_col, (sx, sy), ring_r, 2)

        # Phase-2 pulsing second aura
        if self._phase2:
            ring_r2 = r + 18 + round(pulse * 7)
            pygame.draw.circle(surf, C.C_SOVEREIGN_SHOT, (sx, sy), ring_r2, 1)

        # Burst wind-up glow
        if self._burst_winding:
            frac = self._burst_wind_up / 0.45
            pygame.draw.circle(surf, C.C_SOVEREIGN_SHOT, (sx, sy), r + round(frac * 16), 3)

        # Body
        body_sx, body_sy = self._draw_body(surf, camera, C.C_SOVEREIGN_SHOT, C.C_SOVEREIGN)

        # Void eye
        if self._flash <= 0:
            pygame.draw.circle(surf, (0, 0, 0), (body_sx, body_sy), r // 3)
            pygame.draw.circle(surf, C.C_SOVEREIGN_SHOT, (body_sx, body_sy), r // 5)
            pygame.draw.circle(surf, (230, 200, 255), (body_sx, body_sy), r // 8)
