"""Pixel-art icon renderer — procedural icons for relics and perks.

Each icon is drawn using pygame draw primitives, scaled to any size.

Public API
----------
    draw(surf, cx, cy, size, icon_id, color)
        Draw icon centred at world point (cx, cy) in a bounding box of *size* px.
    surface(size, icon_id, color) -> pygame.Surface
        Return a cached *size×size* SRCALPHA Surface with the icon on it.
"""

from __future__ import annotations

import math

import pygame

# ── Cache ──────────────────────────────────────────────────────────────────────
_cache: dict[tuple, pygame.Surface] = {}


# ── Colour helpers ─────────────────────────────────────────────────────────────


def _dim(c: tuple, f: float = 0.50) -> tuple:
    return tuple(max(0, min(255, int(x * f))) for x in c[:3])


def _bright(c: tuple, f: float = 1.45) -> tuple:
    return tuple(min(255, int(x * f)) for x in c[:3])


# ── Geometry helpers ───────────────────────────────────────────────────────────


def _p(cx: float, cy: float, dx: float, dy: float) -> tuple[int, int]:
    """Offset (cx,cy) by scaled deltas and return an integer point."""
    return (int(cx + dx), int(cy + dy))


def _heart_pts(cx: float, cy: float, r: float) -> list[tuple[int, int]]:
    pts = []
    for i in range(20):
        t = math.pi * 2 * i / 20
        x = r * 0.9 * math.pow(abs(math.sin(t)), 3) * (1 if math.sin(t) >= 0 else -1)
        y = -r * (0.8125 * math.cos(t) - 0.3125 * math.cos(2 * t) - 0.125 * math.cos(3 * t) - 0.0625 * math.cos(4 * t))
        pts.append((int(cx + x), int(cy + y)))
    return pts


def _star_pts(
    cx: float, cy: float, r_out: float, r_in: float, n: int = 5, offset: float = -math.pi / 2
) -> list[tuple[int, int]]:
    pts = []
    for i in range(n * 2):
        a = math.pi * i / n + offset
        r = r_out if i % 2 == 0 else r_in
        pts.append((int(cx + r * math.cos(a)), int(cy + r * math.sin(a))))
    return pts


def _arrow_right(cx: float, cy: float, r: float) -> list[tuple[int, int]]:
    hw = max(1, r / 3)
    hd = max(1, r * 2 / 3)
    return [
        _p(cx, cy, -r, -hw),
        _p(cx, cy, r / 3, -hw),
        _p(cx, cy, r / 3, -hd),
        _p(cx, cy, r, 0),
        _p(cx, cy, r / 3, hd),
        _p(cx, cy, r / 3, hw),
        _p(cx, cy, -r, hw),
    ]


def _arrow_up(cx: float, cy: float, r: float) -> list[tuple[int, int]]:
    hw = max(1, r / 3)
    hd = max(1, r * 2 / 3)
    return [
        _p(cx, cy, -hw, r),
        _p(cx, cy, -hw, -r / 3),
        _p(cx, cy, -hd, -r / 3),
        _p(cx, cy, 0, -r),
        _p(cx, cy, hd, -r / 3),
        _p(cx, cy, hw, -r / 3),
        _p(cx, cy, hw, r),
    ]


# ── Per-icon draw functions ────────────────────────────────────────────────────
# Signature: (surf, cx, cy, r, col)  where r = size // 2

# ·· Perks ·····················································


def _vital_surge(s, cx, cy, r, c):
    """Heart."""
    pts = _heart_pts(cx, cy, r)
    if len(pts) >= 3:
        pygame.draw.polygon(s, c, pts)


def _swift_boots(s, cx, cy, r, c):
    """Lightning bolt."""
    pts = [
        _p(cx, cy, -r * 0.15, -r),
        _p(cx, cy, r * 0.40, -r),
        _p(cx, cy, 0, 0.1 * r),
        _p(cx, cy, r * 0.55, 0.1 * r),
        _p(cx, cy, -r * 0.40, r),
        _p(cx, cy, r * 0.05, 0),
        _p(cx, cy, -r * 0.50, 0),
    ]
    pygame.draw.polygon(s, c, pts)


def _power_draw(s, cx, cy, r, c):
    """Up arrow."""
    pygame.draw.polygon(s, c, _arrow_up(cx, cy, r))


