"""HUD — hearts, coin counter, floor info, death/upgrade overlays."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pygame

from gamejam_may_2026 import constants as C
from gamejam_may_2026 import icons

if TYPE_CHECKING:
    from gamejam_may_2026.camera import Camera
    from gamejam_may_2026.dungeon import Dungeon
    from gamejam_may_2026.perks import Perk
    from gamejam_may_2026.player import Player
    from gamejam_may_2026.relics import Relic

# ── Font cache ────────────────────────────────────────────────────────────────
_fonts: dict[tuple, pygame.font.Font] = {}


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont("monospace", size, bold=bold)
    return _fonts[key]


# ── Heart shape helper ────────────────────────────────────────────────────────
def _draw_heart(
    surf: pygame.Surface,
    cx: int,
    cy: int,
    size: int,
    filled: bool,
    half: bool = False,
) -> None:
    """Draw a diamond heart.

    ``half=True`` draws the left half filled and the right half empty —
    used to show pending half-damage from the Petrified Heart relic.
    """
    s = size // 2
    points = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]

    if half:
        # Draw full diamond with empty colour, then left triangle with full colour
        pygame.draw.polygon(surf, C.C_HEART_EMPTY, points)
        left_tri = [(cx, cy - s), (cx, cy + s), (cx - s, cy)]
        pygame.draw.polygon(surf, C.C_HEART_FULL, left_tri)
    else:
        pygame.draw.polygon(surf, C.C_HEART_FULL if filled else C.C_HEART_EMPTY, points)

    pygame.draw.polygon(surf, (0, 0, 0), points, 1)


# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud(
    surf: pygame.Surface,
    player: Player,
    floor_num: int = 1,
    room_num: int = 1,
    enemies_left: int = 0,
    debug: bool = False,
    mode_label: str = "",
) -> None:
    # Background strip
    hud_y = C.PLAYFIELD_H
    pygame.draw.rect(surf, C.C_HUD_BG, (0, hud_y, C.SCREEN_W, C.HUD_H))
    pygame.draw.line(surf, C.C_HUD_BORDER, (0, hud_y), (C.SCREEN_W, hud_y), 2)

    cy = hud_y + C.HUD_H // 2

    # ── Hearts ────────────────────────────────────────────────────────────────
    heart_size = 30
    hx = 24
    petrified = getattr(player, "petrified_heart", False)
    petrified_acc = getattr(player, "_petrified_acc", 0.0)
    # Show the rightmost filled heart as half when a pending half-hit is accumulated.
    half_heart_idx = (player.hp - 1) if (petrified and petrified_acc >= 0.5) else -1
    for i in range(player.max_hp):
        _draw_heart(surf, hx, cy, heart_size, i < player.hp, half=i == half_heart_idx)
        hx += 38

    # ── Coin counter ──────────────────────────────────────────────────────────
    coin_x = 24 + player.max_hp * 38 + 20
    pygame.draw.circle(surf, C.C_COIN, (coin_x, cy), 11)
    pygame.draw.circle(surf, C.C_COIN_DARK, (coin_x, cy), 11, 2)
    pygame.draw.circle(surf, (255, 240, 120), (coin_x - 3, cy - 3), 4)
    coin_label = _font(22, bold=True).render(f"× {player.coins}", True, C.C_COIN)
    surf.blit(coin_label, (coin_x + 18, cy - 11))

    # ── Enemies left ──────────────────────────────────────────────────────────
    if enemies_left > 0:
        label = _font(18).render(f"! {enemies_left}", True, (200, 80, 80))
        surf.blit(label, (C.SCREEN_W // 2 - label.get_width() // 2, cy - 10))

    # ── Floor / room  or  custom mode label ───────────────────────────────────
    if mode_label:
        ml = _font(19, bold=True).render(mode_label, True, (190, 150, 255))
        surf.blit(ml, (C.SCREEN_W - ml.get_width() - 12, hud_y + 22))
    else:
        floor_label = _font(20, bold=True).render(f"Floor {floor_num}", True, (165, 148, 125))
        room_label = _font(15).render(f"Room {room_num}", True, (105, 92, 80))
        surf.blit(floor_label, (C.SCREEN_W - 140, hud_y + 12))
        surf.blit(room_label, (C.SCREEN_W - 120, hud_y + 38))

    # ── Relic icon strip (small icons left-aligned, second row) ──────────────
    relics = getattr(player, "relics", [])
    if relics:
        icon_size = 16
        rx = 12
        iy = hud_y + 58 + icon_size // 2  # vertical centre of icon row
        for relic in relics:
            icons.draw(surf, rx + icon_size // 2, iy, icon_size, relic.id, (195, 175, 255))
            rx += icon_size + 4

    # ── Dash cooldown hint ────────────────────────────────────────────────────
    hint = _font(13).render("[SPACE] dash   [LMB] shoot", True, (70, 60, 50))
    surf.blit(hint, (C.SCREEN_W - hint.get_width() - 10, hud_y + C.HUD_H - 20))

    # ── Debug banner ─────────────────────────────────────────────────────────
    if debug:
        dbg = _font(14, bold=True).render("[DEBUG]  K = kill all", True, (255, 80, 80))
        surf.blit(dbg, (C.SCREEN_W // 2 - dbg.get_width() // 2, hud_y + C.HUD_H - 18))


# ── Shared stat-block helper ──────────────────────────────────────────────────


def _fmt_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def _draw_run_stats(
    surf: pygame.Surface,
    stats: dict,
    cx: int,
    top_y: int,
    color: tuple[int, int, int] = (185, 170, 145),
) -> int:
    """Render a four-line stat block and return the y of the bottom edge."""
    lines = [
        f"Floor reached:    {stats.get('floors', 1)} / 7",
        f"Rooms cleared:    {stats.get('rooms', 0)}",
        f"Coins collected:  {stats.get('coins', 0)}",
        f"Time:             {_fmt_time(stats.get('time', 0.0))}",
    ]
    fnt = _font(22)
    lh = 32
    for i, line in enumerate(lines):
        s = fnt.render(line, True, color)
        surf.blit(s, (cx - s.get_width() // 2, top_y + i * lh))
    return top_y + len(lines) * lh


# ── Game Over overlay ─────────────────────────────────────────────────────────
def draw_death_screen(
    surf: pygame.Surface,
    stats: dict,
    new_highscore: bool = False,
    highscore: dict | None = None,
) -> None:
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 170))
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.SCREEN_H // 2

    # Title
    title = _font(72, bold=True).render("YOU DIED", True, (210, 50, 50))
    surf.blit(title, (cx - title.get_width() // 2, cy - 200))

    # Run stats
    stats_bottom = _draw_run_stats(surf, stats, cx, cy - 130)

    # High-score line
    hs_y = stats_bottom + 14
    if new_highscore:
        best = _font(26, bold=True).render("*  NEW BEST RUN!  *", True, (255, 215, 55))
        surf.blit(best, (cx - best.get_width() // 2, hs_y))
        hs_y += best.get_height() + 4
    elif highscore and highscore.get("floors", 0) > 0:
        hs_line = (
            f"Best: Floor {highscore['floors']}  ·  "
            f"{highscore['rooms']} rooms  ·  "
            f"{_fmt_time(highscore.get('time', 0.0))}"
        )
        hs_surf = _font(17).render(hs_line, True, (145, 128, 90))
        surf.blit(hs_surf, (cx - hs_surf.get_width() // 2, hs_y))
        hs_y += hs_surf.get_height() + 4

    # Prompt
    restart = _font(22).render("Press  R  to return to menu", True, (180, 160, 140))
    surf.blit(restart, (cx - restart.get_width() // 2, hs_y + 10))


# ── Upgrade selection overlay ─────────────────────────────────────────────────

# Card geometry — kept in sync with game.py's _upgrade_card_rect()
UPGRADE_CARD_W = 280
UPGRADE_CARD_H = 200
UPGRADE_CARD_GAP = 30


def _upgrade_card_rect(idx: int) -> pygame.Rect:
    """Return the screen rect for upgrade card *idx* (0, 1, 2)."""
    total_w = 3 * UPGRADE_CARD_W + 2 * UPGRADE_CARD_GAP
    start_x = (C.SCREEN_W - total_w) // 2
    card_y = C.PLAYFIELD_H // 2 - UPGRADE_CARD_H // 2
    return pygame.Rect(
        start_x + idx * (UPGRADE_CARD_W + UPGRADE_CARD_GAP),
        card_y,
        UPGRADE_CARD_W,
        UPGRADE_CARD_H,
    )


def _draw_wrapped(
    surf: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    x: int,
    y: int,
    max_w: int,
    color: tuple[int, int, int],
) -> None:
    """Render *text* word-wrapped inside *max_w* pixels."""
    words = text.split()
    lines: list[str] = []
    line: list[str] = []
    for word in words:
        test = " ".join(line + [word])
        if font.size(test)[0] <= max_w:
            line.append(word)
        else:
            if line:
                lines.append(" ".join(line))
            line = [word]
    if line:
        lines.append(" ".join(line))
    lh = font.get_linesize()
    for i, ln in enumerate(lines):
        surf.blit(font.render(ln, True, color), (x, y + i * lh))


def draw_upgrade_screen(
    surf: pygame.Surface,
    perks: list[Perk],
    hovered: int = -1,
) -> None:
    """Full-screen upgrade chooser: dim overlay + 3 perk cards."""
    # Dim
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 175))
    surf.blit(overlay, (0, 0))

    # Title
    title = _font(38, bold=True).render("Choose an Upgrade", True, (220, 200, 150))
    title_y = _upgrade_card_rect(0).top - 70
    surf.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, title_y))

    # Cards
    for i, perk in enumerate(perks):
        rect = _upgrade_card_rect(i)
        is_hov = i == hovered

        bg_col = (75, 58, 38) if is_hov else (42, 32, 20)
        border_col = (210, 180, 80) if is_hov else (95, 72, 48)
        name_col = (255, 240, 150) if is_hov else (230, 210, 165)

        pygame.draw.rect(surf, bg_col, rect, border_radius=8)
        pygame.draw.rect(surf, border_col, rect, 2, border_radius=8)

        # [1] / [2] / [3] shortcut label
        num = _font(16).render(f"[{i + 1}]", True, (140, 120, 80))
        surf.blit(num, (rect.x + 10, rect.y + 8))

        # Icon
        icon_size = 28
        icons.draw(surf, rect.right - icon_size // 2 - 10, rect.y + 8 + icon_size // 2, icon_size, perk.id, name_col)

        # Perk name
        name_surf = _font(23, bold=True).render(perk.name, True, name_col)
        surf.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 42))

        # Divider line
        pygame.draw.line(surf, border_col, (rect.x + 16, rect.y + 75), (rect.right - 16, rect.y + 75), 1)

        # Description (word-wrapped)
        _draw_wrapped(surf, perk.desc, _font(16), rect.x + 16, rect.y + 84, rect.width - 32, (170, 155, 120))

    # Footer hint
    hint = _font(17).render("Click a card  or press  1 / 2 / 3", True, (100, 90, 70))
    hint_y = _upgrade_card_rect(0).bottom + 18
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, hint_y))


# ── Relic selection overlay ──────────────────────────────────────────────────


def _relic_card_rect(idx: int) -> pygame.Rect:
    """Return the screen rect for relic card *idx* (0 or 1) — 2 cards centred."""
    total_w = 2 * UPGRADE_CARD_W + UPGRADE_CARD_GAP
    start_x = (C.SCREEN_W - total_w) // 2
    card_y = C.PLAYFIELD_H // 2 - UPGRADE_CARD_H // 2
    return pygame.Rect(
        start_x + idx * (UPGRADE_CARD_W + UPGRADE_CARD_GAP),
        card_y,
        UPGRADE_CARD_W,
        UPGRADE_CARD_H,
    )


def draw_relic_screen(
    surf: pygame.Surface,
    relics: list[Relic],
    hovered: int = -1,
) -> None:
    """Full-screen relic chooser: dim overlay + 2 relic cards."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((15, 0, 30, 185))
    surf.blit(overlay, (0, 0))

    title = _font(38, bold=True).render("Choose a Relic", True, (200, 175, 255))
    title_y = _relic_card_rect(0).top - 74
    surf.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, title_y))

    sub = _font(18).render("A permanent boon for the rest of the run", True, (120, 100, 165))
    surf.blit(sub, (C.SCREEN_W // 2 - sub.get_width() // 2, title_y + 44))

    for i, relic in enumerate(relics):
        rect = _relic_card_rect(i)
        is_hov = i == hovered

        bg_col = (55, 38, 80) if is_hov else (28, 18, 48)
        border_col = (200, 150, 255) if is_hov else (88, 60, 140)
        name_col = (240, 210, 255) if is_hov else (200, 170, 240)

        pygame.draw.rect(surf, bg_col, rect, border_radius=8)
        pygame.draw.rect(surf, border_col, rect, 2, border_radius=8)

        # [1] / [2] shortcut label
        num = _font(16).render(f"[{i + 1}]", True, (135, 100, 185))
        surf.blit(num, (rect.x + 10, rect.y + 8))

        # Large icon
        icon_size = 36
        icons.draw(surf, rect.centerx, rect.y + 20 + icon_size // 2, icon_size, relic.id, name_col)

        # Relic name
        name_surf = _font(23, bold=True).render(relic.name, True, name_col)
        surf.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 76))

        # Divider
        pygame.draw.line(surf, border_col, (rect.x + 16, rect.y + 108), (rect.right - 16, rect.y + 108), 1)

        # Description
        _draw_wrapped(surf, relic.desc, _font(16), rect.x + 16, rect.y + 116, rect.width - 32, (165, 140, 215))

    hint = _font(17).render("Click a card  or press  1 / 2", True, (90, 70, 130))
    hint_y = _relic_card_rect(0).bottom + 18
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, hint_y))


