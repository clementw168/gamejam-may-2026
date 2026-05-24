"""Main game state machine.

States
------
MENU          — title screen (initial state and post-run landing)
PLAYING       — normal gameplay
TRANSITIONING — camera panning to the next room
UPGRADE       — choosing a perk after clearing a room
SHOP          — browsing the merchant room
FLOOR_CLEAR   — floor boss killed; staircase spawned; press Space to descend
VICTORY       — all 7 floors cleared
DEAD          — player died; press R to return to menu
PAUSED        — game frozen; press Esc to resume
"""

from __future__ import annotations
import json
import math
import random
import time
from pathlib import Path

import pygame

from gamejam_may_2026 import config, constants as C
from gamejam_may_2026 import sounds, ui
from gamejam_may_2026.camera import Camera
from gamejam_may_2026.dungeon import Dungeon, DungeonRoom
from gamejam_may_2026.enemies import (
    Enemy, GoblinArcher, GoblinRunner, SporePlant, Wolf,
    StoneCrawler, VenomfangBat, CrystalTurret,
)
from gamejam_may_2026.particles import ParticleSystem
from gamejam_may_2026.perks import Perk, PERK_POOL
from gamejam_may_2026.player import Player
from gamejam_may_2026.projectiles import EnemyProjectile
from gamejam_may_2026.rooms import Room

# ── High-score persistence ────────────────────────────────────────────────────
_SAVE_DIR   = Path.home() / ".verdant-depths"
_SCORE_FILE = _SAVE_DIR   / "highscore.json"

_SCORE_ZERO: dict = {"floors": 0, "rooms": 0, "coins": 0, "time": 0.0}


def _load_highscore() -> dict:
    try:
        data = json.loads(_SCORE_FILE.read_text())
        # Ensure all keys exist so callers don't have to guard
        return {**_SCORE_ZERO, **data}
    except Exception:
        return dict(_SCORE_ZERO)


def _save_highscore(score: dict) -> None:
    try:
        _SAVE_DIR.mkdir(parents=True, exist_ok=True)
        _SCORE_FILE.write_text(json.dumps(score))
    except Exception:
        pass   # non-fatal — best-effort save


def _is_better(new: dict, old: dict) -> bool:
    """Primary: floors cleared (more = better).  Tiebreak: rooms, then coins."""
    return (new["floors"], new["rooms"], new["coins"]) > (old["floors"], old["rooms"], old["coins"])


# ── Transition constants ───────────────────────────────────────────────────────
_TRANS_DUR = 0.38                    # seconds for the camera pan

_WORLD_DX = {"E": C.ROOM_PIXEL_W, "W": -C.ROOM_PIXEL_W, "N": 0,              "S": 0}
_WORLD_DY = {"E": 0,              "W": 0,               "N": -C.ROOM_PIXEL_H, "S": C.ROOM_PIXEL_H}
_OPP      = {"E": "W",  "W": "E",  "N": "S",  "S": "N"}