def _rapid_fire(s, cx, cy, r, c):
    """Double right chevrons."""
    lw = max(2, r // 2)
    for dx in (-r * 0.30, r * 0.20):
        pts = [
            _p(cx, cy, dx - r * 0.35, -r * 0.65),
            _p(cx, cy, dx + r * 0.35, 0),
            _p(cx, cy, dx - r * 0.35, r * 0.65),
        ]
        pygame.draw.lines(s, c, False, pts, lw)


def _piercing_shot(s, cx, cy, r, c):
    """Arrow + pierce-marks behind shaft."""
    pygame.draw.polygon(s, c, _arrow_right(cx, cy, r))
    lw = max(1, r // 5)
    for dy in (-r * 0.55, r * 0.55):
        pygame.draw.line(s, _bright(c, 1.3), _p(cx, cy, -r * 0.8, dy), _p(cx, cy, -r * 0.2, dy), lw)


def _double_shot(s, cx, cy, r, c):
    """Two parallel arrows."""
    gap = max(2, r // 3)
    for dy in (-gap, gap):
        hw = max(1, r // 4)
        hd = max(1, r * 2 // 5)
        sl, sr = int(cx - r * 0.85), int(cx + r * 0.10)
        tip = int(cx + r * 0.85)
        pts = [
            (sl, int(cy + dy - hw)),
            (sr, int(cy + dy - hw)),
            (sr, int(cy + dy - hd)),
            (tip, int(cy + dy)),
            (sr, int(cy + dy + hd)),
            (sr, int(cy + dy + hw)),
            (sl, int(cy + dy + hw)),
        ]
        pygame.draw.polygon(s, c, pts)


def _dash_master(s, cx, cy, r, c):
    """Hollow diamond."""
    pts = [(int(cx), int(cy - r)), (int(cx + r), int(cy)), (int(cx), int(cy + r)), (int(cx - r), int(cy))]
    pygame.draw.polygon(s, c, pts)
    ri = max(1, int(r * 0.55))
    inner = [(int(cx), int(cy - ri)), (int(cx + ri), int(cy)), (int(cx), int(cy + ri)), (int(cx - ri), int(cy))]
    pygame.draw.polygon(s, _dim(c, 0.3), inner)


def _phantom_step(s, cx, cy, r, c):
    """Ghost silhouette (oval + wavy skirt + eye dots)."""
    pygame.draw.ellipse(s, c, (int(cx - r), int(cy - r), int(r * 2), int(r * 1.4)))
    n_bumps, bw = 3, r * 2 // 3
    for i in range(n_bumps):
        bx = int(cx - r + i * bw + bw // 2)
        pygame.draw.circle(s, c, (bx, int(cy + r * 0.3)), max(1, bw // 2))
    er = max(1, r // 5)
    for ex in (cx - r * 0.3, cx + r * 0.3):
        pygame.draw.circle(s, _dim(c, 0.15), (int(ex), int(cy - r * 0.15)), er)


def _iron_hide(s, cx, cy, r, c):
    """Armour plate (filled square + darker border + cross bolts)."""
    pygame.draw.rect(s, c, (int(cx - r), int(cy - r), int(r * 2), int(r * 2)))
    bw = max(1, r // 3)
    pygame.draw.rect(s, _dim(c, 0.4), (int(cx - r), int(cy - r), int(r * 2), int(r * 2)), bw)
    pygame.draw.line(s, _dim(c, 0.4), (int(cx - r * 0.5), int(cy)), (int(cx + r * 0.5), int(cy)), bw)
    pygame.draw.line(s, _dim(c, 0.4), (int(cx), int(cy - r * 0.5)), (int(cx), int(cy + r * 0.5)), bw)


def _swift_arrow(s, cx, cy, r, c):
    """Thin arrow + speed lines."""
    hw = max(1, r // 5)
    hd = max(1, int(r * 0.65))
    pts = [
        _p(cx, cy, -r, -hw),
        _p(cx, cy, r // 3, -hw),
        _p(cx, cy, r // 3, -hd),
        _p(cx, cy, r, 0),
        _p(cx, cy, r // 3, hd),
        _p(cx, cy, r // 3, hw),
        _p(cx, cy, -r, hw),
    ]
    pygame.draw.polygon(s, c, pts)
    lw = max(1, r // 6)
    for dy in (-r * 0.55, r * 0.55):
        pygame.draw.line(s, _bright(c, 1.3), _p(cx, cy, -r * 0.9, dy), _p(cx, cy, -r * 0.4, dy), lw)


def _coin_magnet(s, cx, cy, r, c):
    """Horseshoe magnet + coin."""
    lw = max(2, r // 3)
    ri = r - lw
    n = 10
    # Outer arch (π → 2π, i.e. left → top → right in screen coords)
    outer = [
        _p(cx, cy, r * math.cos(math.pi + math.pi * i / n), r * math.sin(math.pi + math.pi * i / n))
        for i in range(n + 1)
    ]
    # Inner arch (right → top → left)
    inner = [
        _p(cx, cy, ri * math.cos(2 * math.pi - math.pi * i / n), ri * math.sin(2 * math.pi - math.pi * i / n))
        for i in range(n + 1)
    ]
    # Arms going downward from arch endpoints
    arm_h = int(r * 0.65)
    arch_pts = (
        [_p(cx, cy, -r, 0), _p(cx, cy, -r, arm_h)]
        + [_p(cx, cy, -r + lw, arm_h), _p(cx, cy, -r + lw, 0)]
        + inner[n:][::-1]  # inner arch right end
        + [_p(cx, cy, r - lw, 0), _p(cx, cy, r - lw, arm_h)]
        + [_p(cx, cy, r, arm_h), _p(cx, cy, r, 0)]
        + outer
    )
    # Build proper winding polygon: left arm + outer arch + right arm + inner arch
    poly = (
        [_p(cx, cy, -r, arm_h), _p(cx, cy, -r, 0)]
        + outer
        + [_p(cx, cy, r, 0), _p(cx, cy, r, arm_h), _p(cx, cy, r - lw, arm_h), _p(cx, cy, r - lw, 0)]
        + inner[::-1]
        + [_p(cx, cy, -r + lw, 0), _p(cx, cy, -r + lw, arm_h)]
    )
    if len(poly) >= 3:
        pygame.draw.polygon(s, c, poly)
    # Coin below
    cr = max(2, r // 4)
    pygame.draw.circle(s, _bright(c, 1.15), (int(cx), int(cy + arm_h + cr + 1)), cr)


def _berserker(s, cx, cy, r, c):
    """8-ray starburst (rage)."""
    lw = max(1, r // 3)
    for i in range(8):
        a = math.pi * 2 * i / 8
        pygame.draw.line(
            s,
            c,
            (int(cx + r * 0.3 * math.cos(a)), int(cy + r * 0.3 * math.sin(a))),
            (int(cx + r * math.cos(a)), int(cy + r * math.sin(a))),
            lw,
        )
    pygame.draw.circle(s, c, (int(cx), int(cy)), max(2, r // 4))


# ·· Relics ····················································


def _wardens_mark(s, cx, cy, r, c):
    """Shield with cross."""
    pts = [
        _p(cx, cy, 0, -r),
        _p(cx, cy, r, -r * 0.40),
        _p(cx, cy, r * 0.80, r * 0.30),
        _p(cx, cy, 0, r),
        _p(cx, cy, -r * 0.80, r * 0.30),
        _p(cx, cy, -r, -r * 0.40),
    ]
    pygame.draw.polygon(s, c, pts)
    lw = max(1, r // 3)
    pygame.draw.line(s, _dim(c), (int(cx), int(cy - r * 0.5)), (int(cx), int(cy + r * 0.5)), lw)
    pygame.draw.line(s, _dim(c), (int(cx - r * 0.4), int(cy)), (int(cx + r * 0.4), int(cy)), lw)


def _echoing_shot(s, cx, cy, r, c):
    """Arc + arrowhead (echo arrow)."""
    lw = max(1, r // 3)
    arc_rect = (int(cx - r * 0.7), int(cy - r * 0.8), int(r * 1.4), int(r * 1.4))
    pygame.draw.arc(s, c, arc_rect, math.pi * 0.1, math.pi * 1.0, lw)
    # Arrowhead at left end
    hw = max(1, r // 3)
    tip = _p(cx, cy, -r * 0.70, r * 0.08)
    pygame.draw.polygon(
        s,
        c,
        [
            tip,
            _p(cx, cy, -r * 0.15, r * 0.08 - hw),
            _p(cx, cy, -r * 0.15, r * 0.08 + hw),
        ],
    )


def _venom_gland(s, cx, cy, r, c):
    """Poison drop (teardrop)."""
    cr = max(1, int(r * 0.65))
    pygame.draw.circle(s, c, (int(cx), int(cy - r * 0.15)), cr)
    pygame.draw.polygon(
        s,
        c,
        [
            _p(cx, cy, -r * 0.55, r * 0.12),
            _p(cx, cy, r * 0.55, r * 0.12),
            _p(cx, cy, 0, r),
        ],
    )


def _iron_lungs(s, cx, cy, r, c):
    """Three horizontal wind bars."""
    lw = max(1, r // 3)
    offsets = [(-r * 0.40, r * 0.15), (0, 0), (r * 0.40, r * 0.15)]
    for yo, xo in offsets:
        pygame.draw.line(s, c, (int(cx - r + xo), int(cy + yo)), (int(cx + r - xo), int(cy + yo)), lw)


def _bone_buckler(s, cx, cy, r, c):
    """Crossed bone (two dumbbells)."""
    br = max(1, r // 3)
    lw = max(1, r // 4)
    for (ax, ay), (bx, by) in [
        ((-r * 0.55, -r * 0.55), (r * 0.55, r * 0.55)),
        ((r * 0.55, -r * 0.55), (-r * 0.55, r * 0.55)),
    ]:
        pygame.draw.circle(s, c, (int(cx + ax), int(cy + ay)), br)
        pygame.draw.circle(s, c, (int(cx + bx), int(cy + by)), br)
        pygame.draw.line(
            s, c, (int(cx + ax * 0.80), int(cy + ay * 0.80)), (int(cx + bx * 0.80), int(cy + by * 0.80)), lw
        )


def _coin_fed_heart(s, cx, cy, r, c):
    """Small heart + offset coin."""
    sr = max(1, int(r * 0.62))
    pts = _heart_pts(int(cx - r * 0.2), cy, sr)
    if len(pts) >= 3:
        pygame.draw.polygon(s, c, pts)
    cr = max(1, r // 3)
    coin_col = _bright(c, 1.2)
    pygame.draw.circle(s, coin_col, (int(cx + r * 0.6), int(cy - r * 0.3)), cr)
    pygame.draw.circle(s, _dim(c, 0.4), (int(cx + r * 0.6), int(cy - r * 0.3)), cr, max(1, cr // 3))


def _shrapnel_tips(s, cx, cy, r, c):
    """Starburst explosion."""
    lw = max(1, r // 4)
    for i in range(8):
        a = math.pi * 2 * i / 8
        ri = r * (0.35 if i % 2 == 0 else 0.25)
        ro = r * (0.95 if i % 2 == 0 else 0.65)
        pygame.draw.line(
            s,
            c,
            (int(cx + ri * math.cos(a)), int(cy + ri * math.sin(a))),
            (int(cx + ro * math.cos(a)), int(cy + ro * math.sin(a))),
            lw,
        )
    pygame.draw.circle(s, c, (int(cx), int(cy)), max(2, r // 4))


def _phase_cloak(s, cx, cy, r, c):
    """Ghost (same as phantom_step — dodge/phase motif)."""
    _phantom_step(s, cx, cy, r, c)


def _leech_stone(s, cx, cy, r, c):
    """Blood drop (teardrop, rounded top)."""
    cr = max(1, int(r * 0.62))
    pygame.draw.circle(s, c, (int(cx), int(cy - r * 0.15)), cr)
    pygame.draw.polygon(
        s,
        c,
        [
            _p(cx, cy, -r * 0.50, r * 0.12),
            _p(cx, cy, r * 0.50, r * 0.12),
            _p(cx, cy, 0, r),
        ],
    )
    # Shine dot
    pygame.draw.circle(s, _bright(c, 1.4), (int(cx - r * 0.18), int(cy - r * 0.38)), max(1, r // 7))


def _overcharged_quiver(s, cx, cy, r, c):
    """Bold lightning bolt (larger/fatter than swift_boots)."""
    pts = [
        _p(cx, cy, -r * 0.10, -r),
        _p(cx, cy, r * 0.50, -r),
        _p(cx, cy, r * 0.05, 0),
        _p(cx, cy, r * 0.70, 0),
        _p(cx, cy, -r * 0.50, r),
        _p(cx, cy, r * 0.0, 0),
        _p(cx, cy, -r * 0.60, 0),
    ]
    pygame.draw.polygon(s, c, pts)


def _ancient_sigil(s, cx, cy, r, c):
    """4-pointed star."""
    pts = _star_pts(cx, cy, r, r * 0.32, n=4, offset=-math.pi / 2)
    pygame.draw.polygon(s, c, pts)
    pygame.draw.circle(s, _dim(c), (int(cx), int(cy)), max(1, r // 5))


def _echo_chamber(s, cx, cy, r, c):
    """Speaker triangle + three arcs."""
    # Speaker cone (trapezoid shifted left)
    ox = -r * 0.2
    pygame.draw.polygon(
        s,
        c,
        [
            _p(cx, cy, ox - r * 0.3, -r * 0.28),
            _p(cx, cy, ox + r * 0.1, -r * 0.60),
            _p(cx, cy, ox + r * 0.1, r * 0.60),
            _p(cx, cy, ox - r * 0.3, r * 0.28),
        ],
    )
    lw = max(1, r // 4)
    for ar in (r * 0.5, r * 0.72, r * 0.95):
        pygame.draw.arc(
            s, c, (int(cx + ox + r * 0.05), int(cy - ar), int(ar * 2), int(ar * 2)), -math.pi * 0.45, math.pi * 0.45, lw
        )


def _spiked_shell(s, cx, cy, r, c):
    """Circle with 6 triangular spikes."""
    cr = max(2, int(r * 0.60))
    for i in range(6):
        a = math.pi * 2 * i / 6
        b1 = a + math.pi * 0.22
        b2 = a - math.pi * 0.22
        pygame.draw.polygon(
            s,
            c,
            [
                (int(cx + r * math.cos(a)), int(cy + r * math.sin(a))),
                (int(cx + cr * math.cos(b1)), int(cy + cr * math.sin(b1))),
                (int(cx + cr * math.cos(b2)), int(cy + cr * math.sin(b2))),
            ],
        )
    pygame.draw.circle(s, c, (int(cx), int(cy)), cr)


def _temporal_blur(s, cx, cy, r, c):
    """Concentric partial arcs (spiral blur)."""
    lw = max(1, r // 3)
    for ar, start, span in [
        (r * 0.90, 0.15, math.pi * 1.70),
        (r * 0.58, 0.65, math.pi * 1.50),
        (r * 0.28, 1.10, math.pi * 1.30),
    ]:
        pygame.draw.arc(s, c, (int(cx - ar), int(cy - ar), int(ar * 2), int(ar * 2)), start, start + span, lw)


def _runic_arrows(s, cx, cy, r, c):
    """Arrow + rune-like tick marks on shaft."""
    pygame.draw.polygon(s, c, _arrow_right(cx, cy, r))
    lw = max(1, r // 4)
    for dx in (-r * 0.55, -r * 0.2):
        pygame.draw.line(s, _dim(c), (int(cx + dx), int(cy - r * 0.42)), (int(cx + dx), int(cy + r * 0.42)), lw)


def _bloodlust(s, cx, cy, r, c):
    """Flame (teardrop pointing up)."""
    cr = max(1, int(r * 0.65))
    pygame.draw.circle(s, c, (int(cx), int(cy + r * 0.12)), cr)
    pygame.draw.polygon(
        s,
        c,
        [
            _p(cx, cy, -r * 0.52, r * 0.12),
            _p(cx, cy, r * 0.52, r * 0.12),
            _p(cx, cy, 0, -r),
        ],
    )
    # Inner flicker
    pygame.draw.circle(s, _bright(c, 1.4), (int(cx), int(cy + r * 0.18)), max(1, cr // 2))


def _curse_of_greed(s, cx, cy, r, c):
    """Skull (oval + eye sockets + teeth)."""
    pygame.draw.ellipse(s, c, (int(cx - r), int(cy - r), int(r * 2), int(r * 1.55)))
    bg = _dim(c, 0.10)
    er = max(1, r // 4)
    pygame.draw.circle(s, bg, (int(cx - r * 0.38), int(cy - r * 0.12)), er)
    pygame.draw.circle(s, bg, (int(cx + r * 0.38), int(cy - r * 0.12)), er)
    tw = max(1, r // 4)
    for i in range(-1, 2):
        pygame.draw.rect(s, bg, (int(cx + i * r * 0.36 - tw // 2), int(cy + r * 0.38), tw, int(r * 0.38)))


def _petrified_heart(s, cx, cy, r, c):
    """Blocky stone heart."""
    pts = [
        _p(cx, cy, -r, -r * 0.10),
        _p(cx, cy, -r * 0.10, -r),
        _p(cx, cy, r * 0.10, -r),
        _p(cx, cy, r, -r * 0.10),
        _p(cx, cy, r, r * 0.45),
        _p(cx, cy, 0, r),
        _p(cx, cy, -r, r * 0.45),
    ]
    pygame.draw.polygon(s, c, pts)
    lw = max(1, r // 5)
    pygame.draw.line(
        s, _dim(c, 0.40), (int(cx - r * 0.3), int(cy - r * 0.25)), (int(cx + r * 0.1), int(cy + r * 0.40)), lw
    )


def _hunters_mark(s, cx, cy, r, c):
    """Bullseye (3 concentric circles)."""
    pygame.draw.circle(s, c, (int(cx), int(cy)), r)
    lw = max(1, r // 4)
    pygame.draw.circle(s, _dim(c, 0.2), (int(cx), int(cy)), int(r * 0.68), lw)
    pygame.draw.circle(s, _dim(c, 0.2), (int(cx), int(cy)), int(r * 0.38), lw)
    pygame.draw.circle(s, _dim(c, 0.15), (int(cx), int(cy)), max(1, r // 6))


def _void_core(s, cx, cy, r, c):
    """Dark disc with glowing ring."""
    pygame.draw.circle(s, _dim(c, 0.25), (int(cx), int(cy)), r)
    lw = max(1, r // 3)
    pygame.draw.circle(s, c, (int(cx), int(cy)), r, lw)
    pygame.draw.circle(s, _dim(c, 0.65), (int(cx), int(cy)), int(r * 0.52), max(1, lw // 2))


# ── Icon registry ──────────────────────────────────────────────────────────────

_ICONS: dict[str, object] = {
    # Perks
    "vital_surge": _vital_surge,
    "swift_boots": _swift_boots,
    "power_draw": _power_draw,
    "rapid_fire": _rapid_fire,
    "piercing_shot": _piercing_shot,
    "double_shot": _double_shot,
    "dash_master": _dash_master,
    "phantom_step": _phantom_step,
    "iron_hide": _iron_hide,
    "swift_arrow": _swift_arrow,
    "coin_magnet": _coin_magnet,
    "berserker": _berserker,
    # Relics
    "wardens_mark": _wardens_mark,
    "echoing_shot": _echoing_shot,
    "venom_gland": _venom_gland,
    "iron_lungs": _iron_lungs,
    "bone_buckler": _bone_buckler,
    "coin_fed_heart": _coin_fed_heart,
    "shrapnel_tips": _shrapnel_tips,
    "phase_cloak": _phase_cloak,
    "leech_stone": _leech_stone,
    "overcharged_quiver": _overcharged_quiver,
    "ancient_sigil": _ancient_sigil,
    "echo_chamber": _echo_chamber,
    "spiked_shell": _spiked_shell,
    "temporal_blur": _temporal_blur,
    "runic_arrows": _runic_arrows,
    "bloodlust": _bloodlust,
    "curse_of_greed": _curse_of_greed,
    "petrified_heart": _petrified_heart,
    "hunters_mark": _hunters_mark,
    "void_core": _void_core,
    # Shared alias for the heart-vial shop item
    "heart_vial": _vital_surge,
}


# ── Public API ─────────────────────────────────────────────────────────────────


def draw(surf: pygame.Surface, cx: int, cy: int, size: int, icon_id: str, color: tuple) -> None:
    """Draw icon centred at (cx, cy) inside a *size × size* bounding box."""
    r = max(1, size // 2)
    fn = _ICONS.get(icon_id)
    if fn is not None:
        fn(surf, cx, cy, r, tuple(color[:3]))
    else:
        # Fallback: question-mark box outline
        pygame.draw.rect(surf, color, (cx - r, cy - r, r * 2, r * 2), max(1, r // 4))


def surface(size: int, icon_id: str, color: tuple) -> pygame.Surface:
    """Return a cached *size × size* SRCALPHA Surface with the icon on it."""
    key = (size, icon_id, tuple(color[:3]))
    if key not in _cache:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        draw(surf, size // 2, size // 2, size, icon_id, color)
        _cache[key] = surf
    return _cache[key]
