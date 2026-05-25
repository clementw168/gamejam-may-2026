"""Player — movement, dash, shooting, health."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

from gamejam_may_2026 import config, sounds
from gamejam_may_2026 import constants as C
from gamejam_may_2026.projectiles import Arrow

if TYPE_CHECKING:
    from gamejam_may_2026.camera import Camera
    from gamejam_may_2026.particles import ParticleSystem
    from gamejam_may_2026.rooms import Room


class Player:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.hp = C.PLAYER_MAX_HP
        self.max_hp = C.PLAYER_MAX_HP
        self.coins = 0

        # ── Per-run stats (modified by perks) ─────────────────────────────────
        self.speed = float(C.PLAYER_SPEED)
        self.dash_speed = float(C.PLAYER_DASH_SPEED)
        self.dash_cooldown = float(C.PLAYER_DASH_COOLDOWN)
        self.dash_duration = float(C.PLAYER_DASH_DURATION)
        self.iframes_dur = float(C.PLAYER_IFRAMES)
        self.shoot_cooldown = float(C.PLAYER_SHOOT_COOLDOWN)
        self.arrow_damage = int(C.ARROW_DAMAGE)
        self.arrow_speed = float(C.ARROW_SPEED)
        self.piercing = False  # arrows pass through enemies
        self.double_shot = False  # fire 2 arrows per click
        self.magnet_range = 80.0  # coin pull radius (px)

        # Aim
        self.aim_angle = 0.0  # radians

        # Dash state
        self._dashing = False
        self._dash_timer = 0.0
        self._dash_cd = 0.0
        self._dash_dir = pygame.Vector2(1, 0)

        # Shoot state
        self._shoot_cd = 0.0
        self.arrows: list[Arrow] = []

        # Invincibility
        self._iframes = 0.0
        self._flash = 0.0  # white flash duration

        # Radius (collision)
        self.radius = C.PLAYER_RADIUS

        # Dead flag
        self.dead = False

        # ── Relic inventory ───────────────────────────────────────────────────
        self.relics: list = []  # for HUD icon strip

        # Relic effect flags / counters (set by Relic.apply)
        self.wardens_mark: bool = False  # half HP per floor start
        self.echoing_shot: bool = False  # echo arrow on kill
        self.arrow_poison: bool = False  # Venom Gland — tags enemies (Day 12 ticks)
        self.iron_lungs: bool = False  # dash-through contact damage
        self.bone_buckler: bool = False  # Bone Buckler relic (reset charge per room)
        self.block_charge: int = 0  # Bone Buckler — absorb next hit
        self.coin_fed_heart: bool = False  # +1 HP per 100 coins
        self._coin_fed_acc: int = 0  # coin accumulator for Coin-Fed Heart
        self.shrapnel_tips: bool = False  # wall-impact shrapnel fan
        self.phase_cloak: bool = False  # dash stuns enemies
        self.leech_stone: bool = False  # +HP on 50 kills
        self._leech_kills: int = 0  # kill counter
        self.overcharged_quiver: bool = False  # every 4th arrow ×3 dmg
        self._overcharged_count: int = 0  # arrow counter
        self.ancient_sigil: bool = False  # 1 s iframes on room entry
        self.spiked_shell: bool = False  # AoE on hurt
        self.spiked_shell_triggered: bool = False  # set by take_damage; read & cleared by game.py
        self.temporal_blur: bool = False  # blur clones on dash
        self.runic_arrows: bool = False  # arrows bounce off walls
        self.bloodlust: bool = False  # speed on kill
        self._bloodlust_stacks: int = 0  # 0–3
        self._bloodlust_t: float = 0.0  # seconds remaining
        self.curse_of_greed: bool = False  # 2× coins, zero per floor
        self.petrified_heart: bool = False  # 50% dmg reduction, no overheal
        self._petrified_acc: float = 0.0  # accumulates 0.5× damage; triggers when ≥1
        self.hunter_mark: bool = False  # first hit per room ×3
        self._hunter_mark_used: bool = False  # cleared per room
        self.void_core: bool = False  # 8-way pulse every 10 s
        self._void_t: float = 10.0  # countdown to next pulse
        self._void_queue: list = []  # (x, y, angle) tuples for game.py

        # Shrapnel tips — dead wall-hit arrow positions for game.py
        self._wall_hit_arrows: list = []  # (x, y, angle)

    # ── Effective speed (bloodlust bonus stacked on top of base speed) ────────
    @property
    def _effective_speed(self) -> float:
        return self.speed * (1.0 + 0.10 * self._bloodlust_stacks)

    # ── Input handling ─────────────────────────────────────────────────────────
    def handle_event(self, event: pygame.event.Event, particles: ParticleSystem) -> None:
        if event.type == pygame.KEYDOWN and event.key == config.get_keys()["dash"]:
            self._try_dash()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._try_shoot()

    def _try_dash(self) -> None:
        if self._dashing or self._dash_cd > 0:
            return
        keys = pygame.key.get_pressed()
        km = config.get_keys()
        d = pygame.Vector2(0, 0)
        if keys[km["up"]]:
            d.y -= 1
        if keys[km["down"]]:
            d.y += 1
        if keys[km["left"]]:
            d.x -= 1
        if keys[km["right"]]:
            d.x += 1
        if d.length_squared() == 0:
            d = pygame.Vector2(math.cos(self.aim_angle), math.sin(self.aim_angle))
        else:
            d = d.normalize()
        self._dash_dir = d
        self._dashing = True
        self._dash_timer = self.dash_duration
        self._dash_cd = self.dash_cooldown
        sounds.play("dash")

    def _try_shoot(self) -> None:
        if self._shoot_cd > 0:
            return
        angles = [self.aim_angle]
        if self.double_shot:
            angles.append(self.aim_angle + 0.15)
        for ang in angles:
            if self.overcharged_quiver:
                self._overcharged_count += 1
            overcharged = self.overcharged_quiver and (self._overcharged_count % 4 == 0)
            a = Arrow(
                self.x,
                self.y,
                ang,
                speed=self.arrow_speed,
                damage=self.arrow_damage,
                piercing=self.piercing,
                bouncing=self.runic_arrows,
                overcharged=overcharged,
            )
            self.arrows.append(a)
        self._shoot_cd = self.shoot_cooldown
        sounds.play("shoot")

    # ── Update ─────────────────────────────────────────────────────────────────
    def update(self, dt: float, room: Room, particles: ParticleSystem) -> None:
        # Update mouse aim (convert screen pos → accounts for camera offset = 0 in Day-1)
        mx, my = pygame.mouse.get_pos()
        self.aim_angle = math.atan2(my - self.y, mx - self.x)

        # Timers
        self._shoot_cd = max(0.0, self._shoot_cd - dt)
        self._iframes = max(0.0, self._iframes - dt)
        self._flash = max(0.0, self._flash - dt)
        self._dash_cd = max(0.0, self._dash_cd - dt)
        if config.DEBUG:
            self._dash_cd = 0.0  # infinite dash in debug mode

        # Bloodlust speed-buff timer
        if self._bloodlust_t > 0:
            self._bloodlust_t -= dt
            if self._bloodlust_t <= 0:
                self._bloodlust_t = 0.0
                self._bloodlust_stacks = 0

        # Void Core — 8-way pulse every 10 s (queued for game.py to spawn)
        if self.void_core:
            self._void_t -= dt
            if self._void_t <= 0:
                self._void_t = 10.0
                for i in range(8):
                    self._void_queue.append((self.x, self.y, i * math.pi / 4))

        if self._dashing:
            self._dash_timer -= dt
            if self._dash_timer <= 0:
                self._dashing = False
            else:
                d = self._dash_dir
                self._move(d.x * self.dash_speed * dt, d.y * self.dash_speed * dt, room)
                particles.emit_dash_trail(self.x, self.y)
        else:
            keys = pygame.key.get_pressed()
            km = config.get_keys()
            mv = pygame.Vector2(0, 0)
            if keys[km["up"]]:
                mv.y -= 1
            if keys[km["down"]]:
                mv.y += 1
            if keys[km["left"]]:
                mv.x -= 1
            if keys[km["right"]]:
                mv.x += 1
            if mv.length_squared() > 0:
                mv = mv.normalize() * (self._effective_speed * dt)
            self._move(mv.x, mv.y, room)

        # Update arrows
        self._wall_hit_arrows.clear()
        for a in self.arrows:
            a.update(dt, room)
            if not a.alive:
                particles.emit_hit(a.x, a.y, math.degrees(a.angle))
                if getattr(a, "_wall_hit", False) and not getattr(a, "_is_shrapnel", False):
                    self._wall_hit_arrows.append((a.x, a.y, a.angle))
        self.arrows = [a for a in self.arrows if a.alive]

    def _move(self, dx: float, dy: float, room: Room) -> None:
        # Sub-step so the player slides right up to wall faces (no visible gap)
        # and can't tunnel through thin geometry at dash speed.
        _SUBSTEP = 2.0  # px per sub-step
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

    # ── Damage ─────────────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> bool:
        """Return True if damage was actually applied (not during iframes)."""
        if self._iframes > 0 or self._dashing:  # dash gives iframes
            return False
        # Bone Buckler: absorb the first hit each room
        if self.block_charge > 0:
            self.block_charge -= 1
            self._iframes = self.iframes_dur
            self._flash = 0.12
            if self.spiked_shell:
                self.spiked_shell_triggered = True
            return True  # hit registered (for spiked_shell etc.) but no HP lost
        # Petrified Heart: 50 % damage reduction via accumulator.
        # Each hit contributes amount×0.5 to the acc; only integer overflow is applied.
        # e.g. two 1-dmg hits → 0.5+0.5=1 → take 1 HP total instead of 2.
        if self.petrified_heart:
            self._petrified_acc += amount * 0.5
            amount = int(self._petrified_acc)
            self._petrified_acc -= amount
            if amount == 0:
                # Damage absorbed into accumulator — still trigger iframes/flash
                self._iframes = self.iframes_dur
                self._flash = 0.12
                return True
        if self.spiked_shell:
            self.spiked_shell_triggered = True
        self.hp -= amount
        self._iframes = self.iframes_dur
        self._flash = 0.12
        if self.hp <= 0:
            if config.DEBUG:
                self.hp = 1  # HP floor — can't die in debug mode
            else:
                self.hp = 0
                self.dead = True
        return True

    # ── Draw ───────────────────────────────────────────────────────────────────
    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)

        # Invincibility blink
        if self._iframes > 0 and not self._dashing:
            if int(self._iframes * 12) % 2 == 0:
                return  # blink invisible

        color = (255, 255, 255) if self._flash > 0 else (C.C_DASH_TRAIL if self._dashing else C.C_PLAYER)
        dark = (80, 70, 60) if not self._dashing else (60, 100, 160)

        # Shadow
        pygame.draw.circle(surf, (8, 8, 8), (sx + 2, sy + 4), self.radius - 2)
        # Body
        pygame.draw.circle(surf, color, (sx, sy), self.radius)
        # Lower shading
        if self._flash <= 0:
            pygame.draw.circle(surf, dark, (sx, sy + self.radius // 3), self.radius // 2)

        # Aim dot (shows direction)
        ax = sx + round(math.cos(self.aim_angle) * (self.radius - 4))
        ay = sy + round(math.sin(self.aim_angle) * (self.radius - 4))
        pygame.draw.circle(surf, (50, 40, 30), (ax, ay), 4)

        # Dash cooldown arc (outer ring)
        if self._dash_cd > 0:
            frac = 1 - self._dash_cd / self.dash_cooldown
            if frac < 1:
                arc_rect = pygame.Rect(
                    sx - self.radius - 4, sy - self.radius - 4, (self.radius + 4) * 2, (self.radius + 4) * 2
                )
                pygame.draw.arc(surf, (100, 180, 255), arc_rect, math.radians(90), math.radians(90 + 360 * frac), 2)

        # Draw player arrows
        for a in self.arrows:
            a.draw(surf, camera)
