"""Player — movement, dash, shooting, health."""

from __future__ import annotations
import math
import pygame
from gamejam_may_2026 import constants as C
from gamejam_may_2026 import config
from gamejam_may_2026 import sounds
from gamejam_may_2026.projectiles import Arrow

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from gamejam_may_2026.rooms import Room
    from gamejam_may_2026.particles import ParticleSystem
    from gamejam_may_2026.camera import Camera


class Player:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.hp = C.PLAYER_MAX_HP
        self.max_hp = C.PLAYER_MAX_HP
        self.coins = 0

        # ── Per-run stats (modified by perks) ─────────────────────────────────
        self.speed          = float(C.PLAYER_SPEED)
        self.dash_speed     = float(C.PLAYER_DASH_SPEED)
        self.dash_cooldown  = float(C.PLAYER_DASH_COOLDOWN)
        self.dash_duration  = float(C.PLAYER_DASH_DURATION)
        self.iframes_dur    = float(C.PLAYER_IFRAMES)
        self.shoot_cooldown = float(C.PLAYER_SHOOT_COOLDOWN)
        self.arrow_damage   = int(C.ARROW_DAMAGE)
        self.arrow_speed    = float(C.ARROW_SPEED)
        self.piercing       = False   # arrows pass through enemies
        self.double_shot    = False   # fire 2 arrows per click
        self.magnet_range   = 80.0   # coin pull radius (px)

        # Aim
        self.aim_angle = 0.0   # radians

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
        self._flash = 0.0      # white flash duration

        # Radius (collision)
        self.radius = C.PLAYER_RADIUS

        # Dead flag
        self.dead = False

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
        if keys[km["up"]]:    d.y -= 1
        if keys[km["down"]]:  d.y += 1
        if keys[km["left"]]:  d.x -= 1
        if keys[km["right"]]: d.x += 1
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
        self.arrows.append(Arrow(
            self.x, self.y, self.aim_angle,
            speed=self.arrow_speed, damage=self.arrow_damage, piercing=self.piercing,
        ))
        if self.double_shot:
            spread = 0.15  # radians between the two arrows
            self.arrows.append(Arrow(
                self.x, self.y, self.aim_angle + spread,
                speed=self.arrow_speed, damage=self.arrow_damage, piercing=self.piercing,
            ))
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
            if keys[km["up"]]:    mv.y -= 1
            if keys[km["down"]]:  mv.y += 1
            if keys[km["left"]]:  mv.x -= 1
            if keys[km["right"]]: mv.x += 1
            if mv.length_squared() > 0:
                mv = mv.normalize() * (self.speed * dt)
            self._move(mv.x, mv.y, room)

        # Update arrows
        for a in self.arrows:
            a.update(dt, room)
            if not a.alive:
                particles.emit_hit(a.x, a.y, math.degrees(a.angle))
        self.arrows = [a for a in self.arrows if a.alive]

    def _move(self, dx: float, dy: float, room: Room) -> None:
        if room.is_circle_walkable(self.x + dx, self.y, self.radius):
            self.x += dx
        if room.is_circle_walkable(self.x, self.y + dy, self.radius):
            self.y += dy

    # ── Damage ─────────────────────────────────────────────────────────────────
    def take_damage(self, amount: int) -> bool:
        """Return True if damage was actually applied (not during iframes)."""
        if self._iframes > 0 or self._dashing:  # dash gives iframes
            return False
        self.hp -= amount
        self._iframes = self.iframes_dur
        self._flash = 0.12
        if self.hp <= 0:
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
                arc_rect = pygame.Rect(sx - self.radius - 4, sy - self.radius - 4,
                                       (self.radius + 4) * 2, (self.radius + 4) * 2)
                pygame.draw.arc(surf, (100, 180, 255), arc_rect,
                                math.radians(90), math.radians(90 + 360 * frac), 2)

        # Draw player arrows
        for a in self.arrows:
            a.draw(surf, camera)
