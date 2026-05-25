# Verdant Depths

A roguelite dungeon crawler set in overgrown forest ruins. Fight through 7 floors of increasingly dangerous enemies, collect perks and relics, and face powerful bosses in your way to the depths.

Built with [pygame-ce](https://pyga.me/) for the May 2026 Game Jam.

---

## Install & Run

**Requirements:** Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone https://github.com/clementw168/gamejam-may-2026.git
cd gamejam-may-2026
uv run verdant-depths
```

**Key layout options** (default: ZQSD):

```bash
uv run verdant-depths --keys wasd
uv run verdant-depths --keys arrows
```

---

## How to Play

### Goal

Clear all rooms on each floor, defeat the boss, pick a relic, and descend — 7 floors total. Reach the bottom to win.

### Controls

| Input | Action |
|---|---|
| ZQSD / WASD / Arrows | Move |
| Mouse | Aim |
| Left Click | Shoot arrow |
| Space | Dash (invincible while dashing) |
| R | Return to menu after death or victory |
| Esc | Quit |

### Core loop

- **Rooms** — each room spawns enemies; clear them all to open the doors and earn an upgrade (perk)
- **Boss gate** — the boss room is locked until every other room on the floor is cleared
- **Boss** — defeating the floor boss lets you pick a **relic** before descending
- **Shop** — one room per floor sells HP and a perk for coins; enemies drop coins on death
- **Upgrades** — after each room clear, choose 1 of 3 perks (speed, damage, dash, etc.)
- **Relics** — powerful passive items picked after each boss; stack and synergise across the run


---

## Game Modes

### Story (default)
7 floors, progressive difficulty. Unlocks perks in every room and a relic after each boss.

### Arena (`A` from menu)
Practice mode — pick any enemy (or boss) and an optional relic, then fight. No coins, no progression.

### Endless (`E` from menu)
Infinite waves in a sealed room. Every 5-wave cycle rewards HP, perks, and relics. Pick a starting wave to skip ahead if you want a harder start.

---

## Bosses

| Floor | Boss | Notes |
|---|---|---|
| 1–2 | Goblin Shaman | Bolt bursts + runner summons |
| 3 | Ancient Tree | Root sprays + thorn rings; stationary |
| 4 | Iron Warden | Stomp AoE + shrapnel; patrols |
| 5 | Abyssal Leech | Homing tendrils that heal it on hit |
| 6 | Fungal Matriarch | Spore volleys + SporeElder summons; healing aura |
| 7 | Void Sovereign | 8-way bursts + Wraith summons; arena shrinks in Phase 2 |

All bosses have a Phase 2 triggered at half HP — the HP bar turns orange as a warning.
