"""Dungeon — graph of DungeonRoom nodes for one floor.

Generation
----------
DFS random walk produces a tree of 5–7 rooms.  Each node records which
cardinal directions it connects to; those door sets are handed straight
to Room so tile openings are cut at construction time.

The room furthest (BFS distance) from the start is marked as_boss.
"""

from __future__ import annotations

import random
from collections import deque

from rooms import TEMPLATES, Room

# ── Direction helpers ─────────────────────────────────────────────────────────
DIRS: dict[str, tuple[int, int]] = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}
OPP: dict[str, str] = {"N": "S", "S": "N", "E": "W", "W": "E"}


def _step(pos: tuple[int, int], d: str) -> tuple[int, int]:
    dx, dy = DIRS[d]
    return (pos[0] + dx, pos[1] + dy)


# ── DungeonRoom node ──────────────────────────────────────────────────────────


class DungeonRoom:
    """One node in the dungeon graph."""

    def __init__(self, gx: int, gy: int, room: Room) -> None:
        self.gx = gx
        self.gy = gy
        self.room = room
        self.connections: dict[str, DungeonRoom] = {}
        self.visited: bool = False
        self.cleared: bool = False
        self.is_start: bool = False
        self.is_boss: bool = False
        self.is_shop: bool = False
        # Shop items are set by game.py on first entry; stored here so they
        # persist if the player re-enters the room.  Each entry is a plain dict:
        #   {"kind": "hp"|"perk", "cost": int, "perk": Perk|None, "bought": bool}
        self.shop_items: list = []

    def __repr__(self) -> str:
        tags = []
        if self.is_start:
            tags.append("START")
        if self.is_boss:
            tags.append("BOSS")
        if self.is_shop:
            tags.append("SHOP")
        if self.cleared:
            tags.append("cleared")
        return f"DungeonRoom({self.gx},{self.gy} {' '.join(tags)} doors={set(self.connections)})"


# ── Dungeon ───────────────────────────────────────────────────────────────────


class Dungeon:
    """Generates and holds the room graph for one floor."""

    def __init__(self, floor: int = 1) -> None:
        self.floor = floor
        self.rooms: dict[tuple[int, int], DungeonRoom] = {}
        self.current: DungeonRoom
        self._generate()

    # ── Generation ────────────────────────────────────────────────────────────
    def _generate(self) -> None:
        target = random.randint(max(5, self.floor + 4), min(14, self.floor + 6))

        # ── Phase 1: build the door-connection graph (DFS random walk) ────────
        # pos_doors maps grid position → set of outgoing direction strings
        pos_doors: dict[tuple[int, int], set[str]] = {(0, 0): set()}
        stack: list[tuple[int, int]] = [(0, 0)]

        while len(pos_doors) < target:
            if not stack:
                break
            pos = stack[-1]
            free = [d for d in DIRS if _step(pos, d) not in pos_doors]
            if not free:
                stack.pop()
                continue
            d = random.choice(free)
            npos = _step(pos, d)
            pos_doors[pos].add(d)
            pos_doors[npos] = {OPP[d]}
            stack.append(npos)

        # ── Phase 2: build Room objects with correct door openings ─────────────
        # Deeper floors unlock later (underground-ruin) templates.
        # Floor 1 → templates 0–4; each additional floor unlocks 1 more, up to all 9.
        n_tmpl = min(len(TEMPLATES), 5 + min(4, self.floor - 1))
        templates = list(range(n_tmpl))
        random.shuffle(templates)
        for i, (pos, doors) in enumerate(pos_doors.items()):
            tmpl = templates[i % len(templates)]
            room = Room(template_idx=tmpl, doors=doors)
            dr = DungeonRoom(pos[0], pos[1], room)
            dr.is_start = pos == (0, 0)
            self.rooms[pos] = dr

        # ── Phase 3: link DungeonRoom cross-references ─────────────────────────
        for pos, doors in pos_doors.items():
            for d in doors:
                npos = _step(pos, d)
                if npos in self.rooms:
                    self.rooms[pos].connections[d] = self.rooms[npos]

        # ── Phase 4: mark special rooms ───────────────────────────────────────
        start = self.rooms[(0, 0)]
        start.visited = True
        self.current = start

        boss_pos = self._bfs_furthest()
        self.rooms[boss_pos].is_boss = True

        # Mark one non-start, non-boss room as the shop.
        # Prefer a room at BFS depth 1 or 2 to keep it reachable early.
        candidates = [pos for pos in self.rooms if pos != (0, 0) and pos != boss_pos]
        if candidates:
            self.rooms[random.choice(candidates)].is_shop = True

    def _bfs_furthest(self) -> tuple[int, int]:
        """Return the grid position with greatest BFS depth from (0, 0).

        Uses the actual door-connection graph (not raw grid adjacency) so that
        rooms which are grid-neighbours but have no door between them are never
        treated as reachable from each other.  The old DIRS loop could produce
        a shortcut path that made a node appear closer than its real graph
        distance, causing the wrong room to be selected as the boss and
        sometimes trapping the shop behind the boss gate with no other exit.
        """
        dist: dict[tuple[int, int], int] = {(0, 0): 0}
        q: deque[tuple[int, int]] = deque([(0, 0)])
        farthest = (0, 0)
        while q:
            pos = q.popleft()
            if dist[pos] > dist[farthest]:
                farthest = pos
            # Only follow rooms that are actually connected by a door.
            for d in self.rooms[pos].connections:
                npos = _step(pos, d)
                if npos not in dist:
                    dist[npos] = dist[pos] + 1
                    q.append(npos)
        return farthest
