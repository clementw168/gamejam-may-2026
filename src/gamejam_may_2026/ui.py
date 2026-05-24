"""HUD — hearts, coin counter, floor info, death/upgrade overlays."""

from __future__ import annotations
import pygame
from gamejam_may_2026 import constants as C

from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from gamejam_may_2026.player import Player
    from gamejam_may_2026.dungeon import Dungeon
    from gamejam_may_2026.perks import Perk

# ── Font cache ────────────────────────────────────────────────────────────────
_fonts: dict[tuple, pygame.font.Font] = {}


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont("monospace", size, bold=bold)
    return _fonts[key]


# ── Heart shape helper ────────────────────────────────────────────────────────
def _draw_heart(surf: pygame.Surface, cx: int, cy: int, size: int, filled: bool) -> None:
    color = C.C_HEART_FULL if filled else C.C_HEART_EMPTY
    # Diamond shape as heart stand-in (quick, readable)
    s = size // 2
    points = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
    pygame.draw.polygon(surf, color, points)
    pygame.draw.polygon(surf, (0, 0, 0), points, 1)


# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud(
    surf: pygame.Surface,
    player: Player,
    floor_num: int = 1,
    room_num: int = 1,
    enemies_left: int = 0,
) -> None:
    # Background strip
    hud_y = C.PLAYFIELD_H
    pygame.draw.rect(surf, C.C_HUD_BG, (0, hud_y, C.SCREEN_W, C.HUD_H))
    pygame.draw.line(surf, C.C_HUD_BORDER, (0, hud_y), (C.SCREEN_W, hud_y), 2)

    cy = hud_y + C.HUD_H // 2

    # ── Hearts ────────────────────────────────────────────────────────────────
    heart_size = 30
    hx = 24
    for i in range(player.max_hp):
        _draw_heart(surf, hx, cy, heart_size, i < player.hp)
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
        label = _font(18).render(f"☠ {enemies_left}", True, (200, 80, 80))
        surf.blit(label, (C.SCREEN_W // 2 - label.get_width() // 2, cy - 10))

    # ── Floor / room ──────────────────────────────────────────────────────────
    floor_label = _font(20, bold=True).render(f"Floor {floor_num}", True, (165, 148, 125))
    room_label = _font(15).render(f"Room {room_num}", True, (105, 92, 80))
    surf.blit(floor_label, (C.SCREEN_W - 140, hud_y + 12))
    surf.blit(room_label, (C.SCREEN_W - 120, hud_y + 38))

    # ── Dash cooldown hint ────────────────────────────────────────────────────
    hint = _font(13).render("[SPACE] dash   [LMB] shoot", True, (70, 60, 50))
    surf.blit(hint, (C.SCREEN_W - hint.get_width() - 10, hud_y + C.HUD_H - 20))


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
    lh  = 32
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
        best = _font(26, bold=True).render("✦  NEW BEST RUN!  ✦", True, (255, 215, 55))
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
UPGRADE_CARD_W   = 280
UPGRADE_CARD_H   = 200
UPGRADE_CARD_GAP = 30


def _upgrade_card_rect(idx: int) -> pygame.Rect:
    """Return the screen rect for upgrade card *idx* (0, 1, 2)."""
    total_w = 3 * UPGRADE_CARD_W + 2 * UPGRADE_CARD_GAP
    start_x = (C.SCREEN_W - total_w) // 2
    card_y  = C.PLAYFIELD_H // 2 - UPGRADE_CARD_H // 2
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
    words  = text.split()
    lines: list[str] = []
    line:  list[str] = []
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
        rect    = _upgrade_card_rect(i)
        is_hov  = (i == hovered)

        bg_col     = (75, 58, 38) if is_hov else (42, 32, 20)
        border_col = (210, 180, 80) if is_hov else (95, 72, 48)
        name_col   = (255, 240, 150) if is_hov else (230, 210, 165)

        pygame.draw.rect(surf, bg_col,     rect, border_radius=8)
        pygame.draw.rect(surf, border_col, rect, 2, border_radius=8)

        # [1] / [2] / [3] shortcut label
        num = _font(16).render(f"[{i + 1}]", True, (140, 120, 80))
        surf.blit(num, (rect.x + 10, rect.y + 8))

        # Icon
        icon = _font(30, bold=True).render(perk.icon, True, name_col)
        surf.blit(icon, (rect.right - icon.get_width() - 10, rect.y + 8))

        # Perk name
        name_surf = _font(23, bold=True).render(perk.name, True, name_col)
        surf.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 42))

        # Divider line
        pygame.draw.line(surf, border_col,
                         (rect.x + 16, rect.y + 75), (rect.right - 16, rect.y + 75), 1)

        # Description (word-wrapped)
        _draw_wrapped(surf, perk.desc, _font(16),
                      rect.x + 16, rect.y + 84,
                      rect.width - 32, (170, 155, 120))

    # Footer hint
    hint = _font(17).render("Click a card  or press  1 / 2 / 3", True, (100, 90, 70))
    hint_y = _upgrade_card_rect(0).bottom + 18
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
    fade_in  = min(1.0, t / 0.2)
    fade_out = min(1.0, (2.5 - t) / 0.5) if t < 2.5 else 1.0
    # fade_out here: goes 0→1 as t goes 2.5→2.0, meaning starts fading at t=2.0
    # Reconsider: t counts DOWN from 2.5 to 0. "last 0.5 s" = t < 0.5.
    fade_out = min(1.0, t / 0.5)   # 0→1 as t goes 0→0.5; full at t≥0.5
    alpha    = int(fade_in * fade_out * 220)
    if alpha <= 0:
        return

    label = _font(17, bold=True).render("⚔  Clear every room to open the gate", True, (220, 180, 75))
    pad   = 7
    w     = label.get_width() + pad * 2
    h     = label.get_height() + pad * 2

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
    cx    = C.SCREEN_W // 2
    bx    = cx - BAR_W // 2
    by    = 10

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
    CW, CH = 14, 7      # cell width × height (2 : 1 matches room proportions)
    GAP    = 2
    STRIDE_X = CW + GAP
    STRIDE_Y = CH + GAP
    PAD    = 6           # padding inside the background rect
    MARGIN = 8           # margin from screen edges

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
                surf, (85, 78, 58),
                (x1 + CW // 2, y1 + CH // 2),
                (x2 + CW // 2, y2 + CH // 2),
                1,
            )

    # ── Cells ─────────────────────────────────────────────────────────────────
    for pos, dr in dungeon.rooms.items():
        if not dr.visited:
            continue
        cx, cy = _cell_topleft(*pos)
        is_cur = (pos == cur_pos)

        if is_cur:
            color  = (220, 190,  60)   # gold — current room
            border = (255, 230,  90)
        elif dr.is_boss:
            color  = (130,  25,  25) if dr.cleared else (210,  45,  45)
            border = ( 80,  20,  20) if dr.cleared else (255,  80,  80)
        elif dr.is_shop:
            color  = ( 20, 120, 130) if dr.cleared else ( 30, 175, 190)
            border = ( 15,  80,  90) if dr.cleared else ( 20, 130, 145)
        elif dr.cleared:
            color  = ( 40,  90,  40)   # dim green — cleared
            border = ( 30,  60,  30)
        else:
            color  = ( 70, 185,  70)   # bright green — uncleared visited
            border = ( 50, 130,  50)

        pygame.draw.rect(surf, color,  (cx, cy, CW, CH))
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
        rect   = _upgrade_card_rect(i)
        bought = item.get("bought", False)
        cost   = item["cost"]
        # HP item: "bought" when HP is full
        if item["kind"] == "hp":
            bought = (player.hp >= player.max_hp)

        can_afford = player.coins >= cost and not bought
        is_hov     = (i == hovered) and can_afford

        if bought:
            bg_col = (28, 28, 28); border_col = (60, 60, 60); name_col = (80, 80, 80)
        elif not can_afford:
            bg_col = (35, 28, 20); border_col = (70, 55, 38); name_col = (120, 100, 75)
        elif is_hov:
            bg_col = (25, 80, 90); border_col = (50, 190, 210); name_col = (160, 240, 250)
        else:
            bg_col = (20, 50, 60); border_col = (40, 130, 145); name_col = (120, 200, 215)

        pygame.draw.rect(surf, bg_col,     rect, border_radius=8)
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
        icon = _font(28, bold=True).render(item.get("icon", "?"), True, name_col)
        surf.blit(icon, (rect.centerx - icon.get_width() // 2, rect.y + 38))

        # Name
        name_surf = _font(21, bold=True).render(item["label"], True, name_col)
        surf.blit(name_surf, (rect.centerx - name_surf.get_width() // 2, rect.y + 78))

        # Divider
        pygame.draw.line(surf, border_col,
                         (rect.x + 16, rect.y + 108), (rect.right - 16, rect.y + 108), 1)

        # Description
        _draw_wrapped(surf, item["desc"], _font(15),
                      rect.x + 16, rect.y + 116, rect.width - 32,
                      (130, 160, 165) if not bought else (65, 65, 65))

    hint = _font(17).render(
        "1 / 2 / 3 to buy  ·  Space or Esc to leave", True, (70, 110, 120))
    hint_y = _upgrade_card_rect(0).bottom + 18
    surf.blit(hint, (C.SCREEN_W // 2 - hint.get_width() // 2, hint_y))


# ── Main menu ─────────────────────────────────────────────────────────────────

def draw_menu(surf: pygame.Surface, highscore: dict) -> None:
    """Title / main-menu screen."""
    surf.fill(C.C_BG)

    cx = C.SCREEN_W // 2

    # ── Decorative vine border lines ─────────────────────────────────────────
    border_col = (35, 65, 25)
    pygame.draw.line(surf, border_col, (0, 4),            (C.SCREEN_W, 4),            3)
    pygame.draw.line(surf, border_col, (0, C.SCREEN_H-5), (C.SCREEN_W, C.SCREEN_H-5), 3)

    # ── Title ─────────────────────────────────────────────────────────────────
    title = _font(82, bold=True).render("VERDANT DEPTHS", True, (95, 195, 90))
    # Slight drop-shadow in a darker green
    shadow = _font(82, bold=True).render("VERDANT DEPTHS", True, (30, 70, 25))
    ty = 100
    surf.blit(shadow, (cx - shadow.get_width() // 2 + 3, ty + 3))
    surf.blit(title,  (cx - title.get_width()  // 2,     ty))

    # Subtitle tagline
    tag = _font(20).render(
        "A forest-ruins roguelite  ·  7 floors  ·  4 bosses", True, (60, 115, 55))
    surf.blit(tag, (cx - tag.get_width() // 2, ty + 100))

    # ── "Press any key" prompt ────────────────────────────────────────────────
    prompt = _font(30, bold=True).render("— Press any key to begin —", True, (145, 210, 130))
    surf.blit(prompt, (cx - prompt.get_width() // 2, 250))

    # ── Controls table ────────────────────────────────────────────────────────
    ctrl_y   = 320
    ctrl_fnt = _font(17)
    key_col  = (130, 185, 120)
    val_col  = (80, 125, 70)
    controls = [
        ("Move",  "ZQSD / WASD / Arrows"),
        ("Aim",   "Mouse"),
        ("Shoot", "Left Click"),
        ("Dash",  "Space  (i-frames + cooldown arc)"),
        ("Buy",   "1 / 2 / 3  in shops & upgrades"),
        ("Quit",  "Esc"),
    ]
    col_gap  = 20
    key_w    = max(ctrl_fnt.size(k + ":")[0] for k, _ in controls)
    lh       = 26
    for i, (key, val) in enumerate(controls):
        y     = ctrl_y + i * lh
        k_s   = ctrl_fnt.render(key + ":", True, key_col)
        v_s   = ctrl_fnt.render(val, True, val_col)
        left  = cx - (key_w + col_gap + v_s.get_width()) // 2
        surf.blit(k_s, (left + key_w - k_s.get_width(), y))
        surf.blit(v_s, (left + key_w + col_gap,         y))

    # ── Best run ──────────────────────────────────────────────────────────────
    best_top = ctrl_y + len(controls) * lh + 30
    if highscore.get("floors", 0) > 0:
        bt = _font(18, bold=True).render("BEST RUN", True, (200, 175, 60))
        surf.blit(bt, (cx - bt.get_width() // 2, best_top))
        bi = _font(16).render(
            f"Floor {highscore['floors']} / 7  ·  "
            f"{highscore['rooms']} rooms  ·  "
            f"{highscore['coins']} coins  ·  "
            f"{_fmt_time(highscore.get('time', 0.0))}",
            True, (165, 145, 75),
        )
        surf.blit(bi, (cx - bi.get_width() // 2, best_top + 26))
    else:
        no_hs = _font(16).render("No runs yet — be the first!", True, (65, 100, 55))
        surf.blit(no_hs, (cx - no_hs.get_width() // 2, best_top + 4))


# ── Floor-clear overlay ───────────────────────────────────────────────────────

def draw_floor_clear(surf: pygame.Surface, floor: int) -> None:
    """Shown after the boss is defeated.  Press Space to descend."""
    overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surf.blit(overlay, (0, 0))

    cx = C.SCREEN_W // 2
    cy = C.PLAYFIELD_H // 2

    title = _font(62, bold=True).render(f"Floor {floor} Cleared!", True, (220, 200, 80))
    surf.blit(title, (cx - title.get_width() // 2, cy - 70))

    sub = _font(24).render(
        f"Descending to floor {floor + 1}…", True, (170, 155, 90))
    surf.blit(sub, (cx - sub.get_width() // 2, cy + 10))

    hint = _font(20).render("Press  SPACE  to continue", True, (120, 110, 75))
    surf.blit(hint, (cx - hint.get_width() // 2, cy + 55))


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
        best = _font(26, bold=True).render("✦  NEW BEST RUN!  ✦", True, (255, 215, 55))
        surf.blit(best, (cx - best.get_width() // 2, hs_y))
        hs_y += best.get_height() + 4

    hint = _font(20).render("Press  R  to return to menu", True, (140, 130, 90))
    surf.blit(hint, (cx - hint.get_width() // 2, hs_y + 10))