# ── Boss-gate hint ───────────────────────────────────────────────────────────
def draw_boss_gate_hint(
    surf: pygame.Surface,
    direction: str,
    t: float,
    cam_ox: float = 0.0,
    cam_oy: float = 0.0,
) -> None:
    """Small tooltip near the boss-gate bars reminding the player to clear all
    rooms.  *t* is the remaining display time (seconds); the label fades out
    over the last 0.5 s and fades in over the first 0.2 s.

    The label is drawn in world space (close to the gate) so it's naturally
    anchored to the door the player just bumped.
    """
    # Alpha: quick fade-in, slow fade-out
    fade_in = min(1.0, t / 0.2)
    fade_out = min(1.0, (2.5 - t) / 0.5) if t < 2.5 else 1.0
    # fade_out here: goes 0→1 as t goes 2.5→2.0, meaning starts fading at t=2.0
    # Reconsider: t counts DOWN from 2.5 to 0. "last 0.5 s" = t < 0.5.
    fade_out = min(1.0, t / 0.5)  # 0→1 as t goes 0→0.5; full at t≥0.5
    alpha = int(fade_in * fade_out * 220)
    if alpha <= 0:
        return

    label = _font(17, bold=True).render("[!]  Clear every room to open the gate", True, (220, 180, 75))
    pad = 7
    w = label.get_width() + pad * 2
    h = label.get_height() + pad * 2

    ts = C.TILE_SIZE
    # Position inside the room, just past the wall face so it's visible even
    # before the player walks up to the gate.
    if direction == "N":
        rx = C.ROOM_PIXEL_W // 2 - w // 2
        ry = ts + 10
    elif direction == "S":
        rx = C.ROOM_PIXEL_W // 2 - w // 2
        ry = C.ROOM_PIXEL_H - ts - h - 10
    elif direction == "W":
        rx = ts + 10
        ry = C.ROOM_PIXEL_H // 2 - h // 2
    else:  # E
        rx = C.ROOM_PIXEL_W - ts - w - 10
        ry = C.ROOM_PIXEL_H // 2 - h // 2

    sx = round(rx + cam_ox)
    sy = round(ry + cam_oy)

    # Dark panel + amber border, then text on top
    panel = pygame.Surface((w, h))
    panel.fill((22, 15, 8))
    pygame.draw.rect(panel, (110, 78, 28), (0, 0, w, h), 1)
    panel.blit(label, (pad, pad))
    panel.set_alpha(alpha)
    surf.blit(panel, (sx, sy))


