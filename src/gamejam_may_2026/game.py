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
ENDLESS_SELECT — endless mode wave-selection screen
ENDLESS       — endless mode combat (sealed room, infinite waves)
ENDLESS_BETWEEN — between-wave overlay (reward display, press Space to continue)
ENDLESS_DEAD  — endless mode death screen
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import pygame

from gamejam_may_2026 import config, sounds, ui
from gamejam_may_2026 import constants as C
from gamejam_may_2026.camera import Camera
from gamejam_may_2026.dungeon import Dungeon, DungeonRoom
from gamejam_may_2026.enemies import (
    AbyssalLeech,
    AncientTree,
    BoneArcher,
    CrystalTurret,
    Enemy,
    FungalMatriarch,
    GoblinArcher,
    GoblinRunner,
    GoblinShaman,
    IronWarden,
    MagmaSlug,
    ShadowWraith,
    SporeElder,
    SporePlant,
    StoneCrawler,
    VenomfangBat,
    VoidShrieker,
    VoidSovereign,
    Wolf,
)
from gamejam_may_2026.particles import ParticleSystem
from gamejam_may_2026.perks import PERK_POOL, Perk
from gamejam_may_2026.player import Player
from gamejam_may_2026.projectiles import Arrow, EnemyProjectile
from gamejam_may_2026.relics import RELIC_POOL, Relic
from gamejam_may_2026.rooms import Room
from gamejam_may_2026.ui import (
    _arena_card_rect,
    _relic_card_rect,
    _upgrade_card_rect,
    endless_start_button_rect,
    endless_wave_arrow_rects,
)

# ── High-score persistence ────────────────────────────────────────────────────
_SAVE_DIR = Path.home() / ".verdant-depths"
_SCORE_FILE = _SAVE_DIR / "highscore.json"

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
        pass  # non-fatal — best-effort save


def _is_better(new: dict, old: dict) -> bool:
    """Primary: floors cleared (more = better).  Tiebreak: rooms, then coins."""
    return (new["floors"], new["rooms"], new["coins"]) > (old["floors"], old["rooms"], old["coins"])


# ── Transition constants ───────────────────────────────────────────────────────
_TRANS_DUR = 0.38  # seconds for the camera pan

_WORLD_DX = {"E": C.ROOM_PIXEL_W, "W": -C.ROOM_PIXEL_W, "N": 0, "S": 0}
_WORLD_DY = {"E": 0, "W": 0, "N": -C.ROOM_PIXEL_H, "S": C.ROOM_PIXEL_H}
_OPP = {"E": "W", "W": "E", "N": "S", "S": "N"}

