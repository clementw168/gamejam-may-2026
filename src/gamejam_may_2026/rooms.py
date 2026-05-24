"""Room — tile grid, pre-rendered surface, wall collision, templates."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pygame

from gamejam_may_2026 import constants as C

if TYPE_CHECKING:
    from gamejam_may_2026.camera import Camera

# ── Tile helpers ──────────────────────────────────────────────────────────────


def _empty() -> list[list[int]]:
    return [[C.TILE_FLOOR] * C.ROOM_TILE_W for _ in range(C.ROOM_TILE_H)]


def _border(t: list[list[int]]) -> None:
    for c in range(C.ROOM_TILE_W):
        t[0][c] = C.TILE_WALL
        t[C.ROOM_TILE_H - 1][c] = C.TILE_WALL
    for r in range(C.ROOM_TILE_H):
        t[r][0] = C.TILE_WALL
        t[r][C.ROOM_TILE_W - 1] = C.TILE_WALL


def _rect(t: list[list[int]], row: int, col: int, h: int, w: int) -> None:
    for dr in range(h):
        for dc in range(w):
            r2, c2 = row + dr, col + dc
            if 0 <= r2 < C.ROOM_TILE_H and 0 <= c2 < C.ROOM_TILE_W:
                t[r2][c2] = C.TILE_WALL


# ── Template builders ─────────────────────────────────────────────────────────


def _template_arena() -> list[list[int]]:
    """Open arena with 2×3 corner pillars and a small centre block."""
    t = _empty()
    _border(t)
    _rect(t, 2, 2, 2, 3)  # TL
    _rect(t, 2, 35, 2, 3)  # TR
    _rect(t, 16, 2, 2, 3)  # BL
    _rect(t, 16, 35, 2, 3)  # BR
    _rect(t, 9, 18, 2, 4)  # centre rock
    return t


def _template_columns() -> list[list[int]]:
    """Six slender columns arranged symmetrically."""
    t = _empty()
    _border(t)
    for col in (9, 20, 31):
        _rect(t, 4, col, 4, 1)
        _rect(t, 12, col, 4, 1)
    return t


def _template_lshapes() -> list[list[int]]:
    """L-shaped rubble in the four inner corners."""
    t = _empty()
    _border(t)
    # TL L
    _rect(t, 2, 2, 1, 5)
    _rect(t, 2, 2, 4, 1)
    # TR L
    _rect(t, 2, 33, 1, 5)
    _rect(t, 2, 37, 4, 1)
    # BL L
    _rect(t, 17, 2, 1, 5)
    _rect(t, 14, 2, 4, 1)
    # BR L
    _rect(t, 17, 33, 1, 5)
    _rect(t, 14, 37, 4, 1)
    return t


def _template_maze() -> list[list[int]]:
    """Two horizontal wall segments creating a corridor feel."""
    t = _empty()
    _border(t)
    _rect(t, 5, 8, 1, 14)
    _rect(t, 14, 18, 1, 14)
    # Gap in each wall (3 tiles)
    for c in range(14, 17):
        t[5][c] = C.TILE_FLOOR
    for c in range(22, 25):
        t[14][c] = C.TILE_FLOOR
    return t


def _template_island() -> list[list[int]]:
    """Large impassable island in the centre with side cover."""
    t = _empty()
    _border(t)
    _rect(t, 7, 16, 6, 8)  # centre island
    # Side rocks
    _rect(t, 4, 5, 2, 2)
    _rect(t, 4, 33, 2, 2)
    _rect(t, 14, 5, 2, 2)
    _rect(t, 14, 33, 2, 2)
    return t


def _template_corridor() -> list[list[int]]:
    """Two N–S side corridors separated by vertical dividers with 3-tile choke passages."""
    t = _empty()
    _border(t)
    # Left divider — gap at rows 9–11 (aligns with E/W door height)
    _rect(t, 2, 12, 7, 2)  # rows 2-8
    _rect(t, 12, 12, 7, 2)  # rows 12-18
    # Right divider — same gap
    _rect(t, 2, 26, 7, 2)  # rows 2-8
    _rect(t, 12, 26, 7, 2)  # rows 12-18
    return t


def _template_pit_ring() -> list[list[int]]:
    """Large impassable central pit with a ring walkway around the perimeter."""
    t = _empty()
    _border(t)
    _rect(t, 5, 14, 10, 12)  # central pit: rows 5-14, cols 14-25
    return t


def _template_rubble_heap() -> list[list[int]]:
    """Asymmetric scatter of wall blocks — deliberately no axis of symmetry."""
    t = _empty()
    _border(t)
    # Top-left quadrant
    _rect(t, 3, 4, 1, 3)
    _rect(t, 5, 9, 2, 1)
    _rect(t, 7, 5, 1, 4)
    # Top-right quadrant
    _rect(t, 2, 30, 2, 2)
    _rect(t, 6, 33, 1, 3)
    _rect(t, 4, 25, 1, 2)
    # Bottom-left quadrant
    _rect(t, 13, 3, 2, 2)
    _rect(t, 15, 8, 1, 3)
    _rect(t, 16, 4, 1, 2)
    # Bottom-right quadrant
    _rect(t, 12, 31, 1, 4)
    _rect(t, 14, 28, 2, 2)
    _rect(t, 16, 33, 2, 1)
    # Centre-adjacent pieces (away from boss spawn zone)
    _rect(t, 4, 15, 1, 2)
    _rect(t, 14, 23, 1, 2)
    return t


def _template_pillars_dense() -> list[list[int]]:
    """Twelve single-tile pillars breaking lines of sight across the room."""
    t = _empty()
    _border(t)
    # Top row of pillars
    _rect(t, 4, 7, 1, 1)
    _rect(t, 4, 14, 1, 1)
    _rect(t, 5, 25, 1, 1)  # slight row offset for visual interest
    _rect(t, 4, 32, 1, 1)
    # Middle row (shifted columns, avoid door rows 9-11 near border)
    _rect(t, 10, 6, 1, 1)
    _rect(t, 10, 16, 1, 1)
    _rect(t, 10, 23, 1, 1)
    _rect(t, 10, 33, 1, 1)
    # Bottom row
    _rect(t, 15, 8, 1, 1)
    _rect(t, 15, 15, 1, 1)
    _rect(t, 14, 24, 1, 1)
    _rect(t, 15, 31, 1, 1)
    return t


TEMPLATES = [
    _template_arena,  # 0 — all floors
    _template_columns,  # 1 — all floors
    _template_lshapes,  # 2 — all floors
    _template_maze,  # 3 — all floors
    _template_island,  # 4 — all floors
    _template_corridor,  # 5 — floor 2+
    _template_pit_ring,  # 6 — floor 3+
    _template_rubble_heap,  # 7 — floor 4+
    _template_pillars_dense,  # 8 — floor 5+
]

# ── Tile renderer ─────────────────────────────────────────────────────────────


def _render_tiles(tiles: list[list[int]]) -> pygame.Surface:
    surf = pygame.Surface((C.ROOM_PIXEL_W, C.ROOM_PIXEL_H))
    surf.fill(C.C_BG)
    ts = C.TILE_SIZE

    for r in range(C.ROOM_TILE_H):
        for c in range(C.ROOM_TILE_W):
            x, y = c * ts, r * ts
            tile = tiles[r][c]

            if tile == C.TILE_FLOOR:
                base = C.C_FLOOR if (r + c) % 2 == 0 else C.C_FLOOR_ALT
                surf.fill(base, (x, y, ts, ts))
                # Subtle darker patch using stable pseudo-random
                rng = (r * 7919 + c * 6571) % 100
                if rng < 18:
                    dark = (max(0, base[0] - 10), max(0, base[1] - 14), max(0, base[2] - 10))
                    surf.fill(dark, (x + ts // 4, y + ts // 4, ts // 2, ts // 2))
                # Tile edge line
                edge = (max(0, base[0] - 6), max(0, base[1] - 9), max(0, base[2] - 6))
                pygame.draw.rect(surf, edge, (x, y, ts, ts), 1)

            else:  # WALL
                surf.fill(C.C_WALL, (x, y, ts, ts))
                # Top + left highlight
                pygame.draw.line(surf, C.C_WALL_LIT, (x, y), (x + ts - 1, y), 2)
                pygame.draw.line(surf, C.C_WALL_LIT, (x, y), (x, y + ts - 1), 2)
                # Bottom + right shadow
                pygame.draw.line(surf, C.C_WALL_DARK, (x, y + ts - 1), (x + ts - 1, y + ts - 1), 1)
                pygame.draw.line(surf, C.C_WALL_DARK, (x + ts - 1, y), (x + ts - 1, y + ts - 1), 1)
                # Pseudo-random stone detail
                rng = (r * 7919 + c * 6571) % 100
                if rng < 35:
                    dark2 = (max(0, C.C_WALL[0] - 14), max(0, C.C_WALL[1] - 10), max(0, C.C_WALL[2] - 8))
                    surf.fill(dark2, (x + 5, y + 5, ts - 10, ts - 10))

    return surf


# ── Door helper ───────────────────────────────────────────────────────────────


def _cut_doors(tiles: list[list[int]], doors: set[str]) -> None:
    """Cut 3-tile-wide openings through the border walls for each direction."""
    cx = C.ROOM_TILE_W // 2  # col 20  — centre column
    cy = C.ROOM_TILE_H // 2  # row 10  — centre row
    # Door spans columns cx-1 … cx+1  (or rows cy-1 … cy+1 for E/W)
    # Opening is 2 tiles deep to match the 2-tile-thick visual wall.
    if "N" in doors:
        for r in range(2):
            for dc in (-1, 0, 1):
                tiles[r][cx + dc] = C.TILE_FLOOR
    if "S" in doors:
        for r in range(C.ROOM_TILE_H - 2, C.ROOM_TILE_H):
            for dc in (-1, 0, 1):
                tiles[r][cx + dc] = C.TILE_FLOOR
    if "W" in doors:
        for c in range(2):
            for dr in (-1, 0, 1):
                tiles[cy + dr][c] = C.TILE_FLOOR
    if "E" in doors:
        for c in range(C.ROOM_TILE_W - 2, C.ROOM_TILE_W):
            for dr in (-1, 0, 1):
                tiles[cy + dr][c] = C.TILE_FLOOR


# ── Room class ────────────────────────────────────────────────────────────────


class Room:
    def __init__(
        self,
        template_idx: int = 0,
        doors: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        self.doors: set[str] = set(doors)
        builder = TEMPLATES[template_idx % len(TEMPLATES)]
        self.tiles: list[list[int]] = builder()
        if self.doors:
            _cut_doors(self.tiles, self.doors)
        self.surface: pygame.Surface = _render_tiles(self.tiles)
        self.cleared = False

    # ── Collision ──────────────────────────────────────────────────────────────
    def is_circle_walkable(self, cx: float, cy: float, radius: float) -> bool:
        """Return True if a circle at (cx, cy) with *radius* doesn't overlap a wall."""
        tile_l = max(0, int((cx - radius) // C.TILE_SIZE))
        tile_r = min(C.ROOM_TILE_W - 1, int((cx + radius) // C.TILE_SIZE))
        tile_t = max(0, int((cy - radius) // C.TILE_SIZE))
        tile_b = min(C.ROOM_TILE_H - 1, int((cy + radius) // C.TILE_SIZE))

        for r in range(tile_t, tile_b + 1):
            for c in range(tile_l, tile_r + 1):
                if self.tiles[r][c] == C.TILE_WALL:
                    close_x = max(c * C.TILE_SIZE, min(cx, (c + 1) * C.TILE_SIZE))
                    close_y = max(r * C.TILE_SIZE, min(cy, (r + 1) * C.TILE_SIZE))
                    if (cx - close_x) ** 2 + (cy - close_y) ** 2 < radius * radius:
                        return False
        return True

    # ── Spawn positions ────────────────────────────────────────────────────────
    def get_spawn_positions(
        self,
        count: int,
        min_dist_from_centre: float = 200.0,
        exclude_pos: tuple[float, float] | None = None,
        exclude_dist: float = 200.0,
    ) -> list[tuple[float, float]]:
        """Return up to *count* floor-tile centres away from the room centre.

        If *exclude_pos* is given, also exclude tiles within *exclude_dist* px
        of that point (used to keep enemies away from the player entry point).
        """
        cx = C.ROOM_PIXEL_W / 2
        cy = C.ROOM_PIXEL_H / 2
        ex_sq = exclude_dist * exclude_dist
        candidates: list[tuple[float, float]] = []
        for r in range(2, C.ROOM_TILE_H - 2):
            for c in range(2, C.ROOM_TILE_W - 2):
                if self.tiles[r][c] == C.TILE_FLOOR:
                    px = (c + 0.5) * C.TILE_SIZE
                    py = (r + 0.5) * C.TILE_SIZE
                    if (px - cx) ** 2 + (py - cy) ** 2 >= min_dist_from_centre**2:
                        if exclude_pos is None or ((px - exclude_pos[0]) ** 2 + (py - exclude_pos[1]) ** 2 >= ex_sq):
                            candidates.append((px, py))
        random.shuffle(candidates)
        return candidates[:count]

    # ── Draw ───────────────────────────────────────────────────────────────────
    def find_spawn_near_centre(self, radius: float = 14.0) -> tuple[float, float]:
        """Return the nearest floor position to the room centre where a circle of *radius* fits."""
        import math

        cx = C.ROOM_PIXEL_W / 2.0
        cy = C.ROOM_PIXEL_H / 2.0
        if self.is_circle_walkable(cx, cy, radius):
            return (cx, cy)
        for dist in range(C.TILE_SIZE, 300, C.TILE_SIZE):
            n_steps = max(8, dist // (C.TILE_SIZE // 2))
            for step in range(n_steps):
                angle = step * 2 * math.pi / n_steps
                px = cx + math.cos(angle) * dist
                py = cy + math.sin(angle) * dist
                if self.is_circle_walkable(px, py, radius):
                    return (px, py)
        return (cx, cy)  # last-resort fallback

    def draw(self, surf: pygame.Surface, camera: Camera) -> None:
        sx, sy = camera.apply_pos(0, 0)
        surf.blit(self.surface, (round(sx), round(sy)))