# ── Boss HP bar (top of playfield) ───────────────────────────────────────────
def draw_boss_hpbar(
    surf: pygame.Surface,
    name: str,
    hp: int,
    max_hp: int,
    phase2: bool = False,
) -> None:
    """Centred boss HP bar near the top of the playfield."""
    BAR_W = 380
    BAR_H = 14
    cx = C.SCREEN_W // 2
    bx = cx - BAR_W // 2
    by = 10

    # Name label
    label = _font(15, bold=True).render(name.upper(), True, (220, 190, 145))
    surf.blit(label, (cx - label.get_width() // 2, by - 17))

    # Background + fill
    pygame.draw.rect(surf, (35, 5, 5), (bx - 1, by - 1, BAR_W + 2, BAR_H + 2))
    frac = max(0.0, hp / max_hp)
    fill = round(BAR_W * frac)
    bar_col = (255, 130, 30) if phase2 else (210, 45, 45)
    if fill > 0:
        pygame.draw.rect(surf, bar_col, (bx, by, fill, BAR_H))

    # Border
    pygame.draw.rect(surf, (110, 60, 28), (bx - 1, by - 1, BAR_W + 2, BAR_H + 2), 1)

    # HP text centred on bar
    txt = _font(12).render(f"{max(0, hp)} / {max_hp}", True, (200, 175, 140))
    surf.blit(txt, (cx - txt.get_width() // 2, by + 1))


# ── Minimap ───────────────────────────────────────────────────────────────────
def draw_minimap(surf: pygame.Surface, dungeon: Dungeon) -> None:
    """Overlay a small room-grid in the top-right corner of the playfield."""
    CW, CH = 20, 11  # cell width × height (2 : 1 matches room proportions)
    GAP = 2
    STRIDE_X = CW + GAP
    STRIDE_Y = CH + GAP
    PAD = 6  # padding inside the background rect
    MARGIN = 8  # margin from screen edges

    all_pos = list(dungeon.rooms.keys())
    if not all_pos:
        return

    min_gx = min(p[0] for p in all_pos)
    max_gx = max(p[0] for p in all_pos)
    min_gy = min(p[1] for p in all_pos)
    max_gy = max(p[1] for p in all_pos)

    grid_w = max_gx - min_gx + 1
    grid_h = max_gy - min_gy + 1

    map_w = grid_w * STRIDE_X - GAP + PAD * 2
    map_h = grid_h * STRIDE_Y - GAP + PAD * 2

    # Anchor to top-right of playfield
    map_x = C.SCREEN_W - map_w - MARGIN
    map_y = MARGIN

    # Semi-transparent dark background
    bg = pygame.Surface((map_w, map_h), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 150))
    surf.blit(bg, (map_x, map_y))
    pygame.draw.rect(surf, (90, 78, 60), (map_x, map_y, map_w, map_h), 1)

    cur = dungeon.current
    cur_pos = (cur.gx, cur.gy)

    def _cell_topleft(gx: int, gy: int) -> tuple[int, int]:
        return (
            map_x + PAD + (gx - min_gx) * STRIDE_X,
            map_y + PAD + (gy - min_gy) * STRIDE_Y,
        )

    # ── Connection lines (visited rooms only, each edge once) ─────────────────
    drawn_edges: set[tuple] = set()
    for pos, dr in dungeon.rooms.items():
        if not dr.visited:
            continue
        for nbr in dr.connections.values():
            if not nbr.visited:
                continue
            npos = (nbr.gx, nbr.gy)
            edge = (min(pos, npos), max(pos, npos))
            if edge in drawn_edges:
                continue
            drawn_edges.add(edge)
            x1, y1 = _cell_topleft(*pos)
            x2, y2 = _cell_topleft(*npos)
            pygame.draw.line(
                surf,
                (85, 78, 58),
                (x1 + CW // 2, y1 + CH // 2),
                (x2 + CW // 2, y2 + CH // 2),
                1,
            )

    # ── Cells ─────────────────────────────────────────────────────────────────
    for pos, dr in dungeon.rooms.items():
        if not dr.visited:
            continue
        cx, cy = _cell_topleft(*pos)
        is_cur = pos == cur_pos

        if is_cur:
            color = (220, 190, 60)  # gold — current room
            border = (255, 230, 90)
        elif dr.is_boss:
            color = (130, 25, 25) if dr.cleared else (210, 45, 45)
            border = (80, 20, 20) if dr.cleared else (255, 80, 80)
        elif dr.is_shop:
            color = (20, 120, 130) if dr.cleared else (30, 175, 190)
            border = (15, 80, 90) if dr.cleared else (20, 130, 145)
        elif dr.cleared:
            color = (40, 90, 40)  # dim green — cleared
            border = (30, 60, 30)
        else:
            color = (70, 185, 70)  # bright green — uncleared visited
            border = (50, 130, 50)

        pygame.draw.rect(surf, color, (cx, cy, CW, CH))
        pygame.draw.rect(surf, border, (cx, cy, CW, CH), 1)

        # Mark start room with a small white dot
        if dr.is_start and not is_cur:
            pygame.draw.circle(surf, (200, 200, 200), (cx + CW // 2, cy + CH // 2), 1)

        # Mark boss room with a small red dot (when cleared)
        if dr.is_boss and dr.cleared and not is_cur:
            pygame.draw.circle(surf, (80, 10, 10), (cx + CW // 2, cy + CH // 2), 1)

        # Mark shop room with a small cyan dot
        if dr.is_shop and not is_cur:
            pygame.draw.circle(surf, (30, 210, 220), (cx + CW // 2, cy + CH // 2), 1)


# ── Shop screen ───────────────────────────────────────────────────────────────


def draw_shop_screen(
    surf: pygame.Surface,
    items: list[Any],
    player: Player,
    hovered: int = -1,
) -> None:
    """Coin shop: 3 cards (HP vial + 2 perks).  Space/Esc to leave."""
    # Dim overlay — slightly different tint from upgrade screen
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 10, 20, 170))
    surf.blit(overlay, (0, 0))

    # Title
    title = _font(38, bold=True).render("Merchant", True, (160, 220, 230))
    title_y = _upgrade_card_rect(0).top - 70
    surf.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, title_y))

    # Coin balance
    bal = _font(22).render(f"Your coins:  {player.coins}", True, C.C_COIN)
    surf.blit(bal, (C.SCREEN_W // 2 - bal.get_width() // 2, title_y + 42))

    for i, item in enumerate(items[:3]):
        rect = _upgrade_card_rect(i)
        bought = item.get("bought", False)
        cost = item["cost"]
        # HP item: "bought" when HP is full
        if item["kind"] == "hp":
            bought = player.hp >= player.max_hp

        can_afford = player.coins >= cost and not bought
        is_hov = (i == hovered) and can_afford

        if bought:
            bg_col = (28, 28, 28)
            border_col = (60, 60, 60)
            name_col = (80, 80, 80)
        elif not can_afford:
            bg_col = (35, 28, 20)
            border_col = (70, 55, 38)
            name_col = (120, 100, 75)
        elif is_hov:
            bg_col = (25, 80, 90)
            border_col = (50, 190, 210)
            name_col = (160, 240, 250)
        else:
            bg_col = (20, 50, 60)
            border_col = (40, 130, 145)
            name_col = (120, 200, 215)

        pygame.draw.rect(surf, bg_col, rect, border_radius=8)
        pygame.draw.rect(surf, border_col, rect, 2, border_radius=8)

        # Shortcut label
        num = _font(16).render(f"[{i + 1}]", True, (100, 140, 150))
        surf.blit(num, (rect.x + 10, rect.y + 8))

        # Price badge (top-right)
        if bought and item["kind"] != "hp":
            badge_txt = "Sold Out"
            badge_col = (80, 80, 80)
        elif item["kind"] == "hp" and player.hp >= player.max_hp:
            badge_txt = "Full HP"
            badge_col = (80, 80, 80)
        else:
            badge_txt = f"{cost} ¢"
            badge_col = C.C_COIN if can_afford else (120, 100, 60)
        badge = _font(17, bold=True).render(badge_txt, True, badge_col)
        surf.blit(badge, (rect.right - badge.get_width() - 10, rect.y + 10))

        # Icon
        icon_size = 28
        icons.draw(
            surf, rect.centerx, rect.y + 38 + icon_size // 2, icon_size, item.get("icon_id", "heart_vial"), name_col
        )

        # Name
        name_surf = _font(21, bold=True).render(item["label"], True, name_col)
        surf.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 78))

        # Divider
        pygame.draw.line(surf, border_col, (rect.x + 16, rect.y + 108), (rect.right - 16, rect.y + 108), 1)

        # Description
        _draw_wrapped(
            surf,
            item["desc"],
            _font(15),
            rect.x + 16,
            rect.y + 116,
            rect.width - 32,
            (130, 160, 165) if not bought else (65, 65, 65),
        )

    hint = _font(17).render("1 / 2 / 3 to buy  ·  Space or Esc to leave", True, (70, 110, 120))
    hint_y = _upgrade_card_rect(0).bottom + 18
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, hint_y))


# ── Main menu ─────────────────────────────────────────────────────────────────

_MENU_BTN_W = 360
_MENU_BTN_H = 64
_MENU_BTN_GAP = 16

# Colours per button index: (normal_bg, hover_bg, normal_bd, hover_bd, normal_lbl, hover_lbl)
_MENU_BTN_STYLES = [
    # Dungeon Mode — forest green
    ((28, 52, 22), (52, 96, 40), (58, 128, 48), (100, 220, 80), (145, 210, 125), (220, 255, 195)),
    # Arena Mode — purple
    ((35, 18, 58), (68, 28, 110), (88, 42, 150), (180, 100, 255), (165, 120, 230), (220, 175, 255)),
    # Endless Mode — teal/cyan
    ((12, 42, 52), (18, 78, 100), (28, 110, 140), (60, 200, 240), (90, 190, 220), (180, 240, 255)),
    # Codex — amber
    ((44, 34, 12), (80, 60, 18), (110, 80, 28), (200, 155, 55), (185, 155, 90), (240, 210, 120)),
]
_MENU_BTN_LABELS = ["Dungeon Mode", "Arena Mode", "Endless Mode", "Codex"]
_MENU_BTN_SUBLABELS = [
    "7-floor roguelite run",
    "1v1 practice fights",
    "Survive infinite waves",
    "View enemies & relics",
]

_KEY_CHIP_W = 82
_KEY_CHIP_H = 26
_KEY_CHIP_GAP = 8
_KEY_LAYOUTS_ORDER = ["zqsd", "wasd", "arrows"]
_KEY_LAYOUTS_LABEL = {"zqsd": "ZQSD", "wasd": "WASD", "arrows": "Arrows"}


def _menu_button_rects() -> list[pygame.Rect]:
    """Return the four main-menu button rects (Dungeon, Arena, Endless, Codex)."""
    n = 4
    total_h = n * _MENU_BTN_H + (n - 1) * _MENU_BTN_GAP
    top = C.SCREEN_H // 2 - total_h // 2 + 20  # slight downward nudge from centre
    bx = C.SCREEN_W // 2 - _MENU_BTN_W // 2
    return [pygame.Rect(bx, top + i * (_MENU_BTN_H + _MENU_BTN_GAP), _MENU_BTN_W, _MENU_BTN_H) for i in range(n)]


def menu_button_at(mx: int, my: int) -> int:
    """Return 0/1/2 if (mx, my) hits that button, else -1."""
    for i, r in enumerate(_menu_button_rects()):
        if r.collidepoint(mx, my):
            return i
    return -1


def _key_chip_rects() -> list[pygame.Rect]:
    rects = _menu_button_rects()
    ctrl_y = rects[-1].bottom + 26
    chip_y = ctrl_y + 24
    total_w = 3 * _KEY_CHIP_W + 2 * _KEY_CHIP_GAP
    left = C.SCREEN_W // 2 - total_w // 2
    return [
        pygame.Rect(left + i * (_KEY_CHIP_W + _KEY_CHIP_GAP), chip_y, _KEY_CHIP_W, _KEY_CHIP_H)
        for i in range(3)
    ]


def key_layout_chip_at(mx: int, my: int) -> str | None:
    """Return layout name ("zqsd"/"wasd"/"arrows") if (mx, my) hits a chip, else None."""
    for i, r in enumerate(_key_chip_rects()):
        if r.collidepoint(mx, my):
            return _KEY_LAYOUTS_ORDER[i]
    return None


def draw_menu(surf: pygame.Surface, highscore: dict, hovered: int = -1, key_layout: str = "zqsd") -> None:
    """Title / main-menu screen with three navigation buttons."""
    surf.fill(C.C_BG)
    cx = C.SCREEN_W // 2

    # ── Decorative vine borders ───────────────────────────────────────────────
    border_col = (35, 65, 25)
    pygame.draw.line(surf, border_col, (0, 4), (C.SCREEN_W, 4), 3)
    pygame.draw.line(surf, border_col, (0, C.SCREEN_H - 5), (C.SCREEN_W, C.SCREEN_H - 5), 3)

    # ── Title ─────────────────────────────────────────────────────────────────
    title = _font(80, bold=True).render("VERDANT DEPTHS", True, (95, 195, 90))
    shadow = _font(80, bold=True).render("VERDANT DEPTHS", True, (30, 70, 25))
    ty = 62
    surf.blit(shadow, (cx - shadow.get_width() // 2 + 3, ty + 3))
    surf.blit(title, (cx - title.get_width() // 2, ty))

    tag = _font(18).render("A forest-ruins roguelite  ·  7 floors  ·  6 bosses", True, (55, 110, 50))
    surf.blit(tag, (cx - tag.get_width() // 2, ty + 92))

    # ── Navigation buttons ────────────────────────────────────────────────────
    rects = _menu_button_rects()
    for i, rect in enumerate(rects):
        is_hov = i == hovered
        nbg, hbg, nbd, hbd, nlbl, hlbl = _MENU_BTN_STYLES[i]
        bg_col = hbg if is_hov else nbg
        bd_col = hbd if is_hov else nbd
        lbl_col = hlbl if is_hov else nlbl

        pygame.draw.rect(surf, bg_col, rect, border_radius=8)
        pygame.draw.rect(surf, bd_col, rect, 2, border_radius=8)

        label = _font(26, bold=True).render(_MENU_BTN_LABELS[i], True, lbl_col)
        surf.blit(label, (rect.centerx - label.get_width() // 2, rect.y + 10))

        sub = _font(14).render(_MENU_BTN_SUBLABELS[i], True, (180, 160, 100) if is_hov else (100, 88, 58))
        surf.blit(sub, (rect.centerx - sub.get_width() // 2, rect.y + 38))

    # ── Quick controls strip ──────────────────────────────────────────────────
    ctrl_y = rects[-1].bottom + 26
    ctrl_fnt = _font(15)
    active_move = {"zqsd": "ZQSD", "wasd": "WASD", "arrows": "Arrows"}.get(key_layout, "ZQSD")
    controls = [
        ("Move", active_move),
        ("Shoot", "Left Click"),
        ("Dash", "Space"),
        ("Quit", "Esc"),
    ]
    parts: list[str] = []
    for key, val in controls:
        parts.append(f"{key}: {val}")
    ctrl_str = "   ·   ".join(parts)
    ctrl_s = ctrl_fnt.render(ctrl_str, True, (65, 100, 55))
    surf.blit(ctrl_s, (cx - ctrl_s.get_width() // 2, ctrl_y))

    # ── Key layout toggle chips ───────────────────────────────────────────────
    chip_rects = _key_chip_rects()
    keys_lbl = _font(14).render("Keys:", True, (65, 100, 55))
    surf.blit(keys_lbl, (chip_rects[0].x - keys_lbl.get_width() - 8, chip_rects[0].centery - keys_lbl.get_height() // 2))
    for i, r in enumerate(chip_rects):
        name = _KEY_LAYOUTS_ORDER[i]
        active = name == key_layout
        bg = (52, 96, 40) if active else (22, 38, 18)
        bd = (100, 220, 80) if active else (45, 80, 35)
        lbl_c = (220, 255, 195) if active else (80, 130, 65)
        pygame.draw.rect(surf, bg, r, border_radius=5)
        pygame.draw.rect(surf, bd, r, 2, border_radius=5)
        chip_txt = _font(14, bold=active).render(_KEY_LAYOUTS_LABEL[name], True, lbl_c)
        surf.blit(chip_txt, (r.centerx - chip_txt.get_width() // 2, r.centery - chip_txt.get_height() // 2))

    # ── Best run ──────────────────────────────────────────────────────────────
    best_top = chip_rects[0].bottom + 14
    if highscore.get("floors", 0) > 0:
        bt = _font(16, bold=True).render("BEST RUN", True, (200, 175, 60))
        surf.blit(bt, (cx - bt.get_width() // 2, best_top))
        bi = _font(15).render(
            f"Floor {highscore['floors']} / 7  ·  "
            f"{highscore['rooms']} rooms  ·  "
            f"{highscore['coins']} coins  ·  "
            f"{_fmt_time(highscore.get('time', 0.0))}",
            True,
            (165, 145, 75),
        )
        surf.blit(bi, (cx - bi.get_width() // 2, best_top + 22))
    else:
        no_hs = _font(15).render("No runs yet — be the first!", True, (65, 100, 55))
        surf.blit(no_hs, (cx - no_hs.get_width() // 2, best_top + 4))


# ── Floor-clear overlay ───────────────────────────────────────────────────────


def draw_floor_clear(surf: pygame.Surface, floor: int) -> None:
    """Shown after the boss is defeated.  The staircase is visible behind."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 155))  # slightly lighter so staircase glow shows through
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.PLAYFIELD_H // 2

    title = _font(62, bold=True).render(f"Floor {floor} Cleared!", True, (220, 200, 80))
    surf.blit(title, (cx - title.get_width() // 2, cy - 90))

    sub = _font(24).render("The ancient staircase has opened…", True, (150, 200, 115))
    surf.blit(sub, (cx - sub.get_width() // 2, cy - 20))

    sub2 = _font(20).render("Walk to the staircase to choose a relic, then descend when ready.", True, (120, 160, 88))
    surf.blit(sub2, (cx - sub2.get_width() // 2, cy + 16))

    hint = _font(20).render("Press  SPACE  to descend", True, (115, 105, 72))
    surf.blit(hint, (cx - hint.get_width() // 2, cy + 58))


# ── Victory screen ────────────────────────────────────────────────────────────


def draw_victory(
    surf: pygame.Surface,
    stats: dict,
    new_highscore: bool = False,
) -> None:
    """Shown after clearing all 7 floors."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 190))
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.SCREEN_H // 2

    title = _font(68, bold=True).render("VICTORY!", True, (255, 220, 60))
    surf.blit(title, (cx - title.get_width() // 2, cy - 200))

    sub = _font(24).render("The ancient ruins have been cleansed.", True, (200, 185, 120))
    surf.blit(sub, (cx - sub.get_width() // 2, cy - 135))

    # Run stats
    stats_bottom = _draw_run_stats(surf, stats, cx, cy - 100)

    # New best banner
    hs_y = stats_bottom + 14
    if new_highscore:
        best = _font(26, bold=True).render("*  NEW BEST RUN!  *", True, (255, 215, 55))
        surf.blit(best, (cx - best.get_width() // 2, hs_y))
        hs_y += best.get_height() + 4

    hint = _font(20).render("Press  R  to return to menu", True, (140, 130, 90))
    surf.blit(hint, (cx - hint.get_width() // 2, hs_y + 10))


# ── Descent staircase (drawn in boss room after floor clear) ──────────────────


def draw_staircase(
    surf: pygame.Surface,
    camera: Camera,
    x: float,
    y: float,
    t: float,
    ready: bool = False,
) -> None:
    """Stone staircase descending into the earth — appears after the boss dies."""
    sx, sy = camera.apply_pos(x, y)
    sx, sy = round(sx), round(sy)

    # Pulsing forest-green glow
    pulse = (math.sin(t * 1.8) + 1.0) * 0.5
    gr = 30 + round(pulse * 10)
    glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
    pygame.draw.circle(glow, (55, 195, 85, int(38 + pulse * 38)), (gr, gr), gr)
    surf.blit(glow, (sx - gr, sy - gr))

    # Dark pit opening beneath the steps
    pygame.draw.ellipse(surf, (5, 4, 2), (sx - 22, sy - 5, 44, 22))
    pygame.draw.ellipse(surf, (12, 10, 6), (sx - 16, sy - 3, 32, 14))

    # Four stone steps narrowing with depth
    steps = [
        (44, 8, 0, (86, 68, 48)),
        (32, 7, 7, (74, 58, 40)),
        (22, 6, 13, (62, 48, 32)),
        (14, 5, 18, (50, 40, 26)),
    ]
    base_y = sy - 20
    for w, h, yoff, col in steps:
        rx = sx - w // 2
        ry = base_y + yoff
        # shadow
        pygame.draw.rect(surf, (col[0] // 3, col[1] // 3, col[2] // 3), (rx + 2, ry + 2, w, h))
        # step face
        pygame.draw.rect(surf, col, (rx, ry, w, h))
        # top-edge highlight
        hi = (min(255, col[0] + 26), min(255, col[1] + 20), min(255, col[2] + 14))
        pygame.draw.line(surf, hi, (rx, ry), (rx + w - 1, ry), 1)
        # moss streak
        pygame.draw.line(surf, (38, 88, 28), (rx, ry + h - 2), (rx + w // 3, ry + h - 2), 1)

    # Small label — "Descend" when ready, otherwise "Pick a relic first"
    if ready:
        lbl_text = "Descend"
        lbl_col = (105, 185, 90)
    else:
        lbl_text = "Choose a relic first"
        lbl_col = (160, 140, 80)
    lbl = _font(13).render(lbl_text, True, lbl_col)
    surf.blit(lbl, (sx - lbl.get_width() // 2, sy + 12))


# ── Pause screen ──────────────────────────────────────────────────────────────

_PAUSE_BTN_W = 260
_PAUSE_BTN_H = 52
_PAUSE_BTN_GAP = 18


def pause_button_rects() -> tuple[pygame.Rect, pygame.Rect]:
    """Return (resume_rect, menu_rect) for click detection."""
    cx = C.SCREEN_W // 2
    cy = C.SCREEN_H // 2
    top = cy + 10
    resume = pygame.Rect(cx - _PAUSE_BTN_W // 2, top, _PAUSE_BTN_W, _PAUSE_BTN_H)
    menu = pygame.Rect(cx - _PAUSE_BTN_W // 2, top + _PAUSE_BTN_H + _PAUSE_BTN_GAP, _PAUSE_BTN_W, _PAUSE_BTN_H)
    return resume, menu


def draw_pause_screen(surf: pygame.Surface) -> None:
    """Semi-transparent pause overlay drawn on top of the frozen game view."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 165))
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.SCREEN_H // 2

    # Title
    title = _font(64, bold=True).render("PAUSED", True, (210, 195, 155))
    surf.blit(title, (cx - title.get_width() // 2, cy - 115))

    # Subtitle hint
    sub = _font(16).render("Esc  to resume", True, (115, 104, 80))
    surf.blit(sub, (cx - sub.get_width() // 2, cy - 22))

    resume_rect, menu_rect = pause_button_rects()
    mx, my = pygame.mouse.get_pos()

    for rect, label, hov in [
        (resume_rect, "Resume", resume_rect.collidepoint(mx, my)),
        (menu_rect, "Main Menu", menu_rect.collidepoint(mx, my)),
    ]:
        bg = (72, 58, 36) if hov else (42, 33, 20)
        bd = (200, 170, 72) if hov else (88, 70, 42)
        lc = (255, 232, 130) if hov else (208, 188, 136)
        pygame.draw.rect(surf, bg, rect, border_radius=6)
        pygame.draw.rect(surf, bd, rect, 2, border_radius=6)
        lbl = _font(24, bold=True).render(label, True, lc)
        surf.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - lbl.get_height() // 2))


# ── Codex screen ──────────────────────────────────────────────────────────────

# Tab configuration: (label, index)
_CODEX_TABS = ["ENEMIES", "BOSSES", "RELICS", "PERKS"]

# Enemy/boss entries: (class_name, constructor_kwargs, display_name, floor_badge, description)
_CODEX_REGULAR: list[tuple] | None = None
_CODEX_BOSSES: list[tuple] | None = None


def _get_codex_enemies() -> tuple[list, list]:
    """Lazily build the regular-enemy and boss entry lists (avoids import-time circles)."""
    global _CODEX_REGULAR, _CODEX_BOSSES
    if _CODEX_REGULAR is not None:
        return _CODEX_REGULAR, _CODEX_BOSSES

    from gamejam_may_2026 import enemies as E  # type: ignore

    _CODEX_REGULAR = [
        (
            E.GoblinRunner,
            {},
            "Goblin Runner",
            "F1+",
            "Relentless wall-aware chaser. Deals contact damage. Gains speed each floor.",
        ),
        (
            E.GoblinArcher,
            {},
            "Goblin Archer",
            "F1+",
            "Keeps its distance and fires aimed arrows with a wind-up telegraph.",
        ),
        (E.Wolf, {}, "Wolf", "F1+", "Fast flanker that dashes at any range. Deals contact damage."),
        (E.SporePlant, {}, "Spore Plant", "F1+", "Stationary. Alternates 4-way spore volleys at 0° and 45°."),
        (
            E.StoneCrawler,
            {},
            "Stone Crawler",
            "F4+",
            "Armoured chaser. Deflects the first 3 arrows back at you. Deals 2 damage on contact.",
        ),
        (
            E.VenomfangBat,
            {},
            "Venomfang Bat",
            "F4+",
            "Fast erratic flier with arc-wobble movement. Deals contact damage.",
        ),
        (
            E.CrystalTurret,
            {},
            "Crystal Turret",
            "F5+",
            "Stationary turret. Rapid-fires fast aimed shots directly at you.",
        ),
        (E.SporeElder, {}, "Spore Elder", "F5+ elite", "Elite plant. Fires 8-way volleys and periodic 6-spore clouds."),
        (E.ShadowWraith, {}, "Shadow Wraith", "F5+", "Teleports every 4 s. Fires pairs of homing projectiles."),
        (
            E.BoneArcher,
            {},
            "Bone Archer",
            "F6+",
            "3-way spread shots; every 4th shot is a 3-way volley of slow heavy bone spikes (2 dmg each).",
        ),
        (
            E.MagmaSlug,
            {},
            "Magma Slug",
            "F6+",
            "Slow armoured chaser. Leaves huge magma pools that linger for 8s; deals 2 contact damage.",
        ),
        (
            E.VoidShrieker,
            {},
            "Void Shrieker",
            "F7",
            "Fast erratic screamer. Explodes into an 8-way projectile ring on death.",
        ),
    ]
    _CODEX_BOSSES = [
        (
            E.GoblinShaman,
            {"floor": 1},
            "Goblin Shaman",
            "F1–2",
            "Fires magic bolt bursts and summons Runners. P2: wider burst + pulsing aura.",
        ),
        (
            E.AncientTree,
            {},
            "Ancient Tree",
            "F3",
            "Stationary. Alternating root bursts and fast thorn rings. Grows deadlier in P2.",
        ),
        (E.IronWarden, {}, "Iron Warden", "F4", "Armoured knight. Stomp AoE, shrapnel burst, P2 charge dash."),
        (
            E.AbyssalLeech,
            {},
            "Abyssal Leech",
            "F5",
            "Fires healing tendrils and burst volleys. Moves and doubles tendrils in P2.",
        ),
        (
            E.FungalMatriarch,
            {},
            "Fungal Matriarch",
            "F6",
            "Spore volleys + SporeElder summons. Passive HP aura. Faster fire in P2.",
        ),
        (
            E.VoidSovereign,
            {},
            "Void Sovereign",
            "F7",
            "Orbiting caster. Summons Wraiths. P2: 8-way burst, Shriekers, arena shrinks.",
        ),
    ]
    return _CODEX_REGULAR, _CODEX_BOSSES


def _codex_enemy_sprite(
    surf: pygame.Surface,
    cx: int,
    cy: int,
    clip_r: int,
    enemy_cls: type,
    kwargs: dict,
) -> None:
    """Render a static enemy sprite centred at (cx, cy) clipped to a circle of radius clip_r."""
    from gamejam_may_2026.camera import Camera  # type: ignore

    # Create a throw-away enemy at world origin
    try:
        enemy = enemy_cls(0.0, 0.0, **kwargs)
    except Exception:
        return

    # Trick: shift camera so world(0,0) maps to screen(cx, cy)
    cam = Camera()
    cam.offset.x = float(-cx)
    cam.offset.y = float(-cy)
    cam._sx = 0.0
    cam._sy = 0.0

    # Draw into surf with clip rect
    clip_rect = pygame.Rect(cx - clip_r, cy - clip_r, clip_r * 2, clip_r * 2)
    old_clip = surf.get_clip()
    surf.set_clip(clip_rect)
    try:
        enemy.draw(surf, cam)
    except Exception:
        pass
    surf.set_clip(old_clip)


def codex_tab_at(mx: int, my: int) -> int:
    """Return tab index if (mx, my) falls inside the codex tab bar, else -1."""
    HEADER_H = 44
    TAB_H = 38
    if not (HEADER_H <= my < HEADER_H + TAB_H):
        return -1
    tab_w = C.SCREEN_W // len(_CODEX_TABS)
    idx = mx // tab_w
    return idx if 0 <= idx < len(_CODEX_TABS) else -1


def draw_codex(surf: pygame.Surface, tab: int, scroll: int = 0) -> None:
    """Full-screen Codex — enemies, bosses, relics and perks with sprites/icons."""
    from gamejam_may_2026.perks import PERK_POOL  # type: ignore
    from gamejam_may_2026.relics import RELIC_POOL  # type: ignore

    surf.fill(C.C_BG)

    # ── Decorative border ────────────────────────────────────────────────────
    border_col = (35, 65, 25)
    pygame.draw.line(surf, border_col, (0, 4), (C.SCREEN_W, 4), 3)
    pygame.draw.line(surf, border_col, (0, C.SCREEN_H - 5), (C.SCREEN_W, C.SCREEN_H - 5), 3)

    # ── Header ───────────────────────────────────────────────────────────────
    HEADER_H = 44
    title = _font(30, bold=True).render("CODEX", True, (95, 195, 90))
    surf.blit(title, (16, (HEADER_H - title.get_height()) // 2))
    hint = _font(16).render("Esc  to exit   ·   click / < > tabs   ·   scroll / ^ v", True, (55, 95, 50))
    surf.blit(hint, (C.SCREEN_W - hint.get_width() - 16, (HEADER_H - hint.get_height()) // 2))

    # ── Tab bar ──────────────────────────────────────────────────────────────
    TAB_H = 38
    TAB_Y = HEADER_H
    tab_w = C.SCREEN_W // len(_CODEX_TABS)
    for i, label in enumerate(_CODEX_TABS):
        active = i == tab
        rx = i * tab_w
        bg = (45, 80, 35) if active else (20, 38, 15)
        bd = (80, 165, 65) if active else (35, 68, 28)
        pygame.draw.rect(surf, bg, (rx, TAB_Y, tab_w, TAB_H))
        pygame.draw.rect(surf, bd, (rx, TAB_Y, tab_w, TAB_H), 2)
        lbl = _font(18, bold=active).render(label, True, (185, 235, 150) if active else (85, 130, 65))
        surf.blit(lbl, (rx + tab_w // 2 - lbl.get_width() // 2, TAB_Y + TAB_H // 2 - lbl.get_height() // 2))

    # ── Content area ─────────────────────────────────────────────────────────
    CONTENT_Y = HEADER_H + TAB_H + 8
    CONTENT_H = C.SCREEN_H - CONTENT_Y - 6
    PAD = 12

    if tab in (0, 1):
        # ── Enemy / Boss grid ────────────────────────────────────────────────
        regular, bosses = _get_codex_enemies()
        entries = regular if tab == 0 else bosses

        COLS = 4
        CARD_W = (C.SCREEN_W - PAD * (COLS + 1)) // COLS
        CARD_H = 165
        SPRITE_R = 28  # clip radius for enemy preview

        # Calculate total height for scrolling
        rows = (len(entries) + COLS - 1) // COLS
        total_h = rows * (CARD_H + PAD) + PAD
        max_scroll = max(0, total_h - CONTENT_H)
        scroll = max(0, min(scroll, max_scroll))

        # Clip content to content area
        old_clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, CONTENT_Y, C.SCREEN_W, CONTENT_H))

        for idx, (cls, kwargs, name, badge, desc) in enumerate(entries):
            col = idx % COLS
            row = idx // COLS
            cx_card = PAD + col * (CARD_W + PAD)
            cy_card = CONTENT_Y + PAD + row * (CARD_H + PAD) - scroll

            if cy_card + CARD_H < CONTENT_Y or cy_card > CONTENT_Y + CONTENT_H:
                continue  # off-screen

            # Card background
            card_rect = pygame.Rect(cx_card, cy_card, CARD_W, CARD_H)
            pygame.draw.rect(surf, (18, 35, 14), card_rect, border_radius=6)
            pygame.draw.rect(surf, (45, 80, 35), card_rect, 1, border_radius=6)

            # Enemy sprite preview (top portion)
            sprite_cx = cx_card + CARD_W // 2
            sprite_cy = cy_card + SPRITE_R + 10
            # Dark circle backdrop for sprite
            pygame.draw.circle(surf, (10, 22, 8), (sprite_cx, sprite_cy), SPRITE_R + 4)
            _codex_enemy_sprite(surf, sprite_cx, sprite_cy, SPRITE_R, cls, kwargs)

            # Name
            name_surf = _font(15, bold=True).render(name, True, (165, 220, 130))
            surf.blit(name_surf, (cx_card + CARD_W // 2 - name_surf.get_width() // 2, cy_card + SPRITE_R * 2 + 18))

            # Floor badge
            badge_surf = _font(12).render(badge, True, (200, 170, 70))
            surf.blit(badge_surf, (cx_card + CARD_W // 2 - badge_surf.get_width() // 2, cy_card + SPRITE_R * 2 + 36))

            # Description (wrapped)
            _draw_wrapped(surf, desc, _font(12), cx_card + 8, cy_card + SPRITE_R * 2 + 52, CARD_W - 16, (100, 145, 80))

        surf.set_clip(old_clip)

        # Scroll indicator
        if max_scroll > 0:
            frac = scroll / max_scroll
            bar_h = max(24, int(CONTENT_H * CONTENT_H / total_h))
            bar_y = CONTENT_Y + int(frac * (CONTENT_H - bar_h))
            pygame.draw.rect(surf, (40, 70, 30), (C.SCREEN_W - 8, CONTENT_Y, 6, CONTENT_H), border_radius=3)
            pygame.draw.rect(surf, (75, 145, 60), (C.SCREEN_W - 8, bar_y, 6, bar_h), border_radius=3)

    elif tab == 2:
        # ── Relics grid ──────────────────────────────────────────────────────
        COLS = 4
        CARD_W = (C.SCREEN_W - PAD * (COLS + 1)) // COLS
        CARD_H = 110
        ICON_SIZE = 28

        rows = (len(RELIC_POOL) + COLS - 1) // COLS
        total_h = rows * (CARD_H + PAD) + PAD
        max_scroll = max(0, total_h - CONTENT_H)
        scroll = max(0, min(scroll, max_scroll))

        old_clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, CONTENT_Y, C.SCREEN_W, CONTENT_H))

        for idx, relic in enumerate(RELIC_POOL):
            col = idx % COLS
            row = idx // COLS
            cx_card = PAD + col * (CARD_W + PAD)
            cy_card = CONTENT_Y + PAD + row * (CARD_H + PAD) - scroll

            if cy_card + CARD_H < CONTENT_Y or cy_card > CONTENT_Y + CONTENT_H:
                continue

            card_rect = pygame.Rect(cx_card, cy_card, CARD_W, CARD_H)
            pygame.draw.rect(surf, (22, 18, 40), card_rect, border_radius=6)
            pygame.draw.rect(surf, (75, 55, 130), card_rect, 1, border_radius=6)

            # Icon
            icon_cx = cx_card + CARD_W // 2
            icon_cy = cy_card + ICON_SIZE // 2 + 10
            icons.draw(surf, icon_cx, icon_cy, ICON_SIZE, relic.id, (195, 175, 255))

            # Name
            name_surf = _font(14, bold=True).render(relic.name, True, (210, 190, 255))
            surf.blit(name_surf, (cx_card + CARD_W // 2 - name_surf.get_width() // 2, icon_cy + ICON_SIZE // 2 + 6))

            # Description
            _draw_wrapped(
                surf, relic.desc, _font(12), cx_card + 8, icon_cy + ICON_SIZE // 2 + 24, CARD_W - 16, (135, 115, 195)
            )

        surf.set_clip(old_clip)

        if max_scroll > 0:
            frac = scroll / max_scroll
            bar_h = max(24, int(CONTENT_H * CONTENT_H / total_h))
            bar_y = CONTENT_Y + int(frac * (CONTENT_H - bar_h))
            pygame.draw.rect(surf, (35, 28, 60), (C.SCREEN_W - 8, CONTENT_Y, 6, CONTENT_H), border_radius=3)
            pygame.draw.rect(surf, (95, 70, 170), (C.SCREEN_W - 8, bar_y, 6, bar_h), border_radius=3)

    elif tab == 3:
        # ── Perks grid ───────────────────────────────────────────────────────
        COLS = 4
        CARD_W = (C.SCREEN_W - PAD * (COLS + 1)) // COLS
        CARD_H = 100
        ICON_SIZE = 26

        rows = (len(PERK_POOL) + COLS - 1) // COLS
        total_h = rows * (CARD_H + PAD) + PAD
        max_scroll = max(0, total_h - CONTENT_H)
        scroll = max(0, min(scroll, max_scroll))

        old_clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, CONTENT_Y, C.SCREEN_W, CONTENT_H))

        for idx, perk in enumerate(PERK_POOL):
            col = idx % COLS
            row = idx // COLS
            cx_card = PAD + col * (CARD_W + PAD)
            cy_card = CONTENT_Y + PAD + row * (CARD_H + PAD) - scroll

            if cy_card + CARD_H < CONTENT_Y or cy_card > CONTENT_Y + CONTENT_H:
                continue

            card_rect = pygame.Rect(cx_card, cy_card, CARD_W, CARD_H)
            pygame.draw.rect(surf, (16, 32, 28), card_rect, border_radius=6)
            pygame.draw.rect(surf, (48, 108, 88), card_rect, 1, border_radius=6)

            # Icon
            icon_cx = cx_card + CARD_W // 2
            icon_cy = cy_card + ICON_SIZE // 2 + 10
            icons.draw(surf, icon_cx, icon_cy, ICON_SIZE, perk.id, (140, 215, 185))

            # Name
            name_surf = _font(14, bold=True).render(perk.name, True, (165, 235, 210))
            surf.blit(name_surf, (cx_card + CARD_W // 2 - name_surf.get_width() // 2, icon_cy + ICON_SIZE // 2 + 6))

            # Description
            _draw_wrapped(
                surf, perk.desc, _font(12), cx_card + 8, icon_cy + ICON_SIZE // 2 + 24, CARD_W - 16, (100, 170, 145)
            )

        surf.set_clip(old_clip)

        if max_scroll > 0:
            frac = scroll / max_scroll
            bar_h = max(24, int(CONTENT_H * CONTENT_H / total_h))
            bar_y = CONTENT_Y + int(frac * (CONTENT_H - bar_h))
            pygame.draw.rect(surf, (20, 38, 32), (C.SCREEN_W - 8, CONTENT_Y, 6, CONTENT_H), border_radius=3)
            pygame.draw.rect(surf, (65, 148, 118), (C.SCREEN_W - 8, bar_y, 6, bar_h), border_radius=3)


# ── Arena Mode UI ─────────────────────────────────────────────────────────────

_ARENA_COLS = 6
_ARENA_CARD_W = 180
_ARENA_CARD_H = 128  # taller to hold sprite + name + desc
_ARENA_GAP = 10

# Vertical layout constants (computed once)
_ARENA_GRID_TOP = 160  # y where the enemy grid starts
_ARENA_COUNT_TOP = _ARENA_GRID_TOP + 3 * (_ARENA_CARD_H + _ARENA_GAP) + 14
_ARENA_START_TOP = _ARENA_COUNT_TOP + 60
_ARENA_START_W = 260
_ARENA_START_H = 52


def _arena_card_rect(idx: int) -> pygame.Rect:
    """Return the screen rect for arena enemy card *idx*."""
    col = idx % _ARENA_COLS
    row = idx // _ARENA_COLS
    total_w = _ARENA_COLS * _ARENA_CARD_W + (_ARENA_COLS - 1) * _ARENA_GAP
    start_x = (C.SCREEN_W - total_w) // 2
    return pygame.Rect(
        start_x + col * (_ARENA_CARD_W + _ARENA_GAP),
        _ARENA_GRID_TOP + row * (_ARENA_CARD_H + _ARENA_GAP),
        _ARENA_CARD_W,
        _ARENA_CARD_H,
    )


def arena_count_arrow_rects() -> tuple[pygame.Rect, pygame.Rect]:
    """Return (dec_rect, inc_rect) for the count − / + arrow buttons.

    The buttons sit immediately left/right of the count number display area.
    A fixed 52 px clearance from screen centre leaves room for up to 3 digits.
    """
    cx = C.SCREEN_W // 2
    btn_w = 40
    btn_h = 40
    clearance = 28  # half the number display zone (fits "99" at font-28)
    y = _ARENA_COUNT_TOP + 2
    return (
        pygame.Rect(cx - clearance - btn_w, y, btn_w, btn_h),  # −  (left)
        pygame.Rect(cx + clearance, y, btn_w, btn_h),  # +  (right)
    )


def arena_start_button_rect() -> pygame.Rect:
    """Return the rect for the START FIGHT button."""
    return pygame.Rect(
        C.SCREEN_W // 2 - _ARENA_START_W // 2,
        _ARENA_START_TOP,
        _ARENA_START_W,
        _ARENA_START_H,
    )


def draw_arena_select(
    surf: pygame.Surface,
    entries: list,
    selected: int,
    count: int,
    focus: str = "grid",  # "grid" | "count" | "start"
) -> None:
    """Arena mode enemy selection screen with enemy sprites."""
    surf.fill(C.C_BG)
    cx = C.SCREEN_W // 2

    pygame.draw.line(surf, (45, 20, 70), (0, 4), (C.SCREEN_W, 4), 3)
    pygame.draw.line(surf, (45, 20, 70), (0, C.SCREEN_H - 5), (C.SCREEN_W, C.SCREEN_H - 5), 3)

    # ── Title ─────────────────────────────────────────────────────────────────
    title = _font(52, bold=True).render("ARENA MODE", True, (185, 120, 255))
    shadow = _font(52, bold=True).render("ARENA MODE", True, (55, 18, 95))
    surf.blit(shadow, (cx - shadow.get_width() // 2 + 2, 18 + 2))
    surf.blit(title, (cx - title.get_width() // 2, 18))
    sub = _font(15).render("No perks · No healing · pure skill", True, (110, 75, 165))
    surf.blit(sub, (cx - sub.get_width() // 2, 76))

    # ── Enemy grid ────────────────────────────────────────────────────────────
    SPRITE_R = 26  # clip radius for in-card sprite preview

    for i, entry in enumerate(entries):
        rect = _arena_card_rect(i)
        is_sel = i == selected
        is_boss = entry.get("is_boss", False)

        if is_sel and focus == "grid":
            bg_col = (78, 26, 132)
            bd_col = (215, 148, 255)
            nm_col = (255, 225, 255)
            bd_w = 2
        elif is_sel:
            bg_col = (55, 18, 92)
            bd_col = (155, 90, 210)
            nm_col = (220, 195, 245)
            bd_w = 2
        elif is_boss:
            bg_col = (52, 12, 32)
            bd_col = (165, 50, 68)
            nm_col = (225, 120, 138)
            bd_w = 1
        else:
            bg_col = (22, 14, 40)
            bd_col = (60, 44, 98)
            nm_col = (158, 138, 205)
            bd_w = 1

        pygame.draw.rect(surf, bg_col, rect, border_radius=6)
        pygame.draw.rect(surf, bd_col, rect, bd_w, border_radius=6)

        # ── Sprite preview ────────────────────────────────────────────────────
        sprite_cx = rect.centerx
        sprite_cy = rect.y + SPRITE_R + 8
        pygame.draw.circle(surf, (10, 6, 18), (sprite_cx, sprite_cy), SPRITE_R + 3)
        _codex_enemy_sprite(surf, sprite_cx, sprite_cy, SPRITE_R, entry.get("cls"), entry.get("cls_kwargs", {}))

        # BOSS badge
        if is_boss:
            tag = _font(10, bold=True).render("BOSS", True, (220, 75, 95))
            surf.blit(tag, (rect.right - tag.get_width() - 4, rect.y + 3))

        # Name
        nm = _font(14, bold=True).render(entry["name"], True, nm_col)
        surf.blit(nm, (rect.centerx - nm.get_width() // 2, sprite_cy + SPRITE_R + 5))

        # Description (clipped)
        ds = _font(11).render(entry.get("desc", ""), True, (160, 140, 210) if is_sel else (105, 88, 152))
        old_clip = surf.get_clip()
        surf.set_clip(rect.inflate(-4, 0))
        surf.blit(ds, (rect.centerx - ds.get_width() // 2, sprite_cy + SPRITE_R + 23))
        surf.set_clip(old_clip)

    # ── Count selector ────────────────────────────────────────────────────────
    sel_entry = entries[selected]
    max_c = sel_entry.get("max_count", 10)
    is_count_focused = focus == "count"

    count_y = _ARENA_COUNT_TOP

    # "Count" label above the row
    lbl = _font(14).render("COUNT", True, (185, 148, 255) if is_count_focused else (110, 85, 155))
    surf.blit(lbl, (cx - lbl.get_width() // 2, count_y - 18))

    # Dec / Inc buttons — positions come from arena_count_arrow_rects()
    dec_r, inc_r = arena_count_arrow_rects()

    # Pill background spans from dec_r.left to inc_r.right
    pill_rect = pygame.Rect(dec_r.left - 6, count_y - 2, inc_r.right - dec_r.left + 12, dec_r.height + 4)
    pill_col = (50, 24, 84) if is_count_focused else (24, 12, 42)
    pill_bd = (180, 115, 255) if is_count_focused else (80, 50, 130)
    pygame.draw.rect(surf, pill_col, pill_rect, border_radius=10)
    pygame.draw.rect(surf, pill_bd, pill_rect, 2, border_radius=10)

    # Dec / Inc buttons
    for btn_r, symbol, active in [(dec_r, "−", count > 1), (inc_r, "+", count < max_c)]:
        btn_bg = (68, 34, 116) if (active and is_count_focused) else (30, 14, 52)
        btn_bd = (185, 120, 255) if (active and is_count_focused) else (72, 46, 114)
        sym_c = (240, 210, 255) if active else (88, 66, 126)
        pygame.draw.rect(surf, btn_bg, btn_r, border_radius=6)
        pygame.draw.rect(surf, btn_bd, btn_r, 2, border_radius=6)
        sym = _font(22, bold=True).render(symbol, True, sym_c)
        surf.blit(sym, (btn_r.centerx - sym.get_width() // 2, btn_r.centery - sym.get_height() // 2))

    # Count number centred between buttons
    cnt_s = _font(28, bold=True).render(str(count), True, (245, 225, 255))
    surf.blit(cnt_s, (cx - cnt_s.get_width() // 2, count_y + 3))

    # "/ max" hint to the right of the + button
    max_s = _font(12).render(f"/ {max_c}", True, (105, 80, 155))
    surf.blit(max_s, (inc_r.right + 6, count_y + 15))

    # ── Start button ─────────────────────────────────────────────────────────
    is_start_focused = focus == "start"
    sbr = arena_start_button_rect()
    sbg = (62, 185, 52) if is_start_focused else (28, 88, 22)
    sbd = (130, 255, 110) if is_start_focused else (60, 165, 48)
    slc = (220, 255, 205) if is_start_focused else (150, 220, 130)
    pygame.draw.rect(surf, sbg, sbr, border_radius=8)
    pygame.draw.rect(surf, sbd, sbr, 2, border_radius=8)
    sbl = _font(22, bold=True).render("START FIGHT", True, slc)
    surf.blit(sbl, (sbr.centerx - sbl.get_width() // 2, sbr.centery - sbl.get_height() // 2))

    # ── Navigation hints ──────────────────────────────────────────────────────
    hint_y = sbr.bottom + 12
    hints = "Arrows — navigate   ·   Tab — switch focus   ·   Enter / Space — start   ·   Esc — back"
    hs = _font(13).render(hints, True, (72, 55, 108))
    surf.blit(hs, (cx - hs.get_width() // 2, hint_y))


# ── Arena Relic Select UI ─────────────────────────────────────────────────────

_ARENA_RELIC_COLS = 5
_ARENA_RELIC_CARD_W = 234
_ARENA_RELIC_CARD_H = 88
_ARENA_RELIC_GAP = 8
_ARENA_RELIC_GRID_TOP = 155
_ARENA_RELIC_NO_RELIC_Y = 96
_ARENA_RELIC_NO_RELIC_W = 280
_ARENA_RELIC_NO_RELIC_H = 42


def arena_relic_no_relic_rect() -> pygame.Rect:
    """Return the rect for the 'No Relic' button in the arena relic select screen."""
    return pygame.Rect(
        C.SCREEN_W // 2 - _ARENA_RELIC_NO_RELIC_W // 2,
        _ARENA_RELIC_NO_RELIC_Y,
        _ARENA_RELIC_NO_RELIC_W,
        _ARENA_RELIC_NO_RELIC_H,
    )


def arena_relic_card_rect(idx: int) -> pygame.Rect:
    """Return the screen rect for relic card *idx* (0..19 = RELIC_POOL index)."""
    col = idx % _ARENA_RELIC_COLS
    row = idx // _ARENA_RELIC_COLS
    total_w = _ARENA_RELIC_COLS * _ARENA_RELIC_CARD_W + (_ARENA_RELIC_COLS - 1) * _ARENA_RELIC_GAP
    start_x = (C.SCREEN_W - total_w) // 2
    return pygame.Rect(
        start_x + col * (_ARENA_RELIC_CARD_W + _ARENA_RELIC_GAP),
        _ARENA_RELIC_GRID_TOP + row * (_ARENA_RELIC_CARD_H + _ARENA_RELIC_GAP),
        _ARENA_RELIC_CARD_W,
        _ARENA_RELIC_CARD_H,
    )


def draw_arena_relic_select(
    surf: pygame.Surface,
    relic_pool: list,
    selected: int,  # -1 = No Relic, 0..19 = RELIC_POOL index
    hovered: int = -2,  # -2 = nothing, -1 = No Relic button, 0..19 = relic
) -> None:
    """Full-screen relic selection screen shown before an arena fight."""
    surf.fill((8, 8, 18))

    cx = C.SCREEN_W // 2

    # Title
    title = _font(36, bold=True).render("Choose a Relic", True, (200, 175, 255))
    surf.blit(title, (cx - title.get_width() // 2, 18))
    sub = _font(17).render("Pick one to take into the arena — or go in empty-handed", True, (100, 80, 150))
    surf.blit(sub, (cx - sub.get_width() // 2, 58))

    # ── "No Relic" button ────────────────────────────────────────────────────
    nr_rect = arena_relic_no_relic_rect()
    nr_sel = selected == -1
    nr_hov = hovered == -1
    nr_bg = (50, 38, 72) if nr_sel else (34, 24, 52) if nr_hov else (20, 14, 32)
    nr_border = (210, 160, 255) if nr_sel else (140, 100, 200) if nr_hov else (65, 48, 96)
    pygame.draw.rect(surf, nr_bg, nr_rect, border_radius=8)
    pygame.draw.rect(surf, nr_border, nr_rect, 2, border_radius=8)
    nr_label = _font(18, bold=nr_sel).render(
        "[ No Relic ]  (default)", True, (230, 210, 255) if nr_sel else (140, 120, 180)
    )
    surf.blit(nr_label, (nr_rect.centerx - nr_label.get_width() // 2, nr_rect.centery - nr_label.get_height() // 2))

    # ── Relic grid ───────────────────────────────────────────────────────────
    for i, relic in enumerate(relic_pool):
        rect = arena_relic_card_rect(i)
        is_sel = selected == i
        is_hov = hovered == i

        bg = (55, 40, 82) if is_sel else (38, 26, 58) if is_hov else (20, 13, 34)
        border = (210, 160, 255) if is_sel else (140, 100, 200) if is_hov else (52, 36, 78)
        name_col = (240, 215, 255) if is_sel else (195, 165, 235) if is_hov else (130, 110, 170)
        desc_col = (170, 145, 210) if is_sel else (130, 105, 165) if is_hov else (90, 72, 120)

        pygame.draw.rect(surf, bg, rect, border_radius=6)
        pygame.draw.rect(surf, border, rect, 2, border_radius=6)

        # Icon
        icon_size = 26
        icons.draw(surf, rect.x + 20, rect.centery, icon_size, relic.id, name_col)

        # Name
        name_surf = _font(16, bold=is_sel).render(relic.name, True, name_col)
        surf.blit(name_surf, (rect.x + 46, rect.y + 14))

        # Description (word-wrapped, 2 lines max)
        _draw_wrapped(surf, relic.desc, _font(12), rect.x + 46, rect.y + 38, rect.width - 54, desc_col)

    # ── Description panel for selected/hovered relic ─────────────────────────
    n_rows = (len(relic_pool) + _ARENA_RELIC_COLS - 1) // _ARENA_RELIC_COLS
    grid_bottom = _ARENA_RELIC_GRID_TOP + n_rows * _ARENA_RELIC_CARD_H + (n_rows - 1) * _ARENA_RELIC_GAP
    desc_y = grid_bottom + 10

    active = hovered if hovered >= -1 else selected
    if active >= 0 and active < len(relic_pool):
        relic = relic_pool[active]
        panel_text = f"{relic.name}  —  {relic.desc}"
        ps = _font(16).render(panel_text, True, (200, 180, 240))
        surf.blit(ps, (cx - ps.get_width() // 2, desc_y))
    elif active == -1:
        ps = _font(16).render("No relic — you'll face the challenge unarmed", True, (110, 90, 150))
        surf.blit(ps, (cx - ps.get_width() // 2, desc_y))

    # ── Controls hint ────────────────────────────────────────────────────────
    hint = _font(14).render(
        "Arrow keys — navigate   ·   Enter / Space — confirm   ·   Esc — back to enemy select",
        True,
        (65, 50, 95),
    )
    surf.blit(hint, (cx - hint.get_width() // 2, C.SCREEN_H - 24))


def draw_arena_result(
    surf: pygame.Surface,
    won: bool,
    enemy_name: str,
    count: int,
) -> None:
    """Win / lose overlay drawn on top of the frozen arena fight."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 185))
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.SCREEN_H // 2

    if won:
        title_text = "VICTORY!"
        title_col = (255, 220, 60)
        label_text = f"Defeated {count}× {enemy_name}"
        label_col = (200, 185, 120)
    else:
        title_text = "DEFEATED"
        title_col = (210, 50, 50)
        label_text = f"Slain by {enemy_name}"
        label_col = (180, 110, 110)

    title = _font(68, bold=True).render(title_text, True, title_col)
    surf.blit(title, (cx - title.get_width() // 2, cy - 145))

    sub = _font(26).render(label_text, True, label_col)
    surf.blit(sub, (cx - sub.get_width() // 2, cy - 62))

    hint = _font(22).render("Press  R  to return to menu", True, (165, 148, 115))
    surf.blit(hint, (cx - hint.get_width() // 2, cy - 10))


# ── Endless Mode UI ───────────────────────────────────────────────────────────

_ENDLESS_MAX_START = 35  # 7 full cycles × 5 waves


def endless_start_button_rect() -> pygame.Rect:
    return pygame.Rect(C.SCREEN_W // 2 - 110, 482, 220, 52)


def endless_wave_arrow_rects() -> tuple[pygame.Rect, pygame.Rect]:
    """Return (dec_rect, inc_rect) for the wave selector arrows."""
    arrow_y = 408
    cx = C.SCREEN_W // 2
    return pygame.Rect(cx - 185, arrow_y, 44, 36), pygame.Rect(cx + 141, arrow_y, 44, 36)


def draw_endless_select(surf: pygame.Surface, selected_wave: int) -> None:
    """Endless mode selection screen: pick starting wave."""
    surf.fill(C.C_BG)
    cx = C.SCREEN_W // 2

    # Decorative borders
    border_col = (20, 80, 100)
    pygame.draw.line(surf, border_col, (0, 4), (C.SCREEN_W, 4), 3)
    pygame.draw.line(surf, border_col, (0, C.SCREEN_H - 5), (C.SCREEN_W, C.SCREEN_H - 5), 3)

    # Title
    title = _font(64, bold=True).render("∞ ENDLESS MODE", True, (80, 210, 240))
    shadow = _font(64, bold=True).render("∞ ENDLESS MODE", True, (20, 70, 90))
    surf.blit(shadow, (cx - shadow.get_width() // 2 + 3, 55 + 3))
    surf.blit(title, (cx - title.get_width() // 2, 55))

    tag = _font(17).render("Enemies drop coins — but there are no shops to spend them.", True, (60, 160, 185))
    surf.blit(tag, (cx - tag.get_width() // 2, 135))

    # Cycle structure explanation
    struct_y = 174
    struct = [
        ("Waves 1, 3, 4", "+1 HP", (160, 210, 170)),
        ("Wave 2", "+1 HP  •  Choose a perk", (210, 240, 140)),
        ("Wave 5  (boss)", "Full HP restore  •  Choose a relic", (220, 160, 255)),
    ]
    fnt_key = _font(16, bold=True)
    fnt_val = _font(16)
    col_key = (140, 180, 210)
    for i, (key, val, col_val) in enumerate(struct):
        ks = fnt_key.render(key + ":", True, col_key)
        vs = fnt_val.render(val, True, col_val)
        ky = struct_y + i * 24
        surf.blit(ks, (cx - 340, ky))
        surf.blit(vs, (cx - 340 + 180, ky))

    # Divider
    pygame.draw.line(surf, (30, 80, 100), (cx - 340, struct_y + 82), (cx + 340, struct_y + 82), 1)

    # Starting wave selector label
    lbl = _font(22, bold=True).render("Skip to wave:", True, (175, 210, 230))
    surf.blit(lbl, (cx - 340, 272))

    # Wave display box + arrows
    dec_rect, inc_rect = endless_wave_arrow_rects()
    box_rect = pygame.Rect(dec_rect.right + 6, dec_rect.y, inc_rect.left - dec_rect.right - 12, 36)

    if selected_wave == 0:
        wave_text = "0  —  Fresh start"
        sub_text = "Start with 0 perks · 0 relics"
        sub_col = (100, 130, 140)
    else:
        cycles = selected_wave // 5
        wave_text = f"Wave {selected_wave}"
        p_s = "perk" if cycles == 1 else "perks"
        r_s = "relic" if cycles == 1 else "relics"
        sub_text = f"Pre-select {cycles} {p_s} · {cycles} {r_s}  —  first fight: wave {selected_wave + 1}"
        sub_col = (140, 210, 170)

    # Arrow buttons (use ASCII < > — block glyphs are not in monospace font)
    for rect, label, is_dec in ((dec_rect, "<<", True), (inc_rect, ">>", False)):
        can = (is_dec and selected_wave > 0) or (not is_dec and selected_wave < _ENDLESS_MAX_START)
        bg = (25, 65, 85) if can else (18, 38, 48)
        bd = (60, 160, 200) if can else (35, 70, 85)
        pygame.draw.rect(surf, bg, rect, border_radius=6)
        pygame.draw.rect(surf, bd, rect, 2, border_radius=6)
        ac = (120, 200, 230) if can else (50, 80, 90)
        a = _font(18, bold=True).render(label, True, ac)
        surf.blit(a, (rect.centerx - a.get_width() // 2, rect.y + 8))

    # Wave display box
    pygame.draw.rect(surf, (15, 40, 58), box_rect, border_radius=6)
    pygame.draw.rect(surf, (60, 150, 185), box_rect, 2, border_radius=6)
    wt = _font(20, bold=True).render(wave_text, True, (190, 230, 250))
    surf.blit(wt, (box_rect.centerx - wt.get_width() // 2, box_rect.y + 7))

    # Sub-text under selector
    st = _font(15).render(sub_text, True, sub_col)
    surf.blit(st, (cx - st.get_width() // 2, dec_rect.bottom + 10))

    # Start button
    start_rect = endless_start_button_rect()
    pygame.draw.rect(surf, (18, 72, 100), start_rect, border_radius=8)
    pygame.draw.rect(surf, (60, 190, 230), start_rect, 2, border_radius=8)
    start_lbl = _font(26, bold=True).render("[ START ]", True, (160, 230, 255))
    surf.blit(start_lbl, (start_rect.centerx - start_lbl.get_width() // 2, start_rect.y + 12))

    # Hint
    hint = _font(15).render(
        "Left / Right to adjust   *   Space / Enter to start   *   Esc to cancel",
        True,
        (55, 120, 145),
    )
    surf.blit(hint, (cx - hint.get_width() // 2, start_rect.bottom + 16))


def draw_endless_between(
    surf: pygame.Surface,
    wave_completed: int,
    reward_lines: list[str],
    next_action: str,
) -> None:
    """Between-wave overlay for endless mode."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 165))
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.PLAYFIELD_H // 2

    # Title
    if wave_completed % 5 == 0:
        title_text = f"Boss Wave {wave_completed} Defeated!"
        title_col = (255, 170, 255)
    else:
        title_text = f"Wave {wave_completed} Cleared!"
        title_col = (220, 200, 80)
    title = _font(52, bold=True).render(title_text, True, title_col)
    surf.blit(title, (cx - title.get_width() // 2, cy - 120))

    # Reward lines
    for i, line in enumerate(reward_lines):
        if "HP" in line or "heal" in line.lower():
            col = (130, 240, 140)
        elif "perk" in line.lower() or "relic" in line.lower():
            col = (220, 200, 255)
        else:
            col = (185, 175, 145)
        t = _font(24).render(line, True, col)
        surf.blit(t, (cx - t.get_width() // 2, cy - 42 + i * 34))

    # Continue hint
    if next_action == "perk":
        hint_text = "Press  SPACE  to choose a perk"
        hint_col = (210, 240, 150)
    elif next_action == "relic":
        hint_text = "Press  SPACE  to choose a relic"
        hint_col = (200, 170, 255)
    else:
        hint_text = f"Press  SPACE  for wave {wave_completed + 1}"
        hint_col = (140, 200, 215)
    hint = _font(20).render(hint_text, True, hint_col)
    surf.blit(hint, (cx - hint.get_width() // 2, cy + 72))


def draw_endless_dead(surf: pygame.Surface, wave_reached: int) -> None:
    """Death overlay for endless mode."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 190))
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.SCREEN_H // 2

    title = _font(72, bold=True).render("FALLEN", True, (210, 50, 50))
    surf.blit(title, (cx - title.get_width() // 2, cy - 148))

    survived = wave_reached - 1
    if survived <= 0:
        wave_text = "Fell before surviving a single wave"
    elif survived == 1:
        wave_text = "Survived 1 wave"
    else:
        wave_text = f"Survived {survived} waves"
    ws = _font(30).render(wave_text, True, (175, 145, 115))
    surf.blit(ws, (cx - ws.get_width() // 2, cy - 68))

    hint = _font(22).render("Press  R  to return to menu", True, (140, 120, 90))
    surf.blit(hint, (cx - hint.get_width() // 2, cy - 16))