# Where to place the player inside the NEW room (local coords) when entering
_TS = C.TILE_SIZE
_ENTER_X = {"W": _TS * 3,                       "E": C.ROOM_PIXEL_W - _TS * 3,
             "N": C.ROOM_PIXEL_W // 2,           "S": C.ROOM_PIXEL_W // 2}
_ENTER_Y = {"N": _TS * 3,                       "S": C.ROOM_PIXEL_H - _TS * 3,
             "E": C.ROOM_PIXEL_H // 2,           "W": C.ROOM_PIXEL_H // 2}

# ── Gate visuals ───────────────────────────────────────────────────────────────
_GATE_COL  = (92, 66, 38)

def _draw_gates(
    surf: pygame.Surface,
    camera: Camera,
    room: Room,
    dirs: set[str] | None = None,
) -> None:
    """Draw wooden-bar gates for the given directions (default: all room doors).

    Bars are confined to the single wall tile so they don't protrude into the
    playfield.  Five bars fit inside 32 px at offsets 2, 8, 14, 20, 26.
    """
    draw_dirs = dirs if dirs is not None else set(room.doors)
    ts = C.TILE_SIZE
    door_left = (C.ROOM_TILE_W // 2 - 1) * ts   # col 19 × 32 = 608 px
    door_top  = (C.ROOM_TILE_H // 2 - 1) * ts   # row  9 × 32 = 288 px

    for d in draw_dirs:
        if d not in room.doors:
            continue
        if d in ("N", "S"):
            # Anchor to the single border row: row 0 (y=0) or row 19 (y=608)
            oy = 0 if d == "N" else (C.ROOM_TILE_H - 1) * ts
            for i in range(5):
                bar_y = oy + 2 + i * 6
                sx, sy = camera.apply_pos(door_left, bar_y)
                pygame.draw.rect(surf, _GATE_COL, (round(sx), round(sy), ts * 3, 4))
        else:
            # Anchor to the single border col: col 0 (x=0) or col 39 (x=1248)
            ox = 0 if d == "W" else (C.ROOM_TILE_W - 1) * ts
            for i in range(5):
                bar_x = ox + 2 + i * 6
                sx, sy = camera.apply_pos(bar_x, door_top)
                pygame.draw.rect(surf, _GATE_COL, (round(sx), round(sy), 4, ts * 3))


# ── Coin ───────────────────────────────────────────────────────────────────────

class Coin:
    PICKUP_R_SQ = 22 ** 2

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.collected = False
        self._bob = random.uniform(0, 6.28)

    def update(self, dt: float, player: Player, particles: ParticleSystem) -> bool:
        """Return True the frame this coin is collected."""
        if self.collected:
            return False
        self._bob += dt * 3.5
        dx = player.x - self.x
        dy = player.y - self.y
        dist_sq = dx * dx + dy * dy
        magnet_sq = player.magnet_range ** 2
        if dist_sq < magnet_sq and dist_sq > 0:
            dist = math.sqrt(dist_sq)
            # Speed ramps from 320 px/s at the magnet edge to 920 px/s at the player
            t = 1.0 - dist / player.magnet_range
            speed = 320.0 + t * 600.0
            self.x += dx / dist * speed * dt
            self.y += dy / dist * speed * dt
        if dist_sq < self.PICKUP_R_SQ:
            self.collected = True
            player.coins += 1
            particles.emit_coin_pickup(self.x, self.y)
            return True
        return False

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        if self.collected:
            return
        bob_y = math.sin(self._bob) * 3
        sx, sy = camera.apply_pos(self.x, self.y + bob_y)
        sx, sy = round(sx), round(sy)
        pygame.draw.circle(surf, C.C_COIN,      (sx, sy), 7)
        pygame.draw.circle(surf, C.C_COIN_DARK, (sx, sy), 7, 1)
        pygame.draw.circle(surf, (255, 245, 140), (sx - 2, sy - 2), 3)


# ── Mossy Chest ───────────────────────────────────────────────────────────────

class Chest:
    """A vine-covered ruin-chest holding upgrade perks.

    Spawns in the room centre after clearing a combat room (50 % chance).
    Auto-opens when the player walks within OPEN_RADIUS px.
    A short grace period prevents instant-open if the player was already there.
    """

    OPEN_RADIUS_SQ: float = 28 ** 2   # px²
    _OPEN_DELAY:    float = 0.7        # s before the chest can be opened

    def __init__(self, x: float, y: float, perks: list) -> None:
        self.x = x
        self.y = y
        self.perks = perks
        self.opened = False
        self._pulse_t = random.uniform(0.0, 6.28)
        self._age = 0.0

    def update(self, dt: float, player: Player) -> bool:
        """Tick; return True the frame the player opens this chest."""
        self._pulse_t += dt * 2.5
        self._age     += dt
        if self.opened or self._age < self._OPEN_DELAY:
            return False
        if (player.x - self.x) ** 2 + (player.y - self.y) ** 2 < self.OPEN_RADIUS_SQ:
            self.opened = True
            return True
        return False

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        if self.opened:
            return
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)

        pulse = (math.sin(self._pulse_t) + 1.0) * 0.5   # 0..1

        # Amber glow
        gr = 20 + round(pulse * 8)
        glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (190, 155, 30, int(42 + pulse * 36)), (gr, gr), gr)
        surf.blit(glow, (sx - gr, sy - gr))

        w, h = 22, 16
        # Drop-shadow
        pygame.draw.rect(surf, (8, 5, 2), (sx - w // 2 + 2, sy - h // 2 + 3, w, h))
        # Body
        pygame.draw.rect(surf, (84, 52, 23), (sx - w // 2, sy - h // 2, w, h))
        # Lid (top ~38 %)
        lid_h = 6
        pygame.draw.rect(surf, (112, 70, 32), (sx - w // 2, sy - h // 2, w, lid_h))
        # Gold band
        pygame.draw.rect(surf, (192, 154, 32), (sx - w // 2, sy - h // 2 + lid_h - 1, w, 2))
        # Gold clasp
        pygame.draw.circle(surf, (210, 172, 42), (sx, sy - h // 2 + lid_h + 1), 3)
        # Moss patches (ruins feel)
        pygame.draw.circle(surf, (50, 126, 34), (sx - 7, sy),     3)
        pygame.draw.circle(surf, (40, 110, 26), (sx + 6, sy + 3), 2)
        # Border
        pygame.draw.rect(surf, (140, 90, 40), (sx - w // 2, sy - h // 2, w, h), 1)

        # Hint label (fades in after grace period)
        if self._age > self._OPEN_DELAY:
            lbl = pygame.font.SysFont("monospace", 12).render("walk over", True, (165, 145, 72))
            surf.blit(lbl, (sx - lbl.get_width() // 2, sy - h // 2 - 14))


# ── Spawn wave ─────────────────────────────────────────────────────────────────

def _spawn_wave(room: Room, floor: int, room_num: int = 1) -> list[Enemy]:
    """Scale enemy variety with room_num; scale counts and stats with floor."""
    depth = min(room_num, 3)
    fl    = min(floor,    7)
    #                              F1  F2  F3  F4  F5  F6  F7
    runners  = (2, 3, 4, 4, 5, 5, 6)[fl - 1]
    wolves   = (1, 1, 2, 2, 2, 3, 3)[fl - 1]
    archers  = (1, 2, 2, 3, 3, 4, 4)[fl - 1] if depth >= 2 else 0
    plants   = (1, 1, 2, 2, 3, 3, 4)[fl - 1] if depth >= 3 else 0
    crawlers = (0, 0, 0, 1, 1, 2, 2)[fl - 1]   # floor 4+ — armoured melee
    bats     = (0, 0, 0, 1, 2, 2, 3)[fl - 1]   # floor 4+ — fast arc mover
    turrets  = (0, 0, 0, 0, 1, 1, 2)[fl - 1]   # floor 5+ — stationary, directional

    total = runners + wolves + archers + plants + crawlers + bats + turrets
    positions = room.get_spawn_positions(total)
    idx  = 0
    wave: list[Enemy] = []
    for _ in range(runners):
        if idx < len(positions): wave.append(GoblinRunner(*positions[idx], floor=floor));  idx += 1
    for _ in range(wolves):
        if idx < len(positions): wave.append(Wolf(*positions[idx], floor=floor));          idx += 1
    for _ in range(archers):
        if idx < len(positions): wave.append(GoblinArcher(*positions[idx], floor=floor));  idx += 1
    for _ in range(plants):
        if idx < len(positions): wave.append(SporePlant(*positions[idx], floor=floor));    idx += 1
    for _ in range(crawlers):
        if idx < len(positions): wave.append(StoneCrawler(*positions[idx], floor=floor));  idx += 1
    for _ in range(bats):
        if idx < len(positions): wave.append(VenomfangBat(*positions[idx], floor=floor));  idx += 1
    for _ in range(turrets):
        if idx < len(positions): wave.append(CrystalTurret(*positions[idx], floor=floor)); idx += 1
    return wave


def _spawn_boss(room: Room, floor: int) -> list[Enemy]:
    """Spawn the floor-appropriate boss at the centre of the boss room."""
    from gamejam_may_2026.enemies import GoblinShaman, AncientTree
    if floor <= 2:
        radius = float(C.SHAMAN_RADIUS)
        cx, cy = room.find_spawn_near_centre(radius)
        return [GoblinShaman(cx, cy, floor=floor)]
    else:
        radius = float(C.TREE_RADIUS)
        cx, cy = room.find_spawn_near_centre(radius)
        return [AncientTree(cx, cy)]


# ── Game ───────────────────────────────────────────────────────────────────────

class Game:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        # Persistent across runs — loaded once, updated on new records
        self._highscore:     dict = _load_highscore()
        self._run_stats:     dict = dict(_SCORE_ZERO)
        self._new_highscore: bool = False
        # Initialise gameplay objects so properties never crash, then park in MENU
        self._new_game()
        self.state = "MENU"

    # ── Init ──────────────────────────────────────────────────────────────────
    def _new_game(self) -> None:
        self.state    = "PLAYING"
        self.room_num = 1

        self.camera    = Camera()
        self.particles = ParticleSystem()
        self.dungeon   = Dungeon(floor=1)

        dr = self.dungeon.current
        px, py = dr.room.find_spawn_near_centre(float(C.PLAYER_RADIUS))
        self.player = Player(px, py)

        self.enemies:           list[Enemy]            = _spawn_wave(dr.room, self.dungeon.floor, self.room_num)
        self.enemy_projectiles: list[EnemyProjectile]  = []
        self.coins:             list[Coin]             = []
        self.chests:            list[Chest]            = []

        # Transition state
        self._trans_t:        float                    = 0.0
        self._trans_wdx:      float                    = 0.0
        self._trans_wdy:      float                    = 0.0
        self._trans_next:     DungeonRoom | None       = None
        self._trans_old_room: Room        | None       = None

        # Upgrade state
        self._upgrade_perks:   list[Perk] = []
        self._upgrade_hovered: int        = -1
        self._upgrade_open_ms: int        = 0   # ticks when upgrade screen opened

        # Shop state
        self._shop_hovered: int = -1

        # Boss-gate hint (shown when player bumps a boss-locked door)
        self._boss_hint_t:   float = 0.0   # seconds remaining
        self._boss_hint_dir: str   = "N"   # which door triggered it

        # Descent staircase (spawns in boss room after clearing)
        self._show_staircase: bool  = False
        self._staircase_x:    float = 0.0
        self._staircase_y:    float = 0.0
        self._staircase_t:    float = 0.0   # animation clock

        # Pause state
        self._pre_pause_state: str = "PLAYING"

        # Run statistics (accumulate across floors)
        self._run_start:            float = time.monotonic()
        self._rooms_cleared_total:  int   = 0
        self._coins_collected_total: int  = 0

    # ── Convenience properties ─────────────────────────────────────────────────
    @property
    def _dr(self) -> DungeonRoom:
        return self.dungeon.current

    @property
    def _room(self) -> Room:
        return self.dungeon.current.room

    # ── Events ────────────────────────────────────────────────────────────────
    def handle_event(self, event: pygame.event.Event) -> None:
        # Escape toggles pause from any live gameplay state
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state in ("PLAYING", "UPGRADE", "SHOP", "FLOOR_CLEAR"):
                self._pre_pause_state = self.state
                self.state = "PAUSED"
                return
            elif self.state == "PAUSED":
                self.state = self._pre_pause_state
                return

        if self.state == "MENU":
            # Any key (Esc quits from MENU — handled in main.py) or click starts run
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self._new_game()
        elif self.state == "PAUSED":
            self._handle_pause_event(event)
        elif self.state == "PLAYING":
            if config.DEBUG and event.type == pygame.KEYDOWN and event.key == pygame.K_k:
                self._debug_kill_all()
            self.player.handle_event(event, self.particles)
        elif self.state == "UPGRADE":
            self._handle_upgrade_event(event)
        elif self.state == "SHOP":
            self._handle_shop_event(event)
        elif self.state == "FLOOR_CLEAR":
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER
            ):
                self._next_floor()
        elif self.state in ("DEAD", "VICTORY"):
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                self.state = "MENU"

    # Grace period (ms) before mouse clicks are accepted on the upgrade screen.
    # Prevents an in-flight shoot-click from instantly picking a perk the player
    # never saw, or from leaving the player frozen on the screen if the click
    # lands outside the cards.
    _UPGRADE_CLICK_GRACE_MS: int = 250

    def _handle_upgrade_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self._upgrade_hovered = self._upgrade_card_at(*event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Ignore clicks that arrived before the grace period expires so that
            # rapid shooting doesn't silently pick a perk or leave the screen open.
            if pygame.time.get_ticks() - self._upgrade_open_ms < self._UPGRADE_CLICK_GRACE_MS:
                return
            idx = self._upgrade_card_at(*event.pos)
            if idx >= 0:
                self._pick_perk(idx)
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_1, pygame.K_KP1):
                self._pick_perk(0)
            elif event.key in (pygame.K_2, pygame.K_KP2):
                self._pick_perk(1)
            elif event.key in (pygame.K_3, pygame.K_KP3):
                self._pick_perk(2)

    def _handle_pause_event(self, event: pygame.event.Event) -> None:
        """P key resumes; clicking Resume or Main Menu acts accordingly."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            self.state = self._pre_pause_state
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            resume_rect, menu_rect = ui.pause_button_rects()
            if resume_rect.collidepoint(event.pos):
                self.state = self._pre_pause_state
            elif menu_rect.collidepoint(event.pos):
                self.state = "MENU"

    def _upgrade_card_at(self, mx: int, my: int) -> int:
        """Return 0/1/2 if (mx, my) is inside that card, else -1."""
        from gamejam_may_2026.ui import _upgrade_card_rect
        for i in range(3):
            if _upgrade_card_rect(i).collidepoint(mx, my):
                return i
        return -1

    def _pick_perk(self, idx: int) -> None:
        if 0 <= idx < len(self._upgrade_perks):
            self._upgrade_perks[idx].apply(self.player)
        self._upgrade_perks   = []
        self._upgrade_hovered = -1
        self.state = "PLAYING"

    # ── Shop ──────────────────────────────────────────────────────────────────
    def _handle_shop_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self._shop_hovered = self._upgrade_card_at(*event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            idx = self._upgrade_card_at(*event.pos)
            if idx >= 0:
                self._buy_shop_item(idx)
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_1, pygame.K_KP1):   self._buy_shop_item(0)
            elif event.key in (pygame.K_2, pygame.K_KP2): self._buy_shop_item(1)
            elif event.key in (pygame.K_3, pygame.K_KP3): self._buy_shop_item(2)
            elif event.key in (pygame.K_SPACE, pygame.K_ESCAPE):
                self._shop_hovered = -1
                self.state = "PLAYING"

    def _buy_shop_item(self, idx: int) -> None:
        items = self._dr.shop_items
        if not (0 <= idx < len(items)):
            return
        item = items[idx]
        if item.get("bought"):
            return
        if self.player.coins < item["cost"]:
            return
        if item["kind"] == "hp":
            if self.player.hp >= self.player.max_hp:
                return                          # greyed out — nothing to restore
            self.player.hp += 1
            # HP vials are reusable; don't mark bought
        else:  # perk
            item["perk"].apply(self.player)
            item["bought"] = True
        self.player.coins -= item["cost"]
        sounds.play("coin")

    def _open_shop(self, dr: DungeonRoom) -> None:
        """Generate shop items on first entry, then switch to SHOP state."""
        if not dr.shop_items:
            # Always slot 0: HP vial
            dr.shop_items.append({"kind": "hp", "cost": 5,
                                   "label": "Heart Vial",
                                   "desc": "Restore 1 HP.",
                                   "icon": "♥", "bought": False})
            # Slots 1 & 2: two distinct random perks
            chosen = random.sample(PERK_POOL, 2)
            for perk in chosen:
                dr.shop_items.append({"kind": "perk", "cost": 8,
                                      "label": perk.name,
                                      "desc": perk.desc,
                                      "icon": perk.icon,
                                      "perk": perk, "bought": False})
        self._shop_hovered = -1
        self.state = "SHOP"

    # ── Floor progression ─────────────────────────────────────────────────────
    def _next_floor(self) -> None:
        """Advance to the next floor, keeping player stats."""
        next_floor = self.dungeon.floor + 1
        self.dungeon  = Dungeon(floor=next_floor)
        self.room_num = 1

        dr = self.dungeon.current
        px, py = dr.room.find_spawn_near_centre(float(C.PLAYER_RADIUS))
        # Preserve player position → teleport to new start; keep all other stats
        self.player.x = px
        self.player.y = py
        self.player.arrows.clear()

        self.enemies           = _spawn_wave(dr.room, next_floor, self.room_num)
        self.enemy_projectiles = []
        self.coins             = []
        self.chests            = []
        self.camera            = Camera()
        self._boss_hint_t      = 0.0
        self._show_staircase   = False
        self._staircase_t      = 0.0
        self.state             = "PLAYING"

    # ── Boss-gate helpers ─────────────────────────────────────────────────────
    def _all_non_boss_cleared(self) -> bool:
        """True when every non-boss room on this floor has been cleared."""
        return all(dr.cleared for dr in self.dungeon.rooms.values() if not dr.is_boss)

    def _boss_locked_doors(self) -> set[str]:
        """Directions from the current room that lead to the boss room while
        it is still locked (not all non-boss rooms cleared)."""
        if self._all_non_boss_cleared():
            return set()
        return {d for d, nbr in self._dr.connections.items() if nbr.is_boss}

    # ── Run-end helper ────────────────────────────────────────────────────────
    def _finish_run(self) -> None:
        """Compute run stats and persist a new high score if earned."""
        elapsed = time.monotonic() - self._run_start
        score: dict = {
            "floors": self.dungeon.floor,
            "rooms":  self._rooms_cleared_total,
            "coins":  self._coins_collected_total,
            "time":   round(elapsed, 1),
        }
        self._run_stats = score
        if _is_better(score, self._highscore):
            _save_highscore(score)
            self._highscore    = score
            self._new_highscore = True
        else:
            self._new_highscore = False

    # ── Update ────────────────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        if self.state in ("MENU", "PAUSED"):
            return   # PAUSED freezes everything; MENU has nothing to tick
        self.camera.update(dt)
        if self._show_staircase:
            self._staircase_t += dt
        if self.state == "PLAYING":
            self._update_playing(dt)
        elif self.state == "FLOOR_CLEAR":
            self._update_floor_clear(dt)
        elif self.state == "TRANSITIONING":
            self._update_transitioning(dt)
        # UPGRADE, DEAD: gameplay frozen — particles still tick (ambient feel)
        self.particles.update(dt)

    def _update_playing(self, dt: float) -> None:
        dr   = self._dr
        room = self._room

        self.player.update(dt, room, self.particles)
        if self.player.dead:
            self._finish_run()
            self.state = "DEAD"
            return

        # ── Block locked doors ────────────────────────────────────────────────
        # Locked = room not cleared (all doors) OR leading to boss-room while
        # boss gate is up (that specific door only).
        # Only clamp inside the door opening; tile walls handle all other edges.
        ts     = C.TILE_SIZE
        r      = C.PLAYER_RADIUS
        margin = ts + r   # 32 + 12 = 44 px — natural wall-face stop distance
        ns_lo = (C.ROOM_TILE_W // 2 - 1) * ts - r   # 596 px  (N/S door x-span)
        ns_hi = (C.ROOM_TILE_W // 2 + 2) * ts + r   # 716 px
        ew_lo = (C.ROOM_TILE_H // 2 - 1) * ts - r   # 276 px  (E/W door y-span)
        ew_hi = (C.ROOM_TILE_H // 2 + 2) * ts + r   # 396 px
        p = self.player

        locked = set(room.doors) if not dr.cleared else (self._boss_locked_doors() & set(room.doors))
        if "N" in locked and p.y < margin and ns_lo < p.x < ns_hi:
            p.y = margin
            if dr.cleared:   # boss gate bump — show hint
                self._boss_hint_t = 2.5; self._boss_hint_dir = "N"
        if "S" in locked and p.y > C.ROOM_PIXEL_H - margin and ns_lo < p.x < ns_hi:
            p.y = C.ROOM_PIXEL_H - margin
            if dr.cleared:
                self._boss_hint_t = 2.5; self._boss_hint_dir = "S"
        if "W" in locked and p.x < margin and ew_lo < p.y < ew_hi:
            p.x = margin
            if dr.cleared:
                self._boss_hint_t = 2.5; self._boss_hint_dir = "W"
        if "E" in locked and p.x > C.ROOM_PIXEL_W - margin and ew_lo < p.y < ew_hi:
            p.x = C.ROOM_PIXEL_W - margin
            if dr.cleared:
                self._boss_hint_t = 2.5; self._boss_hint_dir = "E"

        # Tick boss-gate hint timer
        self._boss_hint_t = max(0.0, self._boss_hint_t - dt)

        # ── Enemies ───────────────────────────────────────────────────────────
        for e in self.enemies:
            e.update(dt, self.player, room, self.particles, self.enemy_projectiles)

        # Drain minion-summon queues from boss enemies
        new_summons: list[Enemy] = []
        for e in self.enemies:
            q = getattr(e, '_summon_queue', None)
            if q:
                new_summons.extend(q)
                q.clear()
        self.enemies.extend(new_summons)

        for ep in self.enemy_projectiles:
            ep.update(dt, room)

        # ── Collisions ────────────────────────────────────────────────────────
        for arrow in self.player.arrows:
            if not arrow.alive:
                continue
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                if id(enemy) in arrow.hit_enemies:
                    continue
                if (arrow.x - enemy.x) ** 2 + (arrow.y - enemy.y) ** 2 < (enemy.radius + 5) ** 2:
                    arrow.hit_enemies.add(id(enemy))
                    if not arrow.piercing:
                        arrow.alive = False
                    # CrystalTurret directional vulnerability
                    actual_dmg = arrow.damage
                    if isinstance(enemy, CrystalTurret):
                        impact = math.atan2(arrow.y - enemy.y, arrow.x - enemy.x)
                        diff   = math.atan2(
                            math.sin(impact - enemy._face_angle),
                            math.cos(impact - enemy._face_angle),
                        )
                        if abs(diff) < math.pi / 3:        # front ±60° — immune
                            actual_dmg = 0
                        elif abs(diff) > math.pi * 2 / 3:  # back 120° — double
                            actual_dmg = arrow.damage * 2
                    if actual_dmg > 0:
                        enemy.take_hit(actual_dmg, self.particles)
                    self.camera.add_shake(3)
                    if getattr(enemy, 'phase2_just_triggered', False):
                        enemy.phase2_just_triggered = False
                        self.camera.add_shake(14)
                    if not enemy.alive:
                        self._drop_coins(enemy)

        for ep in self.enemy_projectiles:
            if not ep.alive:
                continue
            if (ep.x - self.player.x) ** 2 + (ep.y - self.player.y) ** 2 < (C.PLAYER_RADIUS + 6) ** 2:
                ep.alive = False
                if self.player.take_damage(ep.damage):
                    self.particles.emit_player_hurt(self.player.x, self.player.y)
                    self.camera.add_shake(6)

        self.enemies           = [e  for e  in self.enemies           if e.alive]
        self.enemy_projectiles = [ep for ep in self.enemy_projectiles if ep.alive]

        # ── Coins ─────────────────────────────────────────────────────────────
        for coin in self.coins:
            if coin.update(dt, self.player, self.particles):
                sounds.play("coin")
                self._coins_collected_total += 1
        self.coins = [c for c in self.coins if not c.collected]

        # ── Chests ────────────────────────────────────────────────────────────
        for chest in self.chests:
            if chest.update(dt, self.player):
                self._upgrade_perks   = chest.perks
                self._upgrade_hovered = -1
                self._upgrade_open_ms = pygame.time.get_ticks()
                self.chests = [c for c in self.chests if not c.opened]
                self.state = "UPGRADE"
                return
        self.chests = [c for c in self.chests if not c.opened]

        # ── Room-clear check ──────────────────────────────────────────────────
        if not self.enemies and not dr.cleared:
            dr.cleared = True
            self._rooms_cleared_total += 1
            sounds.play("room_clear")
            cx = float(C.ROOM_PIXEL_W // 2)
            cy = float(C.ROOM_PIXEL_H // 2)
            self.particles.emit_room_clear(cx, cy)
            if dr.is_boss:
                # Boss killed — spawn staircase; player walks to it (or presses Space)
                if self.dungeon.floor >= 7:
                    self._finish_run()
                    self.state = "VICTORY"
                else:
                    sx, sy = room.find_spawn_near_centre(20.0)
                    self._staircase_x    = sx
                    self._staircase_y    = sy
                    self._staircase_t    = 0.0
                    self._show_staircase = True
                    self.state = "FLOOR_CLEAR"
                return
            elif not dr.is_start and not dr.is_shop:
                # Normal combat room — 50 % chance to spawn a mossy chest
                if random.random() < 0.5:
                    cx2, cy2 = room.find_spawn_near_centre(28.0)
                    self.chests.append(Chest(cx2, cy2, random.sample(PERK_POOL, 3)))

        # ── Door-exit detection (only when cleared) ────────────────────────────
        if dr.cleared:
            self._check_door_exit()

    def _update_floor_clear(self, dt: float) -> None:
        """Player can move freely during the floor-clear overlay; walking into
        the staircase descends to the next floor (Space is the fallback)."""
        self.player.update(dt, self._room, self.particles)
        if self._show_staircase:
            dx = self.player.x - self._staircase_x
            dy = self.player.y - self._staircase_y
            if dx * dx + dy * dy < 40.0 ** 2:
                self._next_floor()

    def _check_door_exit(self) -> None:
        p      = self.player
        margin = C.TILE_SIZE * 1.6
        ts     = C.TILE_SIZE
        r      = C.PLAYER_RADIUS

        # The door opening spans 3 tiles centred on the room midpoint.
        # Player must actually be inside that opening (laterally) to exit —
        # otherwise pressing against any wall on the correct side would trigger.
        #   N/S doors: cols cx-1..cx+1  → x ∈ [608, 704]  (plus one radius slack)
        #   E/W doors: rows cy-1..cy+1  → y ∈ [288, 384]
        ns_lo = (C.ROOM_TILE_W // 2 - 1) * ts - r   # 596 px
        ns_hi = (C.ROOM_TILE_W // 2 + 2) * ts + r   # 716 px
        ew_lo = (C.ROOM_TILE_H // 2 - 1) * ts - r   # 276 px
        ew_hi = (C.ROOM_TILE_H // 2 + 2) * ts + r   # 396 px

        boss_locked = self._boss_locked_doors()
        for d in self._dr.connections:
            if d in boss_locked:
                continue    # boss gate still up
            if d == "N" and p.y < margin              and ns_lo < p.x < ns_hi:
                self._start_transition(d); return
            if d == "S" and p.y > C.ROOM_PIXEL_H - margin and ns_lo < p.x < ns_hi:
                self._start_transition(d); return
            if d == "W" and p.x < margin              and ew_lo < p.y < ew_hi:
                self._start_transition(d); return
            if d == "E" and p.x > C.ROOM_PIXEL_W - margin and ew_lo < p.y < ew_hi:
                self._start_transition(d); return

    # ── Room transition ───────────────────────────────────────────────────────
    def _start_transition(self, direction: str) -> None:
        self.camera._shake = 0.0          # freeze shake during pan
        self._trans_wdx    = float(_WORLD_DX[direction])
        self._trans_wdy    = float(_WORLD_DY[direction])
        self._trans_t      = 0.0
        self._trans_next   = self._dr.connections[direction]
        self._trans_old_room = self._room

        # Pre-place the player at the entrance of the NEW room (in world-space)
        entry = _OPP[direction]
        self.player.x = self._trans_wdx + _ENTER_X[entry]
        self.player.y = self._trans_wdy + _ENTER_Y[entry]
        self.player.arrows.clear()
        self.enemy_projectiles.clear()

        self.state = "TRANSITIONING"

    def _update_transitioning(self, dt: float) -> None:
        self._trans_t = min(1.0, self._trans_t + dt / _TRANS_DUR)
        t    = self._trans_t
        ease = t * t * (3.0 - 2.0 * t)          # smooth-step
        self.camera.offset.x = self._trans_wdx * ease
        self.camera.offset.y = self._trans_wdy * ease
        if self._trans_t >= 1.0:
            self._commit_transition()

    def _commit_transition(self) -> None:
        assert self._trans_next is not None
        next_dr       = self._trans_next
        if not next_dr.visited:   # only count first-time entries
            self.room_num += 1
        next_dr.visited = True
        self.dungeon.current = next_dr
        self.chests.clear()   # chests belong to the room we just left

        # Convert player from world-space back to local room coords
        self.player.x -= self._trans_wdx
        self.player.y -= self._trans_wdy

        # Reset camera to room-local origin
        self.camera.offset.x = 0.0
        self.camera.offset.y = 0.0

        # Spawn enemies only if room not yet cleared
        if not next_dr.cleared:
            if next_dr.is_shop:
                # Shop rooms have no enemies; clear immediately and open shop
                next_dr.cleared = True
                self.enemies = []
                self.coins.clear()
                self._trans_old_room = None
                self._trans_next     = None
                self._open_shop(next_dr)
                return
            elif next_dr.is_boss:
                self.enemies = _spawn_boss(next_dr.room, self.dungeon.floor)
                self.coins.clear()
            else:
                self.enemies = _spawn_wave(next_dr.room, self.dungeon.floor, self.room_num)
                self.coins.clear()
        else:
            self.enemies = []
            # Re-entering a shop room: re-open the shop overlay
            if next_dr.is_shop:
                self._trans_old_room = None
                self._trans_next     = None
                self._open_shop(next_dr)
                return

        self._trans_old_room = None
        self._trans_next     = None
        self.state = "PLAYING"

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _drop_coins(self, enemy: Enemy) -> None:
        for _ in range(enemy.coin_drop):
            ox = random.uniform(-24, 24)
            oy = random.uniform(-24, 24)
            self.coins.append(Coin(enemy.x + ox, enemy.y + oy))

    def _debug_kill_all(self) -> None:
        """[DEBUG] Instantly kill every living enemy in the current room."""
        for e in self.enemies:
            if e.alive:
                e.take_hit(max(e.hp, 9999), self.particles)
                if not e.alive:
                    self._drop_coins(e)

    # ── Draw ──────────────────────────────────────────────────────────────────
    def draw(self) -> None:
        self.screen.fill(C.C_BG)

        if self.state == "MENU":
            ui.draw_menu(self.screen, self._highscore)
            return

        if self.state == "TRANSITIONING":
            self._draw_transitioning()
        else:
            self._draw_playing()

        # Boss HP bar — shown at top of playfield during the boss fight
        if self.state == "PLAYING" and self._dr.is_boss:
            boss_e = next(
                (e for e in self.enemies if getattr(e, 'is_boss_enemy', False)),
                None,
            )
            if boss_e is not None:
                ui.draw_boss_hpbar(
                    self.screen,
                    boss_e.boss_name,
                    boss_e.hp,
                    boss_e.max_hp,
                    phase2=getattr(boss_e, '_phase2', False),
                )

        ui.draw_hud(
            self.screen, self.player,
            floor_num    = self.dungeon.floor,
            room_num     = self.room_num,
            enemies_left = len(self.enemies),
            debug        = config.DEBUG,
        )
        ui.draw_minimap(self.screen, self.dungeon)

        if self.state == "DEAD":
            ui.draw_death_screen(self.screen, self._run_stats, self._new_highscore, self._highscore)
        elif self.state == "VICTORY":
            ui.draw_victory(self.screen, self._run_stats, self._new_highscore)
        elif self.state == "FLOOR_CLEAR":
            ui.draw_floor_clear(self.screen, self.dungeon.floor)
        elif self.state == "UPGRADE":
            ui.draw_upgrade_screen(self.screen, self._upgrade_perks, self._upgrade_hovered)
        elif self.state == "SHOP":
            ui.draw_shop_screen(self.screen, self._dr.shop_items, self.player, self._shop_hovered)
        elif self.state == "PAUSED":
            # Re-draw whichever overlay was active before pausing, then the pause screen on top
            if self._pre_pause_state == "UPGRADE":
                ui.draw_upgrade_screen(self.screen, self._upgrade_perks, self._upgrade_hovered)
            elif self._pre_pause_state == "SHOP":
                ui.draw_shop_screen(self.screen, self._dr.shop_items, self.player, self._shop_hovered)
            elif self._pre_pause_state == "FLOOR_CLEAR":
                ui.draw_floor_clear(self.screen, self.dungeon.floor)
            ui.draw_pause_screen(self.screen)

    def _draw_playing(self) -> None:
        dr   = self._dr
        room = self._room
        cam  = self.camera

        room.draw(self.screen, cam)

        # Draw gates: all doors when uncleared, or boss-locked doors when cleared
        gate_dirs = set()
        if not dr.cleared:
            gate_dirs = set(room.doors)
        gate_dirs |= self._boss_locked_doors() & set(room.doors)
        if gate_dirs:
            _draw_gates(self.screen, cam, room, gate_dirs)

        # Boss-gate hint tooltip (fades in on bump, fades out after 2.5 s)
        if self._boss_hint_t > 0:
            ui.draw_boss_gate_hint(
                self.screen, self._boss_hint_dir, self._boss_hint_t,
                cam.offset.x, cam.offset.y,
            )

        for coin in self.coins:
            coin.draw(self.screen, cam)
        for chest in self.chests:
            chest.draw(self.screen, cam)
        if self._show_staircase:
            ui.draw_staircase(self.screen, cam,
                              self._staircase_x, self._staircase_y, self._staircase_t)
        for e in self.enemies:
            e.draw(self.screen, cam)
        for ep in self.enemy_projectiles:
            ep.draw(self.screen, cam)
        self.player.draw(self.screen, cam)
        self.particles.draw(self.screen, cam.offset.x, cam.offset.y)

    def _draw_transitioning(self) -> None:
        ox = round(self.camera.offset.x)
        oy = round(self.camera.offset.y)

        # Old room sliding out
        if self._trans_old_room is not None:
            self.screen.blit(self._trans_old_room.surface, (-ox, -oy))

        # New room sliding in
        if self._trans_next is not None:
            nx = round(self._trans_wdx) - ox
            ny = round(self._trans_wdy) - oy
            self.screen.blit(self._trans_next.room.surface, (nx, ny))

        # Player appears in the new room during the pan
        self.player.draw(self.screen, self.camera)
        self.particles.draw(self.screen, self.camera.offset.x, self.camera.offset.y)
