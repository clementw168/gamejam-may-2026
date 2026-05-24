"""Relic system — one relic offered (pick 1 of 2) after each floor boss is cleared.

Relics are more powerful, permanent upgrades than perks.  Like perks, each relic
carries an `apply(player)` callback that mutates the Player's run-state directly.
More complex relic effects (e.g. coin_fed_heart, spiked_shell) are checked in
`game.py`'s update loops where the relevant game objects are accessible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from gamejam_may_2026.player import Player


@dataclass
class Relic:
    id:    str
    name:  str
    desc:  str
    icon:  str                      # single emoji / symbol shown on card
    apply: Callable[[Player], None]


# ── Individual relic apply functions ─────────────────────────────────────────

def _wardens_mark(p: Player) -> None:
    """Add 2 max HP, but start each floor at half HP (tracked by wardens_mark flag)."""
    p.max_hp += 2
    p.hp = min(p.hp + 2, p.max_hp)
    p.wardens_mark = True


def _echoing_shot(p: Player) -> None:
    """Arrow kills spawn a reflected arrow aimed at the nearest enemy ≤ 300 px."""
    p.echoing_shot = True


def _venom_gland(p: Player) -> None:
    """Arrows apply Poison (Day 12 effect: 1 HP/s for 4 s) to enemies hit."""
    p.arrow_poison = True


def _iron_lungs(p: Player) -> None:
    """Dash cooldown −50 %; dashing through enemies deals 1 contact damage."""
    p.dash_cooldown *= 0.50
    p.iron_lungs = True


def _bone_buckler(p: Player) -> None:
    """First hit each room is absorbed (block_charge = 1, reset on room entry)."""
    p.bone_buckler = True
    p.block_charge = 1


def _coin_fed_heart(p: Player) -> None:
    """Restore 1 HP every 100 coins collected."""
    p.coin_fed_heart = True


def _shrapnel_tips(p: Player) -> None:
    """On arrow wall-impact, emit 3 mini-shrapnel in a ±30° fan."""
    p.shrapnel_tips = True


def _phase_cloak(p: Player) -> None:
    """Dashing through an enemy stuns it for 0.8 s."""
    p.phase_cloak = True


def _leech_stone(p: Player) -> None:
    """Killing 50 enemies restores 1 HP."""
    p.leech_stone = True


def _overcharged_quiver(p: Player) -> None:
    """Every 4th arrow fired deals triple damage."""
    p.overcharged_quiver = True


def _ancient_sigil(p: Player) -> None:
    """Entering a new room grants 1 s of invincibility."""
    p.ancient_sigil = True


def _echo_chamber(p: Player) -> None:
    """Coin magnet range ×3."""
    p.magnet_range *= 3.0


def _spiked_shell(p: Player) -> None:
    """Taking damage deals 2 to all enemies within 80 px."""
    p.spiked_shell = True


def _temporal_blur(p: Player) -> None:
    """Dashing leaves 2 afterimage clones that each absorb 1 enemy projectile."""
    p.temporal_blur = True


def _runic_arrows(p: Player) -> None:
    """Arrows bounce once off walls before expiring."""
    p.runic_arrows = True


def _bloodlust(p: Player) -> None:
    """Killing an enemy grants +10 % speed for 3 s (stacks up to ×3)."""
    p.bloodlust = True


def _curse_of_greed(p: Player) -> None:
    """Enemies drop 2× coins; you start each floor with 0 coins."""
    p.curse_of_greed = True


def _petrified_heart(p: Player) -> None:
    """Cannot be healed above current max HP; take 50 % less damage."""
    p.petrified_heart = True


def _hunters_mark(p: Player) -> None:
    """The first enemy hit per room takes 3× damage."""
    p.hunter_mark = True


def _void_core(p: Player) -> None:
    """Every 10 s, emit a damaging 8-way pulse from the player's position."""
    p.void_core = True
    p._void_t = 10.0   # schedule first pulse


# ── Pool ──────────────────────────────────────────────────────────────────────

RELIC_POOL: list[Relic] = [
    Relic("wardens_mark",      "Warden's Mark",      "+2 max HP. Each floor starts at half HP.", "🛡", _wardens_mark),
    Relic("echoing_shot",      "Echoing Shot",       "Arrow kills spawn a reflected arrow at the nearest foe ≤300 px.", "↩", _echoing_shot),
    Relic("venom_gland",       "Venom Gland",        "Arrows poison enemies on hit (1 HP/s, 4 s).", "🐍", _venom_gland),
    Relic("iron_lungs",        "Iron Lungs",         "Dash cooldown −50 %. Dashing through enemies deals 1 damage.", "💨", _iron_lungs),
    Relic("bone_buckler",      "Bone Buckler",       "First hit each room is completely absorbed.", "🦴", _bone_buckler),
    Relic("coin_fed_heart",    "Coin-Fed Heart",     "Restore 1 HP for every 100 coins picked up.", "💰", _coin_fed_heart),
    Relic("shrapnel_tips",     "Shrapnel Tips",      "Arrow wall-impacts release 3 shrapnel in a ±30° fan.", "💥", _shrapnel_tips),
    Relic("phase_cloak",       "Phase Cloak",        "Dashing through an enemy stuns it for 0.8 s.", "👻", _phase_cloak),
    Relic("leech_stone",       "Leech Stone",        "Restore 1 HP after killing 50 enemies.", "🩸", _leech_stone),
    Relic("overcharged_quiver","Overcharged Quiver", "Every 4th arrow fired deals triple damage.", "⚡", _overcharged_quiver),
    Relic("ancient_sigil",     "Ancient Sigil",      "Entering a new room grants 1 s of invincibility.", "✦", _ancient_sigil),
    Relic("echo_chamber",      "Echo Chamber",       "Coin magnet range ×3.", "🔊", _echo_chamber),
    Relic("spiked_shell",      "Spiked Shell",       "Taking damage deals 2 to all enemies within 80 px.", "🦔", _spiked_shell),
    Relic("temporal_blur",     "Temporal Blur",      "Dash leaves 2 afterimage clones, each absorbing 1 hit.", "🌀", _temporal_blur),
    Relic("runic_arrows",      "Runic Arrows",       "Arrows bounce once off walls before expiring.", "🔮", _runic_arrows),
    Relic("bloodlust",         "Bloodlust",          "Each kill grants +10 % speed for 3 s (stacks ×3).", "🔥", _bloodlust),
    Relic("curse_of_greed",    "Curse of Greed",     "Enemies drop 2× coins. Start each floor with 0 coins.", "💀", _curse_of_greed),
    Relic("petrified_heart",   "Petrified Heart",    "Cannot over-heal. Take 50 % less damage.", "🗿", _petrified_heart),
    Relic("hunters_mark",      "Hunter's Mark",      "The first enemy hit per room takes 3× damage.", "🎯", _hunters_mark),
    Relic("void_core",         "Void Core",          "Every 10 s, emit a damaging 8-way pulse.", "🌑", _void_core),
]
