"""Upgrade perks — one of three is offered after every room clear.

Each Perk carries an `apply(player)` callback that mutates the Player's
per-run stats directly.  Constants in constants.py serve as base values;
perks scale from wherever the player currently stands (stackable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from player import Player


@dataclass
class Perk:
    id: str
    name: str
    desc: str
    icon: str  # single emoji / symbol shown on card
    apply: Callable[[Player], None]


# ── Individual perk functions ─────────────────────────────────────────────────


def _vital_surge(p: Player) -> None:
    """Add a max heart and heal 1."""
    p.max_hp += 1
    p.hp = min(p.hp + 1, p.max_hp)


def _swift_boots(p: Player) -> None:
    """25 % faster movement."""
    p.speed *= 1.25


def _power_draw(p: Player) -> None:
    """Arrows deal 1 extra damage."""
    p.arrow_damage += 1


def _rapid_fire(p: Player) -> None:
    """30 % shorter shoot cooldown."""
    p.shoot_cooldown *= 0.70


def _piercing_shot(p: Player) -> None:
    """Arrows pass through all enemies."""
    p.piercing = True


def _double_shot(p: Player) -> None:
    """Every click fires two arrows."""
    p.double_shot = True


def _dash_master(p: Player) -> None:
    """30 % shorter dash cooldown."""
    p.dash_cooldown *= 0.70


def _phantom_step(p: Player) -> None:
    """Dash travels 30 % further (longer duration)."""
    p.dash_duration *= 1.30


def _iron_hide(p: Player) -> None:
    """Invincibility window after a hit +0.4 s."""
    p.iframes_dur += 0.40


def _swift_arrow(p: Player) -> None:
    """Arrow travel speed +35 %."""
    p.arrow_speed *= 1.35


def _coin_magnet(p: Player) -> None:
    """Coin pull radius ×2.5."""
    p.magnet_range *= 2.5


def _berserker(p: Player) -> None:
    """Dash speed +25 %."""
    p.dash_speed *= 1.25


# ── Pool ──────────────────────────────────────────────────────────────────────

PERK_POOL: list[Perk] = [
    Perk("vital_surge", "Vital Surge", "+1 max heart. Restore 1 HP.", "♥", _vital_surge),
    Perk("swift_boots", "Swift Boots", "+25% movement speed.", "⚡", _swift_boots),
    Perk("power_draw", "Power Draw", "Arrows deal +1 damage.", "↑", _power_draw),
    Perk("rapid_fire", "Rapid Fire", "Shoot cooldown -30%.", "»", _rapid_fire),
    Perk("piercing_shot", "Piercing Shot", "Arrows pierce through all enemies.", "→", _piercing_shot),
    Perk("double_shot", "Double Shot", "Each click fires two arrows.", "«", _double_shot),
    Perk("dash_master", "Dash Master", "Dash cooldown -30%.", "◇", _dash_master),
    Perk("phantom_step", "Phantom Step", "Dash travels 30% further.", "~", _phantom_step),
    Perk("iron_hide", "Iron Hide", "Invincibility after hit +0.4 s.", "■", _iron_hide),
    Perk("swift_arrow", "Swift Arrow", "Arrow speed +35%.", "▶", _swift_arrow),
    Perk("coin_magnet", "Coin Magnet", "Coin pull radius ×2.5.", "$", _coin_magnet),
    Perk("berserker", "Berserker", "Dash speed +25%.", "☁", _berserker),
]