# Where to place the player inside the NEW room (local coords) when entering
_TS = C.TILE_SIZE
_ENTER_X = {"W": _TS * 3, "E": C.ROOM_PIXEL_W - _TS * 3, "N": C.ROOM_PIXEL_W // 2, "S": C.ROOM_PIXEL_W // 2}
_ENTER_Y = {"N": _TS * 3, "S": C.ROOM_PIXEL_H - _TS * 3, "E": C.ROOM_PIXEL_H // 2, "W": C.ROOM_PIXEL_H // 2}

# ── Gate visuals ───────────────────────────────────────────────────────────────
_GATE_COL = (92, 66, 38)


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
    door_left = (C.ROOM_TILE_W // 2 - 1) * ts  # col 19 x 32 = 608 px
    door_top = (C.ROOM_TILE_H // 2 - 1) * ts  # row  9 x 32 = 288 px

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


# ── Arena mode enemy roster ────────────────────────────────────────────────────

_ARENA_ENTRIES: list[dict] = [
    # ── Regular enemies ──────────────────────────────────────────────────────
    # cls / cls_kwargs are used for static sprite previews in the selection screen
    {
        "name": "Goblin Runner",
        "cls": GoblinRunner,
        "cls_kwargs": {},
        "spawner": lambda x, y: GoblinRunner(x, y, floor=1),
        "is_boss": False,
        "max_count": 15,
        "desc": "Fast wall-aware melee",
    },
    {
        "name": "Goblin Archer",
        "cls": GoblinArcher,
        "cls_kwargs": {},
        "spawner": lambda x, y: GoblinArcher(x, y, floor=1),
        "is_boss": False,
        "max_count": 12,
        "desc": "Ranged, keeps distance",
    },
    {
        "name": "Wolf",
        "cls": Wolf,
        "cls_kwargs": {},
        "spawner": lambda x, y: Wolf(x, y, floor=1),
        "is_boss": False,
        "max_count": 12,
        "desc": "Melee flanker, lunges",
    },
    {
        "name": "Spore Plant",
        "cls": SporePlant,
        "cls_kwargs": {},
        "spawner": lambda x, y: SporePlant(x, y, floor=1),
        "is_boss": False,
        "max_count": 10,
        "desc": "Stationary 4-way volleys",
    },
    {
        "name": "Spore Elder",
        "cls": SporeElder,
        "cls_kwargs": {},
        "spawner": lambda x, y: SporeElder(x, y, floor=5),
        "is_boss": False,
        "max_count": 6,
        "desc": "Elite 8-way + spore cloud",
    },
    {
        "name": "Stone Crawler",
        "cls": StoneCrawler,
        "cls_kwargs": {},
        "spawner": lambda x, y: StoneCrawler(x, y, floor=4),
        "is_boss": False,
        "max_count": 10,
        "desc": "Armoured, 3-hit deflect",
    },
    {
        "name": "Venomfang Bat",
        "cls": VenomfangBat,
        "cls_kwargs": {},
        "spawner": lambda x, y: VenomfangBat(x, y, floor=4),
        "is_boss": False,
        "max_count": 15,
        "desc": "Fast erratic melee",
    },
    {
        "name": "Crystal Turret",
        "cls": CrystalTurret,
        "cls_kwargs": {},
        "spawner": lambda x, y: CrystalTurret(x, y, floor=5),
        "is_boss": False,
        "max_count": 8,
        "desc": "Rotating 3-way, immune front",
    },
    {
        "name": "Shadow Wraith",
        "cls": ShadowWraith,
        "cls_kwargs": {},
        "spawner": lambda x, y: ShadowWraith(x, y, floor=5),
        "is_boss": False,
        "max_count": 8,
        "desc": "Teleporting, homing shots",
    },
    {
        "name": "Bone Archer",
        "cls": BoneArcher,
        "cls_kwargs": {},
        "spawner": lambda x, y: BoneArcher(x, y, floor=6),
        "is_boss": False,
        "max_count": 10,
        "desc": "3-way spread + bone spike",
    },
    {
        "name": "Magma Slug",
        "cls": MagmaSlug,
        "cls_kwargs": {},
        "spawner": lambda x, y: MagmaSlug(x, y, floor=6),
        "is_boss": False,
        "max_count": 6,
        "desc": "Slow, drops burn patches",
    },
    {
        "name": "Void Shrieker",
        "cls": VoidShrieker,
        "cls_kwargs": {},
        "spawner": lambda x, y: VoidShrieker(x, y, floor=7),
        "is_boss": False,
        "max_count": 12,
        "desc": "8-way death burst",
    },
    # ── Bosses ───────────────────────────────────────────────────────────────
    {
        "name": "Goblin Shaman",
        "cls": GoblinShaman,
        "cls_kwargs": {"floor": 1},
        "spawner": lambda x, y: GoblinShaman(x, y, floor=1),
        "is_boss": True,
        "max_count": 5,
        "desc": "Burst volleys + summons",
    },
    {
        "name": "Ancient Tree",
        "cls": AncientTree,
        "cls_kwargs": {},
        "spawner": lambda x, y: AncientTree(x, y),
        "is_boss": True,
        "max_count": 5,
        "desc": "Root burst + thorn ring",
    },
    {
        "name": "Iron Warden",
        "cls": IronWarden,
        "cls_kwargs": {},
        "spawner": lambda x, y: IronWarden(x, y),
        "is_boss": True,
        "max_count": 5,
        "desc": "Stomp AoE + charge dash",
    },
    {
        "name": "Abyssal Leech",
        "cls": AbyssalLeech,
        "cls_kwargs": {},
        "spawner": lambda x, y: AbyssalLeech(x, y),
        "is_boss": True,
        "max_count": 5,
        "desc": "Homing tendrils, self-heals",
    },
    {
        "name": "Fungal Matriarch",
        "cls": FungalMatriarch,
        "cls_kwargs": {"floor": 6},
        "spawner": lambda x, y: FungalMatriarch(x, y, floor=6),
        "is_boss": True,
        "max_count": 5,
        "desc": "Spore volleys + spore aura",
    },
    {
        "name": "Void Sovereign",
        "cls": VoidSovereign,
        "cls_kwargs": {},
        "spawner": lambda x, y: VoidSovereign(x, y),
        "is_boss": True,
        "max_count": 5,
        "desc": "8-way burst + void arena",
    },
]


# ── Coin ───────────────────────────────────────────────────────────────────────


class Coin:
    PICKUP_R_SQ = 22**2

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
        magnet_sq = player.magnet_range**2
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
        pygame.draw.circle(surf, C.C_COIN, (sx, sy), 7)
        pygame.draw.circle(surf, C.C_COIN_DARK, (sx, sy), 7, 1)
        pygame.draw.circle(surf, (255, 245, 140), (sx - 2, sy - 2), 3)


# ── Mossy Chest ───────────────────────────────────────────────────────────────


class Chest:
    """A vine-covered ruin-chest holding upgrade perks.

    Spawns in the room centre after clearing a combat room (50 % chance).
    Auto-opens when the player walks within OPEN_RADIUS px.
    A short grace period prevents instant-open if the player was already there.
    """

    OPEN_RADIUS_SQ: float = 28**2  # px²
    _OPEN_DELAY: float = 0.7  # s before the chest can be opened

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
        self._age += dt
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

        pulse = (math.sin(self._pulse_t) + 1.0) * 0.5  # 0..1

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
        pygame.draw.circle(surf, (50, 126, 34), (sx - 7, sy), 3)
        pygame.draw.circle(surf, (40, 110, 26), (sx + 6, sy + 3), 2)
        # Border
        pygame.draw.rect(surf, (140, 90, 40), (sx - w // 2, sy - h // 2, w, h), 1)

        # Hint label (fades in after grace period)
        if self._age > self._OPEN_DELAY:
            lbl = pygame.font.SysFont("monospace", 12).render("walk over", True, (165, 145, 72))
            surf.blit(lbl, (sx - lbl.get_width() // 2, sy - h // 2 - 14))


# ── Burn Patch (left by MagmaSlug) ────────────────────────────────────────────


class BurnPatch:
    """A smouldering patch of magma left by a MagmaSlug.

    Deals 1 damage per second to the player while they stand inside it.
    Fades visually as it expires.
    """

    RADIUS: float = 20.0
    LIFETIME: float = 4.0

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self._age = 0.0
        self.alive = True

    def update(self, dt: float, player: Player) -> bool:
        """Tick; return True if the player overlaps (for DoT application)."""
        self._age += dt
        if self._age >= self.LIFETIME:
            self.alive = False
            return False
        dx = player.x - self.x
        dy = player.y - self.y
        return (dx * dx + dy * dy) < (self.RADIUS + C.PLAYER_RADIUS) ** 2

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(self.x, self.y)
        sx, sy = round(sx), round(sy)
        frac = max(0.0, 1.0 - self._age / self.LIFETIME)  # 1 → 0 as it fades
        alpha = int(frac * 160)
        r = round(self.RADIUS * (0.6 + frac * 0.4))
        glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        # Inner bright core
        pygame.draw.circle(glow, (*C.C_BURN_PATCH, alpha), (r, r), r)
        pygame.draw.circle(glow, (*C.C_SLUG, min(255, alpha + 30)), (r, r), max(1, r - 5))
        surf.blit(glow, (sx - r, sy - r))


# ── Spawn wave ─────────────────────────────────────────────────────────────────


def _available_perks(player: Player) -> list[Perk]:
    """Return PERK_POOL excluding one-shot perks already applied to this player."""
    pool = [
        p
        for p in PERK_POOL
        if not ((p.id == "piercing_shot" and player.piercing) or (p.id == "double_shot" and player.double_shot))
    ]
    return pool if len(pool) >= 3 else PERK_POOL


def _pack_wave(
    room: Room,
    floor: int,
    exclude_pos: tuple[float, float] | None = None,
) -> list[Enemy]:
    """Spawn a large group of a single enemy type (pack-room encounter)."""
    fl = min(floor, 7)
    pack_types = ["runner", "wolf"]
    if fl >= 4:
        pack_types += ["bat"]
    if fl >= 5:
        pack_types += ["turret"]
    if fl >= 7:
        pack_types += ["shrieker"]
    pack = random.choice(pack_types)

    if pack == "runner":
        n, cls = random.randint(5, 7), GoblinRunner
    elif pack == "wolf":
        n, cls = random.randint(4, 6), Wolf
    elif pack == "bat":
        n, cls = random.randint(5, 7), VenomfangBat
    elif pack == "turret":
        n, cls = random.randint(3, 4), CrystalTurret
    else:  # shrieker
        n, cls = random.randint(4, 5), VoidShrieker

    positions = room.get_spawn_positions(n, min_dist_from_centre=150.0, exclude_pos=exclude_pos)
    return [cls(px, py, floor=floor) for px, py in positions]


def _spawn_wave(
    room: Room,
    floor: int,
    room_num: int = 1,
    exclude_pos: tuple[float, float] | None = None,
) -> list[Enemy]:
    """Scale enemy variety with room_num; scale counts and stats with floor."""
    depth = min(room_num, 3)
    fl = min(floor, 7)
    #                              F1  F2  F3  F4  F5  F6  F7
    runners = (2, 3, 4, 4, 4, 4, 5)[fl - 1]
    wolves = (1, 1, 2, 2, 2, 2, 2)[fl - 1]
    archers = (1, 2, 2, 2, 3, 3, 3)[fl - 1] if depth >= 2 else 0
    plants = (1, 1, 2, 2, 2, 2, 3)[fl - 1] if depth >= 3 else 0
    elders = (0, 0, 0, 0, 1, 1, 1)[fl - 1] if depth >= 3 else 0  # floor 5+ — elite SporePlant
    crawlers = (0, 0, 0, 1, 1, 2, 2)[fl - 1]  # floor 4+ — armoured melee
    bats = (0, 0, 0, 1, 2, 2, 3)[fl - 1]  # floor 4+ — fast arc mover
    turrets = (0, 0, 0, 0, 1, 1, 2)[fl - 1]  # floor 5+ — stationary, directional
    wraiths = (0, 0, 0, 0, 1, 1, 2)[fl - 1]  # floor 5+ — teleporting caster
    bone_archers = (0, 0, 0, 0, 0, 1, 2)[fl - 1]  # floor 6+ — 3-way spread + bone spike
    slugs = (0, 0, 0, 0, 0, 1, 1)[fl - 1]  # floor 6+ — slow melee + burn patches
    shriekers = (0, 0, 0, 0, 0, 0, 1)[fl - 1]  # floor 7  — death burst + void flash

    total = (
        runners
        + wolves
        + archers
        + plants
        + elders
        + crawlers
        + bats
        + turrets
        + wraiths
        + bone_archers
        + slugs
        + shriekers
    )
    positions = room.get_spawn_positions(total, exclude_pos=exclude_pos)
    idx = 0
    wave: list[Enemy] = []
    for _ in range(runners):
        if idx < len(positions):
            wave.append(GoblinRunner(*positions[idx], floor=floor))
            idx += 1
    for _ in range(wolves):
        if idx < len(positions):
            wave.append(Wolf(*positions[idx], floor=floor))
            idx += 1
    for _ in range(archers):
        if idx < len(positions):
            wave.append(GoblinArcher(*positions[idx], floor=floor))
            idx += 1
    for _ in range(plants):
        if idx < len(positions):
            wave.append(SporePlant(*positions[idx], floor=floor))
            idx += 1
    for _ in range(elders):
        if idx < len(positions):
            wave.append(SporeElder(*positions[idx], floor=floor))
            idx += 1
    for _ in range(crawlers):
        if idx < len(positions):
            wave.append(StoneCrawler(*positions[idx], floor=floor))
            idx += 1
    for _ in range(bats):
        if idx < len(positions):
            wave.append(VenomfangBat(*positions[idx], floor=floor))
            idx += 1
    for _ in range(turrets):
        if idx < len(positions):
            wave.append(CrystalTurret(*positions[idx], floor=floor))
            idx += 1
    for _ in range(wraiths):
        if idx < len(positions):
            wave.append(ShadowWraith(*positions[idx], floor=floor))
            idx += 1
    for _ in range(bone_archers):
        if idx < len(positions):
            wave.append(BoneArcher(*positions[idx], floor=floor))
            idx += 1
    for _ in range(slugs):
        if idx < len(positions):
            wave.append(MagmaSlug(*positions[idx], floor=floor))
            idx += 1
    for _ in range(shriekers):
        if idx < len(positions):
            wave.append(VoidShrieker(*positions[idx], floor=floor))
            idx += 1
    return wave


def _spawn_boss(room: Room, floor: int) -> list[Enemy]:
    """Spawn the floor-appropriate boss at the centre of the boss room."""

    if floor <= 2:
        radius = float(C.SHAMAN_RADIUS)
        cx, cy = room.find_spawn_near_centre(radius)
        return [GoblinShaman(cx, cy, floor=floor)]
    if floor == 3:
        radius = float(C.TREE_RADIUS)
        cx, cy = room.find_spawn_near_centre(radius)
        return [AncientTree(cx, cy)]
    if floor == 4:
        radius = float(C.WARDEN_RADIUS)
        cx, cy = room.find_spawn_near_centre(radius)
        return [IronWarden(cx, cy)]
    if floor == 5:
        radius = float(C.LEECH_RADIUS)
        cx, cy = room.find_spawn_near_centre(radius)
        return [AbyssalLeech(cx, cy)]
    if floor == 6:
        radius = float(C.MATRIARCH_RADIUS)
        cx, cy = room.find_spawn_near_centre(radius)
        return [FungalMatriarch(cx, cy, floor=floor)]
    # floor 7+
    radius = float(C.SOVEREIGN_RADIUS)
    cx, cy = room.find_spawn_near_centre(radius)
    return [VoidSovereign(cx, cy)]


# ── Game ───────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        # Persistent across runs — loaded once, updated on new records
        self._highscore: dict = _load_highscore()
        self._run_stats: dict = dict(_SCORE_ZERO)
        self._new_highscore: bool = False
        # Initialise gameplay objects so properties never crash, then park in MENU
        self._new_game()
        self.state = "MENU"

        # Codex browsing state (persists across runs, independent of game state)
        self._codex_tab: int = 0
        self._codex_scroll: int = 0

        # Main menu button hover state
        self._menu_hovered: int = -1  # 0=dungeon 1=arena 2=codex

        # Arena mode state (persists across arena sessions)
        self._arena_selected: int = 0  # index into _ARENA_ENTRIES
        self._arena_count: int = 1  # enemies to spawn
        self._arena_focus: str = "grid"  # "grid" | "count" | "start"

        # Endless mode state
        self._endless_mode: bool = False  # True while inside an endless run
        self._endless_wave: int = 1  # current wave being fought
        self._endless_wave_just_completed: int = 0  # last wave cleared (for between overlay)
        self._endless_select_wave: int = 0  # start wave chosen on select screen (multiple of 5)
        self._endless_pre_pick_queue: list[str] = []  # "perk" / "relic" picks before first wave
        self._endless_between_reward_lines: list[str] = []
        self._endless_between_next_action: str = "wave"  # "perk" | "relic" | "wave"

    # ── Init ──────────────────────────────────────────────────────────────────
    def _new_game(self) -> None:
        self.state = "PLAYING"
        self.room_num = 1

        self.camera = Camera()
        self.particles = ParticleSystem()
        self.dungeon = Dungeon(floor=1)

        dr = self.dungeon.current
        px, py = dr.room.find_spawn_near_centre(float(C.PLAYER_RADIUS))
        self.player = Player(px, py)

        self.enemies: list[Enemy] = _spawn_wave(dr.room, self.dungeon.floor, self.room_num)
        self.enemy_projectiles: list[EnemyProjectile] = []
        self.coins: list[Coin] = []
        self.chests: list[Chest] = []
        self.burn_patches: list[BurnPatch] = []

        # Transition state
        self._trans_t: float = 0.0
        self._trans_wdx: float = 0.0
        self._trans_wdy: float = 0.0
        self._trans_next: DungeonRoom | None = None
        self._trans_old_room: Room | None = None

        # Upgrade state
        self._upgrade_perks: list[Perk] = []
        self._upgrade_hovered: int = -1
        self._upgrade_open_ms: int = 0  # ticks when upgrade screen opened

        # Relic state (shown between FLOOR_CLEAR and floor advance)
        self._relic_choices: list[Relic] = []
        self._relic_hovered: int = -1

        # Temporal Blur clones (spawned when player dashes with that relic)
        self._blur_clones: list[dict] = []  # each: {x, y, charges}

        # Shop state
        self._shop_hovered: int = -1

        # Boss-gate hint (shown when player bumps a boss-locked door)
        self._boss_hint_t: float = 0.0  # seconds remaining
        self._boss_hint_dir: str = "N"  # which door triggered it

        # Descent staircase (spawns in boss room after clearing)
        self._show_staircase: bool = False
        self._staircase_x: float = 0.0
        self._staircase_y: float = 0.0
        self._staircase_t: float = 0.0  # animation clock
        self._ladder_ready: bool = False  # True after relic pick; walk to staircase to descend

        # Pause state
        self._pre_pause_state: str = "PLAYING"

        # VoidShrieker void-flash vignette
        self._void_flash_t: float = 0.0

        # Run statistics (accumulate across floors)
        self._run_start: float = time.monotonic()
        self._rooms_cleared_total: int = 0
        self._coins_collected_total: int = 0

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
            if self.state in ("PLAYING", "UPGRADE", "SHOP", "FLOOR_CLEAR", "RELIC", "ARENA",
                              "ENDLESS", "ENDLESS_BETWEEN"):
                self._pre_pause_state = self.state
                self.state = "PAUSED"
                return
            if self.state == "PAUSED":
                self.state = self._pre_pause_state
                return

        if self.state == "MENU":
            if event.type == pygame.MOUSEMOTION:
                self._menu_hovered = ui.menu_button_at(*event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                idx = ui.menu_button_at(*event.pos)
                if idx == 0:
                    self._new_game()
                elif idx == 1:
                    self._arena_focus = "grid"
                    self.state = "ARENA_SELECT"
                elif idx == 2:
                    self._endless_select_wave = 0
                    self.state = "ENDLESS_SELECT"
                elif idx == 3:
                    self._codex_tab = 0
                    self._codex_scroll = 0
                    self.state = "CODEX"
            elif event.type == pygame.KEYDOWN:
                k = event.key
                if k == pygame.K_RETURN or k == pygame.K_KP_ENTER or k == pygame.K_SPACE:
                    if self._menu_hovered == 1:
                        self._arena_focus = "grid"
                        self.state = "ARENA_SELECT"
                    elif self._menu_hovered == 2:
                        self._endless_select_wave = 0
                        self.state = "ENDLESS_SELECT"
                    elif self._menu_hovered == 3:
                        self._codex_tab = 0
                        self._codex_scroll = 0
                        self.state = "CODEX"
                    else:
                        self._new_game()
                elif k == pygame.K_UP or k == pygame.K_DOWN:
                    n = 4
                    cur = self._menu_hovered if self._menu_hovered >= 0 else 0
                    self._menu_hovered = (cur + (1 if k == pygame.K_DOWN else -1)) % n
                # Legacy shortcuts
                elif k == pygame.K_a:
                    self._arena_focus = "grid"
                    self.state = "ARENA_SELECT"
                elif k == pygame.K_e:
                    self._endless_select_wave = 0
                    self.state = "ENDLESS_SELECT"
                elif k == pygame.K_c:
                    self._codex_tab = 0
                    self._codex_scroll = 0
                    self.state = "CODEX"
        elif self.state == "ARENA_SELECT":
            self._handle_arena_select_event(event)
        elif self.state == "ARENA":
            self.player.handle_event(event, self.particles)
        elif self.state in ("ARENA_WIN", "ARENA_DEAD"):
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                self.state = "MENU"
        elif self.state == "ENDLESS_SELECT":
            self._handle_endless_select_event(event)
        elif self.state == "ENDLESS":
            self.player.handle_event(event, self.particles)
        elif self.state == "ENDLESS_BETWEEN":
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER
            ):
                self._handle_endless_between_continue()
        elif self.state == "ENDLESS_DEAD":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                self._endless_mode = False
                self.state = "MENU"
        elif self.state == "CODEX":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.state = "MENU"
                elif event.key in (pygame.K_LEFT,):
                    self._codex_tab = (self._codex_tab - 1) % len(ui._CODEX_TABS)
                    self._codex_scroll = 0
                elif event.key in (pygame.K_RIGHT,):
                    self._codex_tab = (self._codex_tab + 1) % len(ui._CODEX_TABS)
                    self._codex_scroll = 0
                elif event.key == pygame.K_UP:
                    self._codex_scroll = max(0, self._codex_scroll - 40)
                elif event.key == pygame.K_DOWN:
                    self._codex_scroll += 40
        elif self.state == "PAUSED":
            self._handle_pause_event(event)
        elif self.state == "PLAYING":
            if config.DEBUG and event.type == pygame.KEYDOWN and event.key == pygame.K_k:
                self._debug_kill_all()
            self.player.handle_event(event, self.particles)
        elif self.state == "UPGRADE":
            self._handle_upgrade_event(event)
        elif self.state == "RELIC":
            self._handle_relic_event(event)
        elif self.state == "SHOP":
            self._handle_shop_event(event)
        elif self.state == "FLOOR_CLEAR":
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self._start_relic_selection()
        elif self.state in ("DEAD", "VICTORY") and event.type == pygame.KEYDOWN and event.key == pygame.K_r:
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

    # ── Arena mode ────────────────────────────────────────────────────────────
    def _handle_arena_select_event(self, event: pygame.event.Event) -> None:
        n = len(_ARENA_ENTRIES)
        cols = ui._ARENA_COLS
        rows = (n + cols - 1) // cols
        sel = self._arena_selected
        cur_row = sel // cols
        cur_col = sel % cols

        def _max_c() -> int:
            return _ARENA_ENTRIES[self._arena_selected]["max_count"]

        if event.type == pygame.KEYDOWN:
            k = event.key

            if k == pygame.K_ESCAPE:
                self.state = "MENU"
                return

            # Enter / Space always start from any focus
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._start_arena()
                return

            # Tab cycles focus forward; Shift+Tab backward
            if k == pygame.K_TAB:
                order = ["grid", "count", "start"]
                idx = order.index(self._arena_focus)
                self._arena_focus = order[(idx + (-1 if event.mod & pygame.KMOD_SHIFT else 1)) % len(order)]
                return

            if self._arena_focus == "grid":
                if k in (pygame.K_LEFT, pygame.K_KP4):
                    new_col = (cur_col - 1) % cols
                    self._arena_selected = cur_row * cols + new_col
                    self._arena_count = min(self._arena_count, _max_c())
                elif k in (pygame.K_RIGHT, pygame.K_KP6):
                    new_col = (cur_col + 1) % cols
                    self._arena_selected = (
                        cur_row * cols + min(new_col, n - 1 - cur_row * cols) if False else cur_row * cols + new_col
                    )
                    self._arena_selected = min(self._arena_selected, n - 1)
                    self._arena_count = min(self._arena_count, _max_c())
                elif k in (pygame.K_UP, pygame.K_KP8):
                    if cur_row == 0:
                        pass  # already at top, stay
                    else:
                        self._arena_selected = (cur_row - 1) * cols + cur_col
                    self._arena_count = min(self._arena_count, _max_c())
                elif k in (pygame.K_DOWN, pygame.K_KP2):
                    if cur_row >= rows - 1:
                        # Bottom row → move focus to count
                        self._arena_focus = "count"
                    else:
                        self._arena_selected = min((cur_row + 1) * cols + cur_col, n - 1)
                    self._arena_count = min(self._arena_count, _max_c())

            elif self._arena_focus == "count":
                if k in (pygame.K_LEFT, pygame.K_KP4):
                    self._arena_count = max(1, self._arena_count - 1)
                elif k in (pygame.K_RIGHT, pygame.K_KP6):
                    self._arena_count = min(_max_c(), self._arena_count + 1)
                elif k in (pygame.K_UP, pygame.K_KP8):
                    self._arena_focus = "grid"
                elif k in (pygame.K_DOWN, pygame.K_KP2):
                    self._arena_focus = "start"

            elif self._arena_focus == "start":
                if k in (pygame.K_UP, pygame.K_KP8):
                    self._arena_focus = "count"

        elif event.type == pygame.MOUSEMOTION:
            # Hovering over start button updates focus visually
            if ui.arena_start_button_rect().collidepoint(event.pos):
                self._arena_focus = "start"

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Click on enemy card
                for i in range(n):
                    if _arena_card_rect(i).collidepoint(event.pos):
                        self._arena_selected = i
                        self._arena_count = min(self._arena_count, _max_c())
                        self._arena_focus = "grid"
                        break
                # Click on start button
                if ui.arena_start_button_rect().collidepoint(event.pos):
                    self._start_arena()
                    return
                # Click on count arrows
                dec_r, inc_r = ui.arena_count_arrow_rects()
                if dec_r.collidepoint(event.pos):
                    self._arena_count = max(1, self._arena_count - 1)
                    self._arena_focus = "count"
                elif inc_r.collidepoint(event.pos):
                    self._arena_count = min(_max_c(), self._arena_count + 1)
                    self._arena_focus = "count"
            elif event.button == 4:  # scroll up → +count
                self._arena_count = min(_max_c(), self._arena_count + 1)
            elif event.button == 5:  # scroll down → -count
                self._arena_count = max(1, self._arena_count - 1)

    def _start_arena(self) -> None:
        """Spawn the selected enemy (and count) in a fresh room; enter ARENA state."""
        entry = _ARENA_ENTRIES[self._arena_selected]
        count = self._arena_count

        # Fresh dungeon for a clean room — use the start room only
        self.dungeon = Dungeon(floor=1)
        dr = self.dungeon.current
        room = dr.room

        # Fresh player — no relics, no perks
        px, py = room.find_spawn_near_centre(float(C.PLAYER_RADIUS))
        self.player = Player(px, py)

        # Spawn enemies away from player
        positions = room.get_spawn_positions(count, min_dist_from_centre=100.0, exclude_pos=(px, py))
        # Pad if the room can't place all of them (very high count edge case)
        while len(positions) < count:
            ex, ey = room.find_spawn_near_centre(30.0)
            positions.append((ex, ey))

        spawner = entry["spawner"]
        self.enemies = [spawner(ex, ey) for ex, ey in positions[:count]]

        # Clear all transient game objects
        self.enemy_projectiles = []
        self.coins = []
        self.chests = []
        self.burn_patches = []
        self.camera = Camera()
        self.particles = ParticleSystem()
        self._blur_clones = []
        self._trans_t = 0.0
        self._trans_wdx = 0.0
        self._trans_wdy = 0.0
        self._trans_next = None
        self._trans_old_room = None
        self._boss_hint_t = 0.0
        self._boss_hint_dir = "N"
        self._show_staircase = False
        self._staircase_t = 0.0
        self._void_flash_t = 0.0
        self._burn_dot_acc = 0.0
        self._mat_aura_acc = 0.0
        self._pre_pause_state = "ARENA"
        # Upgrade/relic UI (unused in arena, but must exist for draw())
        self._upgrade_perks = []
        self._upgrade_hovered = -1
        self._upgrade_open_ms = 0
        self._relic_choices = []
        self._relic_hovered = -1
        self._shop_hovered = -1

        self.state = "ARENA"

    def _update_arena(self, dt: float) -> None:
        """Simplified gameplay loop for the arena (no items, no progression)."""
        room = self._room
        p = self.player

        # ── Player ────────────────────────────────────────────────────────────
        self.player.update(dt, room, self.particles)
        if self.player.dead:
            self.state = "ARENA_DEAD"
            return

        # ── Always block ALL door openings (sealed arena) ─────────────────────
        ts = C.TILE_SIZE
        r = C.PLAYER_RADIUS
        margin = ts + r
        ns_lo = (C.ROOM_TILE_W // 2 - 1) * ts - r
        ns_hi = (C.ROOM_TILE_W // 2 + 2) * ts + r
        ew_lo = (C.ROOM_TILE_H // 2 - 1) * ts - r
        ew_hi = (C.ROOM_TILE_H // 2 + 2) * ts + r
        if "N" in room.doors and p.y < margin and ns_lo < p.x < ns_hi:
            p.y = margin
        if "S" in room.doors and p.y > C.ROOM_PIXEL_H - margin and ns_lo < p.x < ns_hi:
            p.y = C.ROOM_PIXEL_H - margin
        if "W" in room.doors and p.x < margin and ew_lo < p.y < ew_hi:
            p.x = margin
        if "E" in room.doors and p.x > C.ROOM_PIXEL_W - margin and ew_lo < p.y < ew_hi:
            p.x = C.ROOM_PIXEL_W - margin

        # Void Sovereign P2 shrinking arena
        for e in self.enemies:
            if getattr(e, "is_void_sovereign", False) and e.alive:
                vm = getattr(e, "_void_margin", 0.0)
                if vm > 0:
                    p.x = max(vm + p.radius, min(C.ROOM_PIXEL_W - vm - p.radius, p.x))
                    p.y = max(vm + p.radius, min(C.ROOM_PIXEL_H - vm - p.radius, p.y))
                break

        self._void_flash_t = max(0.0, self._void_flash_t - dt)

        # ── Enemies ───────────────────────────────────────────────────────────
        for e in self.enemies:
            e.update(dt, self.player, room, self.particles, self.enemy_projectiles)

        # Drain summon queues (boss minions)
        new_summons: list[Enemy] = []
        for e in self.enemies:
            q = getattr(e, "_summon_queue", None)
            if q:
                new_summons.extend(q)
                q.clear()
        self.enemies.extend(new_summons)

        # Drain burn patch queues (MagmaSlug)
        for e in self.enemies:
            pq = getattr(e, "_patch_queue", None)
            if pq:
                for bx, by in pq:
                    self.burn_patches.append(BurnPatch(bx, by))
                pq.clear()

        # Drain VoidShrieker hit-shake + death-burst queues
        for e in self.enemies:
            if getattr(e, "_hit_shake", False):
                e._hit_shake = False  # type: ignore[attr-defined]
                self.camera.add_shake(4)
                self._void_flash_t = max(self._void_flash_t, 0.25)
            dps = getattr(e, "_death_projs", None)
            if dps:
                self.enemy_projectiles.extend(dps)
                dps.clear()

        # Steer homing projectiles
        for ep in self.enemy_projectiles:
            if getattr(ep, "homing", False):
                dx2 = self.player.x - ep.x
                dy2 = self.player.y - ep.y
                dist2 = math.hypot(dx2, dy2) or 1.0
                tx = dx2 / dist2
                ty = dy2 / dist2
                spd = math.hypot(ep.vx, ep.vy) or 1.0
                cx2 = ep.vx / spd
                cy2 = ep.vy / spd
                turn = math.radians(180.0 * dt)
                cross = cx2 * ty - cy2 * tx
                dot = cx2 * tx + cy2 * ty
                angle = max(-turn, min(turn, math.atan2(cross, dot)))
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                ep.vx = (cx2 * cos_a - cy2 * sin_a) * spd
                ep.vy = (cx2 * sin_a + cy2 * cos_a) * spd

        for ep in self.enemy_projectiles:
            ep.update(dt, room)

        # ── Arrow ↔ enemy collisions ──────────────────────────────────────────
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
                    actual_dmg = arrow.damage
                    if getattr(arrow, "_overcharged", False):
                        actual_dmg = arrow.damage * 3
                    if isinstance(enemy, CrystalTurret):
                        impact = math.atan2(arrow.y - enemy.y, arrow.x - enemy.x)
                        diff = math.atan2(
                            math.sin(impact - enemy._face_angle),
                            math.cos(impact - enemy._face_angle),
                        )
                        if abs(diff) < math.pi / 3:
                            actual_dmg = 0
                        elif abs(diff) > math.pi * 2 / 3:
                            actual_dmg = max(actual_dmg, arrow.damage * 2)
                    if actual_dmg > 0:
                        enemy.take_hit(actual_dmg, self.particles)
                    self.camera.add_shake(3)
                    if getattr(enemy, "phase2_just_triggered", False):
                        enemy.phase2_just_triggered = False
                        self.camera.add_shake(getattr(enemy, "_phase2_shake", 14))

        # ── Enemy projectile ↔ player collisions ──────────────────────────────
        for ep in self.enemy_projectiles:
            if not ep.alive:
                continue
            if (ep.x - self.player.x) ** 2 + (ep.y - self.player.y) ** 2 < (C.PLAYER_RADIUS + 6) ** 2:
                ep.alive = False
                if self.player.take_damage(ep.damage):
                    self.particles.emit_player_hurt(self.player.x, self.player.y)
                    self.camera.add_shake(6)
                    # Abyssal Leech tendril healing
                    leech = getattr(ep, "leech_owner", None)
                    if leech is not None and leech.alive:
                        leech.hp = min(leech.max_hp, leech.hp + 3)

        self.enemies = [e for e in self.enemies if e.alive]
        self.enemy_projectiles = [ep for ep in self.enemy_projectiles if ep.alive]

        # Drain any late VoidShrieker death bursts
        for e in self.enemies:
            dps = getattr(e, "_death_projs", None)
            if dps:
                self.enemy_projectiles.extend(dps)
                dps.clear()

        # ── Burn patches ──────────────────────────────────────────────────────
        _bda = getattr(self, "_burn_dot_acc", 0.0)
        burn_overlap = any(patch.update(dt, self.player) for patch in self.burn_patches)
        if burn_overlap:
            _bda += dt
            if _bda >= 1.0:
                _bda -= 1.0
                if self.player.take_damage(1):
                    self.particles.emit_player_hurt(self.player.x, self.player.y)
                    self.camera.add_shake(4)
        else:
            _bda = max(0.0, _bda - dt * 0.5)
        self._burn_dot_acc = _bda
        self.burn_patches = [bp for bp in self.burn_patches if bp.alive]

        # ── Fungal Matriarch passive spore aura ───────────────────────────────
        _maa = getattr(self, "_mat_aura_acc", 0.0)
        mat_overlap = any(
            getattr(e, "_spore_cloud_passive", False)
            and e.alive
            and (self.player.x - e.x) ** 2 + (self.player.y - e.y) ** 2 < 80**2
            for e in self.enemies
        )
        if mat_overlap:
            _maa += dt * 0.5
            if _maa >= 1.0:
                _maa -= 1.0
                if self.player.take_damage(1):
                    self.particles.emit_player_hurt(self.player.x, self.player.y)
                    self.camera.add_shake(3)
        else:
            _maa = max(0.0, _maa - dt * 0.3)
        self._mat_aura_acc = _maa

        # ── Arena clear check ─────────────────────────────────────────────────
        if not self.enemies:
            self.state = "ARENA_WIN"

    # ── Endless mode ─────────────────────────────────────────────────────────
    _ENDLESS_MAX_START = 35  # 7 cycles × 5 waves

    def _handle_endless_select_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_ESCAPE:
                self.state = "MENU"
            elif k in (pygame.K_LEFT, pygame.K_a):
                self._endless_select_wave = max(0, self._endless_select_wave - 5)
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self._endless_select_wave = min(self._ENDLESS_MAX_START, self._endless_select_wave + 5)
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._start_endless()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            dec_r, inc_r = endless_wave_arrow_rects()
            if dec_r.collidepoint(event.pos):
                self._endless_select_wave = max(0, self._endless_select_wave - 5)
            elif inc_r.collidepoint(event.pos):
                self._endless_select_wave = min(self._ENDLESS_MAX_START, self._endless_select_wave + 5)
            elif endless_start_button_rect().collidepoint(event.pos):
                self._start_endless()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 4:
            self._endless_select_wave = min(self._ENDLESS_MAX_START, self._endless_select_wave + 5)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 5:
            self._endless_select_wave = max(0, self._endless_select_wave - 5)

    def _start_endless(self) -> None:
        """Initialise endless mode and begin pre-picks (if any), then first wave."""
        start_wave = self._endless_select_wave

        # Fresh dungeon (single start room used as sealed arena)
        self.dungeon = Dungeon(floor=1)
        dr = self.dungeon.current
        room = dr.room

        # Fresh player
        px, py = room.find_spawn_near_centre(float(C.PLAYER_RADIUS))
        self.player = Player(px, py)

        # Clear all transients
        self.enemies = []
        self.enemy_projectiles = []
        self.coins = []
        self.chests = []
        self.burn_patches = []
        self.camera = Camera()
        self.particles = ParticleSystem()
        self._blur_clones = []
        self._trans_t = 0.0
        self._trans_wdx = 0.0
        self._trans_wdy = 0.0
        self._trans_next = None
        self._trans_old_room = None
        self._boss_hint_t = 0.0
        self._boss_hint_dir = "N"
        self._show_staircase = False
        self._staircase_t = 0.0
        self._void_flash_t = 0.0
        self._burn_dot_acc = 0.0
        self._mat_aura_acc = 0.0
        self._pre_pause_state = "ENDLESS"
        self._upgrade_perks = []
        self._upgrade_hovered = -1
        self._upgrade_open_ms = 0
        self._relic_choices = []
        self._relic_hovered = -1
        self._shop_hovered = -1

        # Endless-specific state
        self._endless_mode = True
        self._endless_wave = start_wave + 1  # first wave to actually fight
        self._endless_wave_just_completed = 0

        # Build pre-pick queue: one perk + one relic per completed cycle
        cycles = start_wave // 5
        self._endless_pre_pick_queue = []
        for _ in range(cycles):
            self._endless_pre_pick_queue.append("perk")
            self._endless_pre_pick_queue.append("relic")

        if self._endless_pre_pick_queue:
            kind = self._endless_pre_pick_queue.pop(0)
            self._endless_offer(kind)
        else:
            self._start_next_endless_wave()

    def _endless_offer(self, kind: str) -> None:
        """Present a perk or relic choice screen (pre-pick or mid-run reward)."""
        if kind == "perk":
            pool = _available_perks(self.player)
            self._upgrade_perks = random.sample(pool, min(3, len(pool)))
            self._upgrade_hovered = -1
            self._upgrade_open_ms = pygame.time.get_ticks()
            self.state = "UPGRADE"
        else:  # relic
            held_ids = {r.id for r in self.player.relics}
            available = [r for r in RELIC_POOL if r.id not in held_ids]
            if not available:
                # All relics held — skip gracefully
                self._after_endless_pick()
                return
            self._relic_choices = random.sample(available, min(2, len(available)))
            self._relic_hovered = -1
            self.state = "RELIC"

    def _after_endless_pick(self) -> None:
        """Called after any perk/relic pick while in endless mode."""
        if self._endless_pre_pick_queue:
            kind = self._endless_pre_pick_queue.pop(0)
            self._endless_offer(kind)
        else:
            self._start_next_endless_wave()

    def _start_next_endless_wave(self) -> None:
        """Spawn enemies for the current endless wave and enter ENDLESS state."""
        wave = self._endless_wave
        room = self._room
        px, py = self.player.x, self.player.y

        if wave % 5 == 0:
            # Boss wave: cycle through the 7 bosses then repeat
            cycle = (wave - 1) // 5  # 0-indexed (wave 5 → 0, wave 10 → 1 …)
            boss_floor = (cycle % 7) + 1
            self.enemies = _spawn_boss(room, boss_floor)
        else:
            cycle = (wave - 1) // 5
            pos = (wave - 1) % 5  # 0–3 for regular waves within a cycle
            vfloor = min(7, 1 + cycle)
            room_depth = min(3, pos + 1)
            self.enemies = _spawn_wave(room, vfloor, room_depth, exclude_pos=(px, py))

        self.enemy_projectiles = []
        self.burn_patches = []
        self._blur_clones = []
        self._void_flash_t = 0.0
        self._burn_dot_acc = 0.0
        self._mat_aura_acc = 0.0

        # Teleport player to room centre for each new wave
        new_px, new_py = room.find_spawn_near_centre(float(C.PLAYER_RADIUS))
        self.player.x = new_px
        self.player.y = new_py
        self.player.arrows.clear()
        self.player._iframes = 0.5  # brief entry grace period

        # Per-wave relic resets (same as room-entry in campaign)
        self.player._hunter_mark_used = False
        if self.player.bone_buckler:
            self.player.block_charge = 1

        self._pre_pause_state = "ENDLESS"
        self.state = "ENDLESS"

    def _endless_wave_complete(self) -> None:
        """Handle wave-clear in endless mode: apply rewards, set up between state."""
        completed = self._endless_wave
        pos = (completed - 1) % 5  # 0–4 within the cycle

        sounds.play("room_clear")
        cx_f = float(C.ROOM_PIXEL_W // 2)
        cy_f = float(C.ROOM_PIXEL_H // 2)
        self.particles.emit_room_clear(cx_f, cy_f)

        reward_lines: list[str] = []
        next_action = "wave"

        if completed % 5 == 0:
            # Boss wave — full HP restore + relic pick
            self.player.hp = self.player.max_hp
            reward_lines = [
                "Full HP restored!",
                "Choose a relic to keep forever.",
            ]
            next_action = "relic"
        else:
            # Regular wave — +1 HP (if not already full)
            if self.player.hp < self.player.max_hp:
                self.player.hp = min(self.player.max_hp, self.player.hp + 1)
                reward_lines.append("+1 HP restored.")
            else:
                reward_lines.append("HP already full.")
            if pos == 1:
                # Wave 2 / 7 / 12 … — also offer a perk
                reward_lines.append("Choose a perk!")
                next_action = "perk"

        self._endless_wave_just_completed = completed
        self._endless_wave += 1  # advance to next wave number
        self._endless_between_reward_lines = reward_lines
        self._endless_between_next_action = next_action
        self.state = "ENDLESS_BETWEEN"

    def _handle_endless_between_continue(self) -> None:
        """Called when player presses Space/Enter in ENDLESS_BETWEEN."""
        action = self._endless_between_next_action
        if action == "perk":
            self._endless_offer("perk")
        elif action == "relic":
            self._endless_offer("relic")
        else:
            self._start_next_endless_wave()

    def _update_endless(self, dt: float) -> None:
        """Endless mode combat loop — full relic/perk effects; no coins or chests."""
        room = self._room
        p = self.player

        # ── Player ────────────────────────────────────────────────────────────
        prev_px = p.x
        prev_py = p.y
        was_dashing = p._dashing
        p.update(dt, room, self.particles)
        if p.dead:
            self.state = "ENDLESS_DEAD"
            return

        # Temporal Blur — spawn 2 clones at dash-start position
        if p.temporal_blur and not was_dashing and p._dashing:
            for _ in range(2):
                self._blur_clones.append({"x": prev_px, "y": prev_py, "charges": 1})

        # Shrapnel Tips — spawn 3 mini-shrapnel per wall-hit arrow
        if p.shrapnel_tips:
            for wx, wy, wang in p._wall_hit_arrows:
                refl_base = math.atan2(-math.sin(wang), -math.cos(wang))
                for dang in (-0.52, 0.0, 0.52):
                    shr = Arrow(wx, wy, refl_base + dang, speed=450, damage=1, lifetime=0.30)
                    shr._is_shrapnel = True  # type: ignore[attr-defined]
                    p.arrows.append(shr)

        # Phase Cloak / Iron Lungs — dash-through effects
        if p._dashing:
            for e in self.enemies:
                if e.alive and (e.x - p.x) ** 2 + (e.y - p.y) ** 2 < (e.radius + p.radius) ** 2:
                    if p.phase_cloak:
                        e._stun_t = max(e._stun_t, 0.8)
                    if p.iron_lungs:
                        e.take_hit(1, self.particles)
                        if not e.alive:
                            self._drop_coins(e)

        # ── Block ALL door openings (sealed arena) ────────────────────────────
        ts = C.TILE_SIZE
        r = C.PLAYER_RADIUS
        margin = ts + r
        ns_lo = (C.ROOM_TILE_W // 2 - 1) * ts - r
        ns_hi = (C.ROOM_TILE_W // 2 + 2) * ts + r
        ew_lo = (C.ROOM_TILE_H // 2 - 1) * ts - r
        ew_hi = (C.ROOM_TILE_H // 2 + 2) * ts + r
        if "N" in room.doors and p.y < margin and ns_lo < p.x < ns_hi:
            p.y = margin
        if "S" in room.doors and p.y > C.ROOM_PIXEL_H - margin and ns_lo < p.x < ns_hi:
            p.y = C.ROOM_PIXEL_H - margin
        if "W" in room.doors and p.x < margin and ew_lo < p.y < ew_hi:
            p.x = margin
        if "E" in room.doors and p.x > C.ROOM_PIXEL_W - margin and ew_lo < p.y < ew_hi:
            p.x = C.ROOM_PIXEL_W - margin

        # Void Sovereign P2 shrinking arena
        for e in self.enemies:
            if getattr(e, "is_void_sovereign", False) and e.alive:
                vm = getattr(e, "_void_margin", 0.0)
                if vm > 0:
                    p.x = max(vm + p.radius, min(C.ROOM_PIXEL_W - vm - p.radius, p.x))
                    p.y = max(vm + p.radius, min(C.ROOM_PIXEL_H - vm - p.radius, p.y))
                break

        self._void_flash_t = max(0.0, self._void_flash_t - dt)

        # Void Core relic — drain pulse queue → piercing arrows
        for vx2, vy2, vangle in p._void_queue:
            vcore_arrow = Arrow(vx2, vy2, vangle, speed=280, damage=p.arrow_damage, lifetime=0.6)
            vcore_arrow.piercing = True
            p.arrows.append(vcore_arrow)
        p._void_queue.clear()

        # ── Enemies ───────────────────────────────────────────────────────────
        for e in self.enemies:
            e.update(dt, p, room, self.particles, self.enemy_projectiles)

        # Drain summon queues (boss minions)
        new_summons: list[Enemy] = []
        for e in self.enemies:
            q = getattr(e, "_summon_queue", None)
            if q:
                new_summons.extend(q)
                q.clear()
        self.enemies.extend(new_summons)

        # Drain MagmaSlug burn-patch queues
        for e in self.enemies:
            pq = getattr(e, "_patch_queue", None)
            if pq:
                for bx, by in pq:
                    self.burn_patches.append(BurnPatch(bx, by))
                pq.clear()

        # Drain VoidShrieker hit-shake + death-burst queues
        for e in self.enemies:
            if getattr(e, "_hit_shake", False):
                e._hit_shake = False  # type: ignore[attr-defined]
                self.camera.add_shake(4)
                self._void_flash_t = max(self._void_flash_t, 0.25)
            dps = getattr(e, "_death_projs", None)
            if dps:
                self.enemy_projectiles.extend(dps)
                dps.clear()

        # Steer homing projectiles
        for ep in self.enemy_projectiles:
            if getattr(ep, "homing", False):
                dx2 = p.x - ep.x
                dy2 = p.y - ep.y
                dist2 = math.hypot(dx2, dy2) or 1.0
                tx = dx2 / dist2
                ty = dy2 / dist2
                spd = math.hypot(ep.vx, ep.vy) or 1.0
                cx2 = ep.vx / spd
                cy2 = ep.vy / spd
                turn = math.radians(180.0 * dt)
                cross = cx2 * ty - cy2 * tx
                dot = cx2 * tx + cy2 * ty
                angle = max(-turn, min(turn, math.atan2(cross, dot)))
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                ep.vx = (cx2 * cos_a - cy2 * sin_a) * spd
                ep.vy = (cx2 * sin_a + cy2 * cos_a) * spd

        for ep in self.enemy_projectiles:
            ep.update(dt, room)

        # ── Arrow ↔ enemy collisions ──────────────────────────────────────────
        for arrow in p.arrows:
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
                    actual_dmg = arrow.damage
                    if getattr(arrow, "_overcharged", False):
                        actual_dmg = arrow.damage * 3
                    if isinstance(enemy, CrystalTurret):
                        impact = math.atan2(arrow.y - enemy.y, arrow.x - enemy.x)
                        diff = math.atan2(
                            math.sin(impact - enemy._face_angle),
                            math.cos(impact - enemy._face_angle),
                        )
                        if abs(diff) < math.pi / 3:
                            actual_dmg = 0
                        elif abs(diff) > math.pi * 2 / 3:
                            actual_dmg = max(actual_dmg, arrow.damage * 2)
                    if actual_dmg > 0:
                        if p.hunter_mark and not p._hunter_mark_used:
                            actual_dmg *= 3
                            p._hunter_mark_used = True
                        enemy.take_hit(actual_dmg, self.particles)
                        if p.arrow_poison:
                            enemy._poison_t = max(enemy._poison_t, 4.0)
                    self.camera.add_shake(3)
                    if getattr(enemy, "phase2_just_triggered", False):
                        enemy.phase2_just_triggered = False
                        self.camera.add_shake(getattr(enemy, "_phase2_shake", 14))
                    if not enemy.alive:
                        self._drop_coins(enemy)
                        if p.echoing_shot:
                            living = [e for e in self.enemies if e.alive and e is not enemy]
                            if living:
                                near = min(
                                    living,
                                    key=lambda e: (e.x - enemy.x) ** 2 + (e.y - enemy.y) ** 2,
                                )
                                if (near.x - enemy.x) ** 2 + (near.y - enemy.y) ** 2 < 300**2:
                                    ea = math.atan2(near.y - enemy.y, near.x - enemy.x)
                                    p.arrows.append(
                                        Arrow(
                                            enemy.x,
                                            enemy.y,
                                            ea,
                                            speed=p.arrow_speed,
                                            damage=p.arrow_damage,
                                            piercing=p.piercing,
                                        )
                                    )
                        if p.leech_stone:
                            p._leech_kills += 1
                            if p._leech_kills >= 50:
                                p._leech_kills = 0
                                if p.hp < p.max_hp:
                                    p.hp += 1
                        if p.bloodlust:
                            p._bloodlust_stacks = min(3, p._bloodlust_stacks + 1)
                            p._bloodlust_t = 3.0

        # ── Enemy projectile ↔ player collisions ──────────────────────────────
        for ep in self.enemy_projectiles:
            if not ep.alive:
                continue
            # Temporal Blur clones intercept projectiles
            absorbed = False
            for clone in self._blur_clones:
                if (ep.x - clone["x"]) ** 2 + (ep.y - clone["y"]) ** 2 < 14**2:
                    ep.alive = False
                    clone["charges"] -= 1
                    self.particles.emit_hit(ep.x, ep.y, 0)
                    absorbed = True
                    break
            if absorbed:
                continue
            if (ep.x - p.x) ** 2 + (ep.y - p.y) ** 2 < (C.PLAYER_RADIUS + 6) ** 2:
                ep.alive = False
                if p.take_damage(ep.damage):
                    self.particles.emit_player_hurt(p.x, p.y)
                    self.camera.add_shake(6)
                    leech = getattr(ep, "leech_owner", None)
                    if leech is not None and leech.alive:
                        leech.hp = min(leech.max_hp, leech.hp + 3)
                    if p.spiked_shell:
                        for e in self.enemies:
                            if e.alive and (e.x - p.x) ** 2 + (e.y - p.y) ** 2 < 80**2:
                                e.take_hit(2, self.particles)
                                if not e.alive:
                                    self._drop_coins(e)

        # Prune expired blur clones
        self._blur_clones = [c for c in self._blur_clones if c["charges"] > 0]

        self.enemies = [e for e in self.enemies if e.alive]
        self.enemy_projectiles = [ep for ep in self.enemy_projectiles if ep.alive]

        # Drain any late death-burst projectiles
        for e in self.enemies:
            dps = getattr(e, "_death_projs", None)
            if dps:
                self.enemy_projectiles.extend(dps)
                dps.clear()

        # ── Burn patches ──────────────────────────────────────────────────────
        _bda = getattr(self, "_burn_dot_acc", 0.0)
        burn_overlap = any(patch.update(dt, p) for patch in self.burn_patches)
        if burn_overlap:
            _bda += dt
            if _bda >= 1.0:
                _bda -= 1.0
                if p.take_damage(1):
                    self.particles.emit_player_hurt(p.x, p.y)
                    self.camera.add_shake(4)
        else:
            _bda = max(0.0, _bda - dt * 0.5)
        self._burn_dot_acc = _bda
        self.burn_patches = [bp for bp in self.burn_patches if bp.alive]

        # ── Fungal Matriarch passive spore aura ───────────────────────────────
        _maa = getattr(self, "_mat_aura_acc", 0.0)
        mat_overlap = any(
            getattr(e, "_spore_cloud_passive", False)
            and e.alive
            and (p.x - e.x) ** 2 + (p.y - e.y) ** 2 < 80**2
            for e in self.enemies
        )
        if mat_overlap:
            _maa += dt * 0.5
            if _maa >= 1.0:
                _maa -= 1.0
                if p.take_damage(1):
                    self.particles.emit_player_hurt(p.x, p.y)
                    self.camera.add_shake(3)
        else:
            _maa = max(0.0, _maa - dt * 0.3)
        self._mat_aura_acc = _maa

        # ── Coins ─────────────────────────────────────────────────────────────
        for coin in self.coins:
            if coin.update(dt, p, self.particles):
                sounds.play("coin")
                if p.coin_fed_heart:
                    p._coin_fed_acc += 1
                    if p._coin_fed_acc >= 100:
                        p._coin_fed_acc = 0
                        if p.hp < p.max_hp and not p.petrified_heart:
                            p.hp += 1
        self.coins = [c for c in self.coins if not c.collected]

        # ── Wave clear check ──────────────────────────────────────────────────
        if not self.enemies:
            self._endless_wave_complete()

    # ── Relic selection ───────────────────────────────────────────────────────
    def _start_relic_selection(self) -> None:
        """Randomly pick 2 relics from the pool (excluding already-held ones) and
        enter the RELIC state.  If the pool is exhausted, advance directly."""
        held_ids = {r.id for r in self.player.relics}
        available = [r for r in RELIC_POOL if r.id not in held_ids]
        if not available:
            self._ladder_ready = True
            self.state = "PLAYING"
            return
        self._relic_choices = random.sample(available, min(2, len(available)))
        self._relic_hovered = -1
        self.state = "RELIC"

    def _handle_relic_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self._relic_hovered = self._relic_card_at(*event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            idx = self._relic_card_at(*event.pos)
            if idx >= 0:
                self._pick_relic(idx)
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_1, pygame.K_KP1):
                self._pick_relic(0)
            elif event.key in (pygame.K_2, pygame.K_KP2):
                self._pick_relic(1)

    def _relic_card_at(self, mx: int, my: int) -> int:
        """Return 0 or 1 if (mx, my) hits that relic card, else -1."""
        for i in range(len(self._relic_choices)):
            if _relic_card_rect(i).collidepoint(mx, my):
                return i
        return -1

    def _pick_relic(self, idx: int) -> None:
        if 0 <= idx < len(self._relic_choices):
            relic = self._relic_choices[idx]
            relic.apply(self.player)
            self.player.relics.append(relic)
        self._relic_choices = []
        self._relic_hovered = -1
        if self._endless_mode:
            self._after_endless_pick()
        else:
            # Return to PLAYING so the player can freely explore before descending
            self._ladder_ready = True
            self.state = "PLAYING"

    def _upgrade_card_at(self, mx: int, my: int) -> int:
        """Return 0/1/2 if (mx, my) is inside that card, else -1."""
        for i in range(3):
            if _upgrade_card_rect(i).collidepoint(mx, my):
                return i
        return -1

    def _pick_perk(self, idx: int) -> None:
        if 0 <= idx < len(self._upgrade_perks):
            self._upgrade_perks[idx].apply(self.player)
        self._upgrade_perks = []
        self._upgrade_hovered = -1
        if self._endless_mode:
            self._after_endless_pick()
        else:
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
            if event.key in (pygame.K_1, pygame.K_KP1):
                self._buy_shop_item(0)
            elif event.key in (pygame.K_2, pygame.K_KP2):
                self._buy_shop_item(1)
            elif event.key in (pygame.K_3, pygame.K_KP3):
                self._buy_shop_item(2)
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
                return  # greyed out — nothing to restore
            self.player.hp += 1
            # HP vials are reusable (don't mark bought)
        else:  # perk
            item["perk"].apply(self.player)
            item["bought"] = True
        self.player.coins -= item["cost"]
        sounds.play("coin")

    def _open_shop(self, dr: DungeonRoom) -> None:
        """Generate shop items on first entry, then switch to SHOP state."""
        if not dr.shop_items:
            fl = min(self.dungeon.floor, 7) - 1  # 0-based index
            hp_price = C.SHOP_HP_PRICE[fl]
            perk_price = C.SHOP_PERK_PRICE[fl]
            # Slot 0: HP vial (once per floor)
            dr.shop_items.append(
                {
                    "kind": "hp",
                    "cost": hp_price,
                    "label": "Heart Vial",
                    "desc": "Restore 1 HP.",
                    "icon": "♥",
                    "icon_id": "heart_vial",
                    "bought": False,
                }
            )
            # Slot 1: one random perk
            chosen = random.sample(_available_perks(self.player), 1)
            for perk in chosen:
                dr.shop_items.append(
                    {
                        "kind": "perk",
                        "cost": perk_price,
                        "label": perk.name,
                        "desc": perk.desc,
                        "icon": perk.icon,
                        "icon_id": perk.id,
                        "perk": perk,
                        "bought": False,
                    }
                )
        self._shop_hovered = -1
        self.state = "SHOP"

    # ── Floor progression ─────────────────────────────────────────────────────
    def _next_floor(self) -> None:
        """Advance to the next floor, keeping player stats."""
        next_floor = self.dungeon.floor + 1
        self.dungeon = Dungeon(floor=next_floor)
        self.room_num = 1

        dr = self.dungeon.current
        px, py = dr.room.find_spawn_near_centre(float(C.PLAYER_RADIUS))
        # Preserve player position → teleport to new start; keep all other stats
        self.player.x = px
        self.player.y = py
        self.player.arrows.clear()

        self.enemies = _spawn_wave(dr.room, next_floor, self.room_num)
        self.enemy_projectiles = []
        self.coins = []
        self.chests = []
        self.burn_patches = []
        self._blur_clones = []
        self.camera = Camera()
        self._boss_hint_t = 0.0
        self._show_staircase = False
        self._staircase_t = 0.0
        self._ladder_ready = False
        self._void_flash_t = 0.0
        self._burn_dot_acc = 0.0

        # Relic per-floor effects
        if self.player.wardens_mark:
            self.player.hp = max(1, self.player.hp // 2)
        if self.player.curse_of_greed:
            self.player.coins = 0

        self.state = "PLAYING"

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
            "rooms": self._rooms_cleared_total,
            "coins": self._coins_collected_total,
            "time": round(elapsed, 1),
        }
        self._run_stats = score
        if _is_better(score, self._highscore):
            _save_highscore(score)
            self._highscore = score
            self._new_highscore = True
        else:
            self._new_highscore = False

    # ── Update ────────────────────────────────────────────────────────────────
    def update(self, dt: float) -> None:
        if self.state in ("MENU", "PAUSED", "CODEX", "ARENA_SELECT", "ENDLESS_SELECT"):
            return  # these states freeze all game logic
        self.camera.update(dt)
        if self._show_staircase:
            self._staircase_t += dt
        self._void_flash_t = max(0.0, self._void_flash_t - dt)
        if self.state == "PLAYING":
            self._update_playing(dt)
        elif self.state == "FLOOR_CLEAR":
            self._update_floor_clear(dt)
        elif self.state == "TRANSITIONING":
            self._update_transitioning(dt)
        elif self.state == "ARENA":
            self._update_arena(dt)
        elif self.state == "ENDLESS":
            self._update_endless(dt)
        # UPGRADE, DEAD, ARENA_WIN, ARENA_DEAD, ENDLESS_BETWEEN, ENDLESS_DEAD:
        # gameplay frozen — particles still tick
        self.particles.update(dt)

    def _update_playing(self, dt: float) -> None:
        dr = self._dr
        room = self._room

        # Track dash state BEFORE player.update so we can detect the start of a dash
        prev_px = self.player.x
        prev_py = self.player.y
        was_dashing = self.player._dashing

        self.player.update(dt, room, self.particles)
        if self.player.dead:
            self._finish_run()
            self.state = "DEAD"
            return

        # Temporal Blur — spawn 2 clones at dash-start position
        if self.player.temporal_blur and not was_dashing and self.player._dashing:
            for _ in range(2):
                self._blur_clones.append({"x": prev_px, "y": prev_py, "charges": 1})

        # Shrapnel Tips — spawn 3 mini-shrapnel per wall-hit arrow
        # _is_shrapnel flag prevents recursive chain: shrapnel hitting walls never spawn more shrapnel
        if self.player.shrapnel_tips:
            for wx, wy, wang in self.player._wall_hit_arrows:
                refl_base = math.atan2(-math.sin(wang), -math.cos(wang))
                for dang in (-0.52, 0.0, 0.52):  # ≈ ±30°
                    shr = Arrow(wx, wy, refl_base + dang, speed=450, damage=1, lifetime=0.30)
                    shr._is_shrapnel = True
                    self.player.arrows.append(shr)

        # Phase Cloak / Iron Lungs — dash-through effects
        if self.player._dashing:
            for e in self.enemies:
                if e.alive and (
                    (e.x - self.player.x) ** 2 + (e.y - self.player.y) ** 2 < (e.radius + self.player.radius) ** 2
                ):
                    if self.player.phase_cloak:
                        e._stun_t = max(e._stun_t, 0.8)
                    if self.player.iron_lungs:
                        e.take_hit(1, self.particles)
                        if not e.alive:
                            self._drop_coins(e)

        # ── Block locked doors ────────────────────────────────────────────────
        # Locked = room not cleared (all doors) OR leading to boss-room while
        # boss gate is up (that specific door only).
        # Only clamp inside the door opening; tile walls handle all other edges.
        ts = C.TILE_SIZE
        r = C.PLAYER_RADIUS
        margin = ts + r  # 32 + 12 = 44 px — natural wall-face stop distance
        ns_lo = (C.ROOM_TILE_W // 2 - 1) * ts - r  # 596 px  (N/S door x-span)
        ns_hi = (C.ROOM_TILE_W // 2 + 2) * ts + r  # 716 px
        ew_lo = (C.ROOM_TILE_H // 2 - 1) * ts - r  # 276 px  (E/W door y-span)
        ew_hi = (C.ROOM_TILE_H // 2 + 2) * ts + r  # 396 px
        p = self.player

        locked = set(room.doors) if not dr.cleared else (self._boss_locked_doors() & set(room.doors))
        if "N" in locked and p.y < margin and ns_lo < p.x < ns_hi:
            p.y = margin
            if dr.cleared:  # boss gate bump — show hint
                self._boss_hint_t = 2.5
                self._boss_hint_dir = "N"
        if "S" in locked and p.y > C.ROOM_PIXEL_H - margin and ns_lo < p.x < ns_hi:
            p.y = C.ROOM_PIXEL_H - margin
            if dr.cleared:
                self._boss_hint_t = 2.5
                self._boss_hint_dir = "S"
        if "W" in locked and p.x < margin and ew_lo < p.y < ew_hi:
            p.x = margin
            if dr.cleared:
                self._boss_hint_t = 2.5
                self._boss_hint_dir = "W"
        if "E" in locked and p.x > C.ROOM_PIXEL_W - margin and ew_lo < p.y < ew_hi:
            p.x = C.ROOM_PIXEL_W - margin
            if dr.cleared:
                self._boss_hint_t = 2.5
                self._boss_hint_dir = "E"

        # ── Void Sovereign: shrinking void field clamp (P2) ──────────────────
        for e in self.enemies:
            if getattr(e, "is_void_sovereign", False) and e.alive:
                vm = getattr(e, "_void_margin", 0.0)
                if vm > 0:
                    p.x = max(vm + p.radius, min(C.ROOM_PIXEL_W - vm - p.radius, p.x))
                    p.y = max(vm + p.radius, min(C.ROOM_PIXEL_H - vm - p.radius, p.y))
                break

        # Tick boss-gate hint timer
        self._boss_hint_t = max(0.0, self._boss_hint_t - dt)

        # ── Enemies ───────────────────────────────────────────────────────────
        for e in self.enemies:
            e.update(dt, self.player, room, self.particles, self.enemy_projectiles)

        # Drain minion-summon queues from boss enemies
        new_summons: list[Enemy] = []
        for e in self.enemies:
            q = getattr(e, "_summon_queue", None)
            if q:
                new_summons.extend(q)
                q.clear()
        self.enemies.extend(new_summons)

        # Drain Void Core pulse queue from player → piercing arrows
        for vx2, vy2, vangle in self.player._void_queue:
            vcore_arrow = Arrow(vx2, vy2, vangle, speed=280, damage=self.player.arrow_damage, lifetime=0.6)
            vcore_arrow.piercing = True
            self.player.arrows.append(vcore_arrow)
        self.player._void_queue.clear()

        # Drain MagmaSlug burn-patch queues → BurnPatch objects
        for e in self.enemies:
            pq = getattr(e, "_patch_queue", None)
            if pq:
                for px2, py2 in pq:
                    self.burn_patches.append(BurnPatch(px2, py2))
                pq.clear()

        # Drain VoidShrieker hit-shake and death-burst queues
        for e in self.enemies:
            if getattr(e, "_hit_shake", False):
                e._hit_shake = False  # type: ignore[attr-defined]
                self.camera.add_shake(4)
                self._void_flash_t = max(self._void_flash_t, 0.25)
            dps = getattr(e, "_death_projs", None)
            if dps:
                self.enemy_projectiles.extend(dps)
                dps.clear()

        # Steer homing projectiles toward player before advancing them
        for ep in self.enemy_projectiles:
            if getattr(ep, "homing", False):
                dx2 = self.player.x - ep.x
                dy2 = self.player.y - ep.y
                dist2 = math.hypot(dx2, dy2) or 1.0
                tx = dx2 / dist2
                ty = dy2 / dist2
                spd = math.hypot(ep.vx, ep.vy) or 1.0
                cx2 = ep.vx / spd
                cy2 = ep.vy / spd
                turn = math.radians(180.0 * dt)  # max turn per frame
                # Rotate current direction by up to `turn` radians toward target
                cross = cx2 * ty - cy2 * tx
                dot = cx2 * tx + cy2 * ty
                angle = math.atan2(cross, dot)
                angle = max(-turn, min(turn, angle))
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                ep.vx = (cx2 * cos_a - cy2 * sin_a) * spd
                ep.vy = (cx2 * sin_a + cy2 * cos_a) * spd

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
                    # Overcharged Quiver: every 4th arrow deals x3
                    if getattr(arrow, "_overcharged", False):
                        actual_dmg = arrow.damage * 3
                    if isinstance(enemy, CrystalTurret):
                        impact = math.atan2(arrow.y - enemy.y, arrow.x - enemy.x)
                        diff = math.atan2(
                            math.sin(impact - enemy._face_angle),
                            math.cos(impact - enemy._face_angle),
                        )
                        if abs(diff) < math.pi / 3:  # front ±60° — immune
                            actual_dmg = 0
                        elif abs(diff) > math.pi * 2 / 3:  # back 120° — double
                            actual_dmg = max(actual_dmg, arrow.damage * 2)
                    if actual_dmg > 0:
                        # Hunter's Mark: first enemy hit per room takes x3
                        if self.player.hunter_mark and not self.player._hunter_mark_used:
                            actual_dmg *= 3
                            self.player._hunter_mark_used = True
                        enemy.take_hit(actual_dmg, self.particles)
                        # Venom Gland: apply poison to enemy
                        if self.player.arrow_poison:
                            enemy._poison_t = max(enemy._poison_t, 4.0)
                    self.camera.add_shake(3)
                    if getattr(enemy, "phase2_just_triggered", False):
                        enemy.phase2_just_triggered = False
                        self.camera.add_shake(getattr(enemy, "_phase2_shake", 14))
                    if not enemy.alive:
                        self._drop_coins(enemy)
                        # Echoing Shot: spawn reflected arrow aimed at nearest survivor
                        if self.player.echoing_shot:
                            living = [e for e in self.enemies if e.alive and e is not enemy]
                            if living:
                                near = min(living, key=lambda e: (e.x - enemy.x) ** 2 + (e.y - enemy.y) ** 2)
                                if (near.x - enemy.x) ** 2 + (near.y - enemy.y) ** 2 < 300**2:
                                    ea = math.atan2(near.y - enemy.y, near.x - enemy.x)
                                    self.player.arrows.append(
                                        Arrow(
                                            enemy.x,
                                            enemy.y,
                                            ea,
                                            speed=self.player.arrow_speed,
                                            damage=self.player.arrow_damage,
                                            piercing=self.player.piercing,
                                        )
                                    )
                        # Leech Stone: +1 HP every 50 kills
                        if self.player.leech_stone:
                            self.player._leech_kills += 1
                            if self.player._leech_kills >= 50:
                                self.player._leech_kills = 0
                                if self.player.hp < self.player.max_hp:
                                    self.player.hp += 1
                        # Bloodlust: +10 % speed per kill, stacks x3, 3 s timer
                        if self.player.bloodlust:
                            self.player._bloodlust_stacks = min(3, self.player._bloodlust_stacks + 1)
                            self.player._bloodlust_t = 3.0

        for ep in self.enemy_projectiles:
            if not ep.alive:
                continue
            # Temporal Blur clones intercept projectiles
            absorbed = False
            for clone in self._blur_clones:
                if (ep.x - clone["x"]) ** 2 + (ep.y - clone["y"]) ** 2 < 14**2:
                    ep.alive = False
                    clone["charges"] -= 1
                    self.particles.emit_hit(ep.x, ep.y, 0)
                    absorbed = True
                    break
            if absorbed:
                continue
            if (ep.x - self.player.x) ** 2 + (ep.y - self.player.y) ** 2 < (C.PLAYER_RADIUS + 6) ** 2:
                ep.alive = False
                if self.player.take_damage(ep.damage):
                    self.particles.emit_player_hurt(self.player.x, self.player.y)
                    self.camera.add_shake(6)
                    # Abyssal Leech tendril healing: boss heals 3 HP when tendril connects
                    leech = getattr(ep, "leech_owner", None)
                    if leech is not None and leech.alive:
                        leech.hp = min(leech.max_hp, leech.hp + 3)
                    # Spiked Shell: deal 2 dmg to all enemies within 80 px
                    if self.player.spiked_shell:
                        for e in self.enemies:
                            if e.alive and ((e.x - self.player.x) ** 2 + (e.y - self.player.y) ** 2 < 80**2):
                                e.take_hit(2, self.particles)
                                if not e.alive:
                                    self._drop_coins(e)

        # Prune expired blur clones
        self._blur_clones = [c for c in self._blur_clones if c["charges"] > 0]

        # Drain any VoidShrieker death-burst projectiles triggered by arrow kills
        for e in self.enemies:
            dps = getattr(e, "_death_projs", None)
            if dps:
                self.enemy_projectiles.extend(dps)
                dps.clear()

        self.enemies = [e for e in self.enemies if e.alive]
        self.enemy_projectiles = [ep for ep in self.enemy_projectiles if ep.alive]

        # ── Coins ─────────────────────────────────────────────────────────────
        for coin in self.coins:
            if coin.update(dt, self.player, self.particles):
                sounds.play("coin")
                self._coins_collected_total += 1
                # Coin-Fed Heart: +1 HP every 100 coins (can't over-heal if Petrified Heart)
                if self.player.coin_fed_heart:
                    self.player._coin_fed_acc += 1
                    if self.player._coin_fed_acc >= 100:
                        self.player._coin_fed_acc = 0
                        if self.player.hp < self.player.max_hp and not self.player.petrified_heart:
                            self.player.hp += 1
        self.coins = [c for c in self.coins if not c.collected]

        # ── Burn patches (MagmaSlug DoT floor hazard) ─────────────────────────
        _burn_dot_acc = getattr(self, "_burn_dot_acc", 0.0)
        _burn_overlap = False
        for patch in self.burn_patches:
            if patch.update(dt, self.player):
                _burn_overlap = True
        if _burn_overlap:
            _burn_dot_acc += dt
            if _burn_dot_acc >= 1.0:
                _burn_dot_acc -= 1.0
                if self.player.take_damage(1):
                    self.particles.emit_player_hurt(self.player.x, self.player.y)
                    self.camera.add_shake(4)
        else:
            _burn_dot_acc = max(0.0, _burn_dot_acc - dt * 0.5)  # decay accumulator when clear
        self._burn_dot_acc = _burn_dot_acc
        self.burn_patches = [bp for bp in self.burn_patches if bp.alive]

        # ── Fungal Matriarch passive: spore aura 0.5 HP/s within 80 px ────────
        _mat_aura_acc = getattr(self, "_mat_aura_acc", 0.0)
        _mat_overlap = False
        for e in self.enemies:
            if getattr(e, "_spore_cloud_passive", False) and e.alive:
                if (self.player.x - e.x) ** 2 + (self.player.y - e.y) ** 2 < 80**2:
                    _mat_overlap = True
                break
        if _mat_overlap:
            _mat_aura_acc += dt * 0.5
            if _mat_aura_acc >= 1.0:
                _mat_aura_acc -= 1.0
                if self.player.take_damage(1):
                    self.particles.emit_player_hurt(self.player.x, self.player.y)
                    self.camera.add_shake(3)
        else:
            _mat_aura_acc = max(0.0, _mat_aura_acc - dt * 0.3)
        self._mat_aura_acc = _mat_aura_acc

        # ── Chests ────────────────────────────────────────────────────────────
        for chest in self.chests:
            if chest.update(dt, self.player):
                self._upgrade_perks = chest.perks
                self._upgrade_hovered = -1
                self._upgrade_open_ms = pygame.time.get_ticks()
                self.chests = [c for c in self.chests if not c.opened]
                self.state = "UPGRADE"
                return
        self.chests = [c for c in self.chests if not c.opened]

        # ── Ladder descent (after relic pick, player walks back to staircase) ──
        if self._ladder_ready and dr.is_boss and self._show_staircase:
            dx = self.player.x - self._staircase_x
            dy = self.player.y - self._staircase_y
            if dx * dx + dy * dy < 40.0**2:
                self._next_floor()
                return

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
                    self._staircase_x = sx
                    self._staircase_y = sy
                    self._staircase_t = 0.0
                    self._show_staircase = True
                    self.state = "FLOOR_CLEAR"
                return
            if not dr.is_start and not dr.is_shop and random.random() < 0.5:
                # Normal combat room — 50 % chance to spawn a mossy chest
                cx2, cy2 = room.find_spawn_near_centre(28.0)
                self.chests.append(Chest(cx2, cy2, random.sample(_available_perks(self.player), 3)))

        # ── Door-exit detection (only when cleared) ────────────────────────────
        if dr.cleared:
            self._check_door_exit()

    def _update_floor_clear(self, dt: float) -> None:
        """Player can move freely during the floor-clear overlay; walking into
        the staircase (or pressing Space) opens the relic-selection screen."""
        self.player.update(dt, self._room, self.particles)
        if self._show_staircase:
            dx = self.player.x - self._staircase_x
            dy = self.player.y - self._staircase_y
            if dx * dx + dy * dy < 40.0**2:
                self._start_relic_selection()

    def _check_door_exit(self) -> None:
        p = self.player
        margin = C.TILE_SIZE * 1.6
        ts = C.TILE_SIZE
        r = C.PLAYER_RADIUS

        # The door opening spans 3 tiles centred on the room midpoint.
        # Player must actually be inside that opening (laterally) to exit —
        # otherwise pressing against any wall on the correct side would trigger.
        #   N/S doors: cols cx-1..cx+1  → x ∈ [608, 704]  (plus one radius slack)
        #   E/W doors: rows cy-1..cy+1  → y ∈ [288, 384]
        ns_lo = (C.ROOM_TILE_W // 2 - 1) * ts - r  # 596 px
        ns_hi = (C.ROOM_TILE_W // 2 + 2) * ts + r  # 716 px
        ew_lo = (C.ROOM_TILE_H // 2 - 1) * ts - r  # 276 px
        ew_hi = (C.ROOM_TILE_H // 2 + 2) * ts + r  # 396 px

        boss_locked = self._boss_locked_doors()
        for d in self._dr.connections:
            if d in boss_locked:
                continue  # boss gate still up
            if d == "N" and p.y < margin and ns_lo < p.x < ns_hi:
                self._start_transition(d)
                return
            if d == "S" and p.y > C.ROOM_PIXEL_H - margin and ns_lo < p.x < ns_hi:
                self._start_transition(d)
                return
            if d == "W" and p.x < margin and ew_lo < p.y < ew_hi:
                self._start_transition(d)
                return
            if d == "E" and p.x > C.ROOM_PIXEL_W - margin and ew_lo < p.y < ew_hi:
                self._start_transition(d)
                return

    # ── Room transition ───────────────────────────────────────────────────────
    def _start_transition(self, direction: str) -> None:
        self.camera._shake = 0.0  # freeze shake during pan
        self._trans_wdx = float(_WORLD_DX[direction])
        self._trans_wdy = float(_WORLD_DY[direction])
        self._trans_t = 0.0
        self._trans_next = self._dr.connections[direction]
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
        t = self._trans_t
        ease = t * t * (3.0 - 2.0 * t)  # smooth-step
        self.camera.offset.x = self._trans_wdx * ease
        self.camera.offset.y = self._trans_wdy * ease
        if self._trans_t >= 1.0:
            self._commit_transition()

    def _commit_transition(self) -> None:
        assert self._trans_next is not None
        next_dr = self._trans_next
        if not next_dr.visited:  # only count first-time entries
            self.room_num += 1
        next_dr.visited = True
        self.dungeon.current = next_dr
        self.chests.clear()  # chests belong to the room we just left
        self.burn_patches.clear()  # burn patches belong to the room we just left
        self._blur_clones.clear()  # clones don't carry across rooms

        # Convert player from world-space back to local room coords
        self.player.x -= self._trans_wdx
        self.player.y -= self._trans_wdy

        # Relic per-room resets
        if self.player.ancient_sigil:
            self.player._iframes = max(self.player._iframes, 1.0)
        if self.player.bone_buckler:
            self.player.block_charge = 1
        self.player._hunter_mark_used = False

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
                self._trans_next = None
                self._open_shop(next_dr)
                return
            if next_dr.is_boss:
                self.enemies = _spawn_boss(next_dr.room, self.dungeon.floor)
                self.coins.clear()
            else:
                ex = (self.player.x, self.player.y)
                if self.dungeon.floor >= 2 and random.random() < 0.20:
                    self.enemies = _pack_wave(next_dr.room, self.dungeon.floor, exclude_pos=ex)
                else:
                    self.enemies = _spawn_wave(next_dr.room, self.dungeon.floor, self.room_num, exclude_pos=ex)
                self.coins.clear()
        else:
            self.enemies = []
            # Re-entering a shop room: re-open the shop overlay
            if next_dr.is_shop:
                self._trans_old_room = None
                self._trans_next = None
                self._open_shop(next_dr)
                return

        self._trans_old_room = None
        self._trans_next = None
        # Entry grace period — 0.5 s iframes so the player can orient after transition
        self.player._iframes = max(self.player._iframes, 0.5)
        self.state = "PLAYING"

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _drop_coins(self, enemy: Enemy) -> None:
        n = enemy.coin_drop * (2 if self.player.curse_of_greed else 1)
        for _ in range(n):
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
            ui.draw_menu(self.screen, self._highscore, hovered=self._menu_hovered)
            return

        if self.state == "CODEX":
            ui.draw_codex(self.screen, self._codex_tab, self._codex_scroll)
            return

        if self.state == "ARENA_SELECT":
            ui.draw_arena_select(
                self.screen, _ARENA_ENTRIES, self._arena_selected, self._arena_count, focus=self._arena_focus
            )
            return

        if self.state == "ENDLESS_SELECT":
            ui.draw_endless_select(self.screen, self._endless_select_wave)
            return

        if self.state == "TRANSITIONING":
            self._draw_transitioning()
        else:
            self._draw_playing()

        # ── Boss HP bar ───────────────────────────────────────────────────────
        _arena_states = ("ARENA", "ARENA_WIN", "ARENA_DEAD")
        _endless_states = ("ENDLESS", "ENDLESS_BETWEEN", "ENDLESS_DEAD")
        show_boss_hp = (
            (self.state == "PLAYING" and self._dr.is_boss)
            or self.state in _arena_states
            or self.state in _endless_states
        )
        if show_boss_hp:
            boss_e = next(
                (e for e in self.enemies if getattr(e, "is_boss_enemy", False)),
                None,
            )
            if boss_e is not None:
                ui.draw_boss_hpbar(
                    self.screen,
                    boss_e.boss_name,
                    boss_e.hp,
                    boss_e.max_hp,
                    phase2=getattr(boss_e, "_phase2", False),
                )

        # ── HUD ───────────────────────────────────────────────────────────────
        if self.state in _arena_states:
            entry = _ARENA_ENTRIES[self._arena_selected]
            label = f"⚔ {entry['name']} ×{self._arena_count}"
            ui.draw_hud(
                self.screen,
                self.player,
                enemies_left=len(self.enemies),
                mode_label=label,
            )
        elif self.state in _endless_states:
            w = self._endless_wave
            boss_marker = " ⚔ BOSS" if w % 5 == 0 else ""
            label = f"∞ Wave {w}{boss_marker}"
            ui.draw_hud(
                self.screen,
                self.player,
                enemies_left=len(self.enemies),
                mode_label=label,
            )
        else:
            ui.draw_hud(
                self.screen,
                self.player,
                floor_num=self.dungeon.floor,
                room_num=self.room_num,
                enemies_left=len(self.enemies),
                debug=config.DEBUG,
            )

        # ── Minimap (not shown in arena or endless) ───────────────────────────
        if self.state not in _arena_states and self.state not in _endless_states:
            ui.draw_minimap(self.screen, self.dungeon)

        # ── State-specific overlays ───────────────────────────────────────────
        if self.state == "DEAD":
            ui.draw_death_screen(self.screen, self._run_stats, self._new_highscore, self._highscore)
        elif self.state == "VICTORY":
            ui.draw_victory(self.screen, self._run_stats, self._new_highscore)
        elif self.state == "FLOOR_CLEAR":
            ui.draw_floor_clear(self.screen, self.dungeon.floor)
        elif self.state == "UPGRADE":
            ui.draw_upgrade_screen(self.screen, self._upgrade_perks, self._upgrade_hovered)
        elif self.state == "RELIC":
            ui.draw_relic_screen(self.screen, self._relic_choices, self._relic_hovered)
        elif self.state == "SHOP":
            ui.draw_shop_screen(self.screen, self._dr.shop_items, self.player, self._shop_hovered)
        elif self.state in ("ARENA_WIN", "ARENA_DEAD"):
            entry = _ARENA_ENTRIES[self._arena_selected]
            ui.draw_arena_result(
                self.screen,
                won=(self.state == "ARENA_WIN"),
                enemy_name=entry["name"],
                count=self._arena_count,
            )
        elif self.state == "ENDLESS_BETWEEN":
            ui.draw_endless_between(
                self.screen,
                self._endless_wave_just_completed,
                self._endless_between_reward_lines,
                self._endless_between_next_action,
            )
        elif self.state == "ENDLESS_DEAD":
            ui.draw_endless_dead(self.screen, self._endless_wave)
        elif self.state == "PAUSED":
            # Re-draw whichever overlay was active before pausing, then the pause screen on top
            if self._pre_pause_state == "UPGRADE":
                ui.draw_upgrade_screen(self.screen, self._upgrade_perks, self._upgrade_hovered)
            elif self._pre_pause_state == "RELIC":
                ui.draw_relic_screen(self.screen, self._relic_choices, self._relic_hovered)
            elif self._pre_pause_state == "SHOP":
                ui.draw_shop_screen(self.screen, self._dr.shop_items, self.player, self._shop_hovered)
            elif self._pre_pause_state == "FLOOR_CLEAR":
                ui.draw_floor_clear(self.screen, self.dungeon.floor)
            elif self._pre_pause_state == "ENDLESS_BETWEEN":
                ui.draw_endless_between(
                    self.screen,
                    self._endless_wave_just_completed,
                    self._endless_between_reward_lines,
                    self._endless_between_next_action,
                )
            ui.draw_pause_screen(self.screen)

    def _draw_playing(self) -> None:
        dr = self._dr
        room = self._room
        cam = self.camera

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
                self.screen,
                self._boss_hint_dir,
                self._boss_hint_t,
                cam.offset.x,
                cam.offset.y,
            )

        for patch in self.burn_patches:
            patch.draw(self.screen, cam)
        # Temporal Blur afterimage clones
        for clone in self._blur_clones:
            cx2, cy2 = cam.apply_pos(clone["x"], clone["y"])
            r = C.PLAYER_RADIUS + 2
            ghost = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(ghost, (140, 190, 255, 80), (r, r), r)
            pygame.draw.circle(ghost, (200, 230, 255, 120), (r, r), r, 2)
            self.screen.blit(ghost, (round(cx2) - r, round(cy2) - r))
        for coin in self.coins:
            coin.draw(self.screen, cam)
        for chest in self.chests:
            chest.draw(self.screen, cam)
        if self._show_staircase and dr.is_boss:
            ui.draw_staircase(
                self.screen, cam, self._staircase_x, self._staircase_y, self._staircase_t, self._ladder_ready
            )
        for e in self.enemies:
            e.draw(self.screen, cam)
        for ep in self.enemy_projectiles:
            ep.draw(self.screen, cam)
        self.player.draw(self.screen, cam)
        self.particles.draw(self.screen, cam.offset.x, cam.offset.y)

        # Void Sovereign: dark void border (P2 shrinking arena)
        for e in self.enemies:
            if getattr(e, "is_void_sovereign", False) and e.alive:
                vm = round(getattr(e, "_void_margin", 0.0))
                if vm > 0:
                    alpha = min(210, 25 + round(vm / C.SOVEREIGN_VOID_MAX * 180))
                    vborder = pygame.Surface((C.SCREEN_W, C.PLAYFIELD_H), pygame.SRCALPHA)
                    bcol = (5, 0, 20, alpha)
                    pygame.draw.rect(vborder, bcol, (0, 0, C.SCREEN_W, vm))
                    pygame.draw.rect(vborder, bcol, (0, C.PLAYFIELD_H - vm, C.SCREEN_W, vm))
                    pygame.draw.rect(vborder, bcol, (0, vm, vm, C.PLAYFIELD_H - 2 * vm))
                    pygame.draw.rect(vborder, bcol, (C.SCREEN_W - vm, vm, vm, C.PLAYFIELD_H - 2 * vm))
                    self.screen.blit(vborder, (0, 0))
                break

        # Void flash vignette (VoidShrieker hit/attack feedback)
        if self._void_flash_t > 0:
            alpha = int(self._void_flash_t / 0.25 * 130)
            vignette = pygame.Surface((C.SCREEN_W, C.PLAYFIELD_H), pygame.SRCALPHA)
            edge = 40  # border thickness
            border_col = (20, 0, 45, min(255, alpha))
            pygame.draw.rect(vignette, border_col, (0, 0, C.SCREEN_W, edge))
            pygame.draw.rect(vignette, border_col, (0, C.PLAYFIELD_H - edge, C.SCREEN_W, edge))
            pygame.draw.rect(vignette, border_col, (0, edge, edge, C.PLAYFIELD_H - 2 * edge))
            pygame.draw.rect(vignette, border_col, (C.SCREEN_W - edge, edge, edge, C.PLAYFIELD_H - 2 * edge))
            self.screen.blit(vignette, (0, 0))

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
