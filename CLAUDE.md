# Verdant Depths — Game Jam 2026

Roguelite dungeon crawler, forest-ruins theme. Built with pygame-ce.

## Run

```
uv run verdant-depths [--keys arrows|wasd|zqsd]
```

## Architecture

| File | Responsibility |
|---|---|
| `constants.py` | All magic numbers (screen size, colours, speeds, radii, boss stats) |
| `config.py` | Runtime config — key layout (`--keys` flag) |
| `sounds.py` | Procedural audio synthesis + asset file override |
| `main.py` | pygame init, mixer pre-init, `sounds.init()`, game loop |
| `game.py` | State machine: **MENU** / PLAYING ↔ TRANSITIONING / UPGRADE / SHOP / FLOOR_CLEAR / RELIC / VICTORY / DEAD / **ARENA_SELECT** / **ARENA_RELIC_SELECT** / **ARENA** / ARENA_WIN / ARENA_DEAD / **ENDLESS_SELECT** / **ENDLESS** / ENDLESS_BETWEEN / ENDLESS_DEAD; dungeon nav, gate blocking, coin drops, floor progression, boss spawn, summon drain, pack wave roll, run-stats tracking, high-score I/O |
| `camera.py` | World↔screen transform + screen shake |
| `rooms.py` | Tile grid, 9 templates (5 base + 4 underground-ruin), collision, `find_spawn_near_centre`, door tile cuts, `get_spawn_positions` with `exclude_pos` |
| `dungeon.py` | DFS room graph, BFS boss detection, floor-weighted template selection |
| `player.py` | Movement, dash (SPACE, i-frames), shoot (LMB), per-run stats, relic flags |
| `perks.py` | 12 `Perk` dataclasses; each has `apply(player)` callback |
| `enemies.py` | All 13 regular enemies + 6 bosses + SporeElder elite; `Enemy` base with `_steer_toward`, `_move`, `tick_status`, status effect timers |
| `relics.py` | 20 `Relic` dataclasses; each has `apply(player)` callback; `RELIC_POOL` list |
| `projectiles.py` | Arrow (speed/damage/piercing/bouncing/overcharged kwargs, `hit_enemies` set), EnemyProjectile (homing, leech_owner flags) |
| `particles.py` | Lightweight particle pool, named presets (inc. boss death/phase-2 bursts) |
| `ui.py` | HUD, minimap (20×11 px cells), **main menu**, death/victory/floor-clear/relic screens, upgrade chooser, shop screen, **boss HP bar**, **boss-gate hint**, **arena relic select** |

## Layout

- Screen: 1280×720
- Tile: 32 px — room is exactly 40×20 tiles = 1280×640
- Bottom 80 px = HUD strip
- Border wall: **1 tile thick** (row 0 / row 19 / col 0 / col 39)
- Door opening: 3 tiles wide, centred — cols 19–21 (N/S) or rows 9–11 (E/W)
- Camera offset = (0, 0) per room; shake handled by `Camera`; smooth-step pan during TRANSITIONING

## Dungeon

- DFS random walk from (0,0) → `max(5, floor+4)`–`min(14, floor+6)` rooms per floor, tree topology
- Boss room = BFS-farthest node from start (follows actual door connections); shop room = random non-start, non-boss room
- Room transitions: PLAYING → TRANSITIONING (0.38 s smooth-step pan) → PLAYING (or SHOP)
- Template selection: F1 draws from templates 0–4; each deeper floor unlocks one more (up to all 9 at F5+)
- Minimap: top-right overlay; gold = current, green = cleared, red = boss, teal = shop

## Door rules

- **Closed** (room not cleared): gate bars drawn flush with the border tile; player blocked at wall face
- **Open** (room cleared): player walks through; exit triggers when centre crosses wall face threshold
- Exit detection checks **lateral position** to prevent wall-corner false triggers
- **Boss gate**: blocks movement until ALL non-boss rooms cleared; shows extra bars + hint tooltip on bump

## Enemies

| Enemy | Type | Floor | Notes |
|---|---|---|---|
| GoblinRunner | melee chaser | all | `_steer_toward` wall-aware movement; HP 3+; 2 coins |
| GoblinArcher | ranged | all | keeps distance, wind-up telegraph; floor-scaled |
| Wolf | melee flanker | all | wobble + `_steer_toward` approach; 175 px/s speed, 550 px/s lunge, 1.0 s CD; lunges at any range whenever CD ready; 2 coins |
| SporePlant | stationary ranged | all | alternating 4-way volleys (0°/45°); HP 5+ |
| SporeElder | stationary ranged elite | **5+** | 8-way simultaneous volleys + 6-spore cloud every 7 s; HP 18+; 7 coins |
| **StoneCrawler** | armoured melee | **4+** | First 3 arrows deflected back at player at full `ARROW_SPEED`; 2 dmg contact; `_steer_toward`; HP 8+; 4 coins |
| **VenomfangBat** | fast erratic melee | **4+** | Arc wobble + erratic wander blend; 1 dmg; HP 2; 3 coins |
| **CrystalTurret** | stationary ranged | **5+** | Rapid-fires fast aimed shots at player (380 px/s, 0.45 s CD, 0.25 s wind-up); HP 10+; 2 coins |
| **ShadowWraith** | teleporting caster | **5+** | Teleports every 4 s; 2-way homing projectiles; HP 4; 5 coins |
| **BoneArcher** | ranged | **6+** | 3-way spread; every 4th shot = 3-way bone spike volley (dmg 2 each, slow, large); HP 4+; 4 coins |
| **MagmaSlug** | slow melee | **6+** | 2 dmg contact; drops large BurnPatch (r=48) every 0.8 s (1 dmg/s, 8 s lifetime); `_steer_toward`; HP 14+; 6 coins |
| **VoidShrieker** | fast erratic melee | **7** | Erratic wander blend; 8-way death burst; void flash on attack; HP 3; 6 coins |

### Enemy movement system (`enemies.py`)

- **`Enemy._steer_toward(tx, ty, room)`** — 8-direction wall-aware probe (scores by goal alignment − wall penalty); returns `(vx, vy)` at `self.speed`. Used by GoblinRunner, Wolf (approach), StoneCrawler, MagmaSlug.
- **Erratic blend** (VenomfangBat, VoidShrieker) — `_wander_angle` shifts ±90° every 0.6 s; movement = 70% steered + 30% wander, then existing wobble applied on top.

### Status effects (`Enemy.tick_status`)

Poison · Slow · Burn · Stun · Bleed timers on every enemy. DoT ticks every 0.5 s; stun freezes movement; slow ×0.4 speed. Colour-coded status rings drawn around affected enemies. Applied by: Venom Gland relic (poison), Phase Cloak relic (stun), MagmaSlug BurnPatch (burn via `game.py`).

### Spawn system (`game.py`)

- **`_spawn_wave`** — mixed enemy table indexed by floor; counts scale F1–F7; accepts `exclude_pos` to keep enemies ≥200 px from player entry point
- **`_pack_wave`** — 20% chance from floor 2+; spawns 3–7 of one type (runner/wolf always; bat F4+; turret F5+; shrieker F7)
- **Entry grace period** — 0.5 s iframes granted on every room transition commit (ancient_sigil bumps to 1.0 s)

### Target run structure

| Floor | Rooms | Boss |
|---|---|---|
| 1 | 5–7 | Goblin Shaman |
| 2 | 6–8 | Goblin Shaman (harder) |
| 3 | 7–9 | Ancient Tree |
| 4 | 8–10 | Iron Warden |
| 5 | 9–11 | Abyssal Leech |
| 6 | 10–12 | Fungal Matriarch |
| 7 | 11–13 | Void Sovereign |

## Bosses

All bosses: `is_boss_enemy = True`, `boss_name`, `_phase2` property, `phase2_just_triggered` flag, `_summon_queue`, `_phase2_shake` class attr. HP bar drawn by `ui.draw_boss_hpbar()` (red P1 → orange P2).

| Boss | Floor | HP | Key attacks | Phase 2 change |
|---|---|---|---|---|
| **Goblin Shaman** | 1–2 | 20/26 | 3-way bolt burst + 2 runner summons | 5-way burst, summons archer, pulsing aura |
| **Ancient Tree** | 3 | 30 | 6-root spray (300° arc, random jitter, aimed at player) + 10-thorn ring (random rotation offset) + 3-shot aimed burst; stationary | 9 roots, 14+14-thorn double ring, 5-shot burst, faster CDs |
| **Iron Warden** | 4 | 40 | Stomp AoE (60 px, 1.0s CD) + 4-way shrapnel; patrols | Stomp CD 0.6s, 8-way shrapnel |
| **Abyssal Leech** | 5 | 35 | 3 homing tendrils (heals 3 HP if hit) + 6-way burst; stationary P1 | Moves, 6 tendrils, burst CD halved |
| **Fungal Matriarch** | 6 | 50 | 5-way spore volley + SporeElder summons; passive 0.5 HP/s aura ≤80 px | Faster fire, alternates SporeElder/VenomfangBat summons |
| **Void Sovereign** | 7 | 70 | 5-way burst + 2× ShadowWraith summons; orbits | 8-way burst, VoidShrieker summons, void-field border shrinks arena |

## Sounds (10 tracks, procedurally synthesised)

`shoot` · `dash` · `hit_enemy` · `enemy_death` · `player_hurt` · `coin` ·
`room_clear` · `wolf_lunge` · `spore_shoot` · `hit_wall`

Override any track: drop `<name>.ogg` (or `.wav`) in `src/gamejam_may_2026/assets/sounds/`.

## Controls

| Key | Action |
|---|---|
| ZQSD / WASD / Arrow | Move (default ZQSD, override with `--keys`) |
| Mouse | Aim |
| Left Click | Shoot arrow |
| Space | Dash (i-frames; cooldown arc shows recharge) |
| R | Return to menu after death / victory |
| C | View Codex (from main menu) |
| A | Arena Mode (from main menu) |
| E | Endless Mode (from main menu) |
| Esc | Quit |

### Arena Mode controls (ARENA_SELECT screen)

| Key | Action |
|---|---|
| Arrow keys | Navigate enemy grid |
| `-` / `=` | Decrease / increase enemy count |
| Mouse scroll | Decrease / increase enemy count |
| Enter / Space | Proceed to relic select |
| Esc | Back to menu |

### Arena Mode controls (ARENA_RELIC_SELECT screen)

| Key | Action |
|---|---|
| Arrow keys | Navigate relic grid |
| Enter / Space | Confirm selection and start fight |
| Esc | Back to enemy select |

## Perks (12 total — `perks.py`)

All perk state lives on `Player` as per-run instance attributes. One-shot perks (Piercing Shot, Double Shot) are filtered from the offer pool once applied.

| Perk | Effect |
|---|---|
| Vital Surge | +1 max heart, restore 1 HP |
| Swift Boots | +25% movement speed |
| Power Draw | arrows deal +1 damage |
| Rapid Fire | shoot cooldown −30% |
| Piercing Shot | arrows pierce through all enemies (one-shot) |
| Double Shot | each click fires two arrows (one-shot) |
| Dash Master | dash cooldown −30% |
| Phantom Step | dash travels 30% further |
| Iron Hide | invincibility after hit +0.4 s |
| Swift Arrow | arrow speed +35% |
| Coin Magnet | coin pull radius ×2.5 |
| Berserker | dash speed +25% |

Upgrade screen: dim overlay + 3 randomly sampled cards; pick with click or `1`/`2`/`3`. Shown after every room clear except the starting room. 250 ms click grace period on open.

## Relics (20 total — `relics.py`)

Pick 1 of 2 offered after each floor boss (`RELIC` state between `FLOOR_CLEAR` and floor advance). Icons shown in HUD strip.

| Relic | Icon | Effect |
|---|---|---|
| Warden's Mark | 🛡 | +2 max HP; start each floor at half HP |
| Echoing Shot | ↩ | Arrow kills spawn a reflected arrow toward nearest enemy ≤300 px |
| Venom Gland | 🐍 | Arrows apply Poison (1 HP/s, 4 s) |
| Iron Lungs | 💨 | Dash cooldown −50%; dash deals 1 contact damage |
| Bone Buckler | 🦴 | First hit each room absorbed; `block_charge` reset on room entry |
| Coin-Fed Heart | 💰 | Every 10 coins collected restores 1 HP |
| Shrapnel Tips | 💥 | Arrow wall-impact emits 3 mini-shrapnel (±30° fan) |
| Phase Cloak | 👻 | Dashing through an enemy stuns it for 0.8 s |
| Leech Stone | 🩸 | Every 5 kills restores 1 HP |
| Overcharged Quiver | ⚡ | Every 4th arrow deals ×3 damage |
| Ancient Sigil | ✦ | Room entry grants 1 s invincibility |
| Echo Chamber | 🔊 | Coin magnet range ×3 |
| Spiked Shell | 🦔 | Taking damage deals 2 to all enemies within 80 px |
| Temporal Blur | 🌀 | Dash leaves 2 afterimage clones (each absorbs 1 hit) |
| Runic Arrows | 🔮 | Arrows bounce once off walls |
| Bloodlust | 🔥 | Kill → +10% speed for 3 s (stacks ×3) |
| Curse of Greed | 💀 | Enemies drop 2× coins; start each floor with 0 coins |
| Petrified Heart | 🗿 | Cannot overheal; take 50% less damage |
| Hunter's Mark | 🎯 | First enemy hit per room takes ×3 damage |
| Void Core | 🌑 | Every 5 s, emit damaging 8-way pulse from player |

## Shop

- One room per floor (never start, never boss); entered automatically on transition
- **Slot 1** Heart Vial — restore 1 HP, 5 coins (reusable while HP < max)
- **Slots 2–3** — two random perks (filtered for already-applied one-shots), 8 coins each
- Press `1`/`2`/`3` to buy; `Space` to leave; shop re-opens on re-entry

## Floor progression

- 7 floors total; boss room on each floor
- Boss gate: bars + movement block until all non-boss rooms cleared
- Boss cleared → `FLOOR_CLEAR` overlay → `RELIC` pick → floor advances (new `Dungeon`, `room_num` resets, player stats preserved)
- Floor 7 boss cleared → `VICTORY` screen

## Endless Mode

Accessible from the main menu with `E`. No coins, no shop, no floor structure — pure wave survival.

### States
- `ENDLESS_SELECT` — wave-selection screen (pick starting multiple of 5: 0, 5, 10 … 35)
- `ENDLESS` — sealed room combat (all doors locked, full relic/perk effects active)
- `ENDLESS_BETWEEN` — between-wave overlay (rewards displayed; Space to continue)
- `ENDLESS_DEAD` — player died; press R to return to menu

### 5-wave cycle structure
| Wave in cycle | Reward |
|---|---|
| 1 | +1 HP |
| 2 | +1 HP + choose a perk |
| 3 | +1 HP |
| 4 | +1 HP |
| 5 (boss) | Full HP restore + choose a relic |

### Difficulty scaling
- Virtual floor = `min(7, 1 + cycle)` where cycle is 0-indexed (wave 1–5 = cycle 0, wave 6–10 = cycle 1 …)
- Room depth = `min(3, position_in_cycle + 1)` → enemy composition uses existing `_spawn_wave(room, vfloor, depth)`
- Boss waves scale by **generation** (complete 7-boss rotations): gen 0 = 1 boss, gen 1 = 2 bosses, gen 2+ = 3 bosses (capped). Each wave picks `slot = cycle % 7` and spawns floors `[slot+1, (slot+1)%7+1, …]` spread across the room.
- After cycle 6 (wave 35+), room_depth stays at 3 but vfloor keeps climbing (uncapped): enemy HP/speed scale every cycle, and counts scale +20% per floor above 7

### Starting from a higher wave
- Player selects a multiple of 5 (e.g. 10); first fight is wave 11
- Pre-selects N/5 perks + N/5 relics before combat starts (using existing UPGRADE/RELIC screens)
- `_endless_mode = True` flag causes `_pick_perk`/`_pick_relic` to return to endless flow instead of `PLAYING`
- Pre-pick queue: `['perk', 'relic']` × cycles_completed; processed one at a time before first wave

### Selection screen controls
| Key | Action |
|---|---|
| ◄ / ► (or Left/Right arrows) | Decrease / increase starting wave by 5 |
| Space / Enter | Start fight |
| Esc | Back to menu |

## High score & menus

- **State flow**: `MENU` → any key → `PLAYING`; death/victory `R` → `MENU`
- **Menu screen**: title, tagline, controls table, best-run panel
- **Run stats**: floors reached, rooms cleared (combat only), coins collected (gross), elapsed time
- **Death / victory overlays**: full stats + "✦ NEW BEST RUN! ✦" banner when applicable
- **High score file**: `~/.verdant-depths/highscore.json`; comparison: floors → rooms → coins

## Room templates (`rooms.py`)

9 templates in `TEMPLATES` list. Floor-weighted unlock: F1 uses templates 0–4; each deeper floor adds one more.

| Index | Name | Description |
|---|---|---|
| 0 | arena | Open with corner pillars + centre rock |
| 1 | columns | Six slender columns symmetrically placed |
| 2 | lshapes | L-shaped rubble in four inner corners |
| 3 | maze | Two horizontal wall segments with gaps |
| 4 | island | Large centre island + side cover rocks |
| 5 | corridor | Vertical dividers with 3-tile choke passages (F2+) |
| 6 | pit_ring | Large impassable central pit, ring walkway (F3+) |
| 7 | rubble_heap | Asymmetric scatter of wall blocks (F4+) |
| 8 | pillars_dense | 12 single-tile sight-breaking pillars (F5+) |

## Coin economy

### Enemy coin drops

All regular enemies drop a **flat 2 coins** to reduce room-to-room variance and simplify balancing. Bosses keep themed values.

| Type | Drop |
|---|---|
| All regular enemies | **2** |
| Goblin Shaman | 10 |
| Ancient Tree | 15 |
| Iron Warden | 18 |
| Abyssal Leech | 20 |
| Fungal Matriarch | 22 |
| Void Sovereign | 30 |

### Expected income per floor

Computed from: `randint(max(5, F+4), min(14, F+6))` total rooms → subtract 3 (start + shop + boss) combat rooms; assume depth-3 wave for all but first 2 rooms.

| Floor | Rooms (avg) | Combat rooms | Enemies/room | Coins/room | ~Floor income |
|---|---|---|---|---|---|
| 1 | 6 | 3 | 5 | 10 | 40 |
| 2 | 7 | 4 | 7 | 14 | 66 |
| 3 | 8 | 5 | 10 | 20 | 115 |
| 4 | 9 | 6 | 12 | 24 | 162 |
| 5 | 10 | 7 | 17 | 34 | 258 |
| 6 | 11 | 8 | 20 | 40 | 342 |
| 7 | 12 | 9 | 27 | 54 | 516 |

### Shop prices (per floor, `constants.py` `SHOP_HP_PRICE` / `SHOP_PERK_PRICE`)

Shop has **1 HP Vial** (reusable while HP < max) + **1 Perk card** — 2 slots, forcing a trade-off. Both items together target ≈ 50–85 % of expected floor income.

Prices set so HP + Perk ≈ expected floor income (30/70 split). Clearing all combat rooms lets you afford exactly one of each.

| Floor | Income | HP Vial | Perk | Total |
|---|---|---|---|---|
| 1 | 40 | 10 | 30 | 40 |
| 2 | 66 | 20 | 45 | 65 |
| 3 | 115 | 35 | 80 | 115 |
| 4 | 162 | 50 | 115 | 165 |
| 5 | 258 | 75 | 180 | 255 |
| 6 | 342 | 105 | 240 | 345 |
| 7 | 516 | 155 | 360 | 515 |

### Relic healing per floor (post-nerf)

| Floor | Coin-Fed Heart (100c/HP) | Leech Stone (50 kills/HP) |
|---|---|---|
| 1 | 0.4 HP | 0.3 HP |
| 2 | 0.7 HP | 0.6 HP |
| 3 | 1.2 HP | 1.0 HP |
| 4 | 1.6 HP | 1.5 HP |
| 5 | 2.6 HP | 2.4 HP |
| 6 | 3.4 HP | 3.2 HP |
| 7 | 5.2 HP | 4.9 HP |

## Known issues (all fixed)

| # | Issue | Fix |
|---|---|---|
| 1 | ~~Flag-based perks offered again after applied~~ | `_available_perks(player)` filters `piercing_shot`/`double_shot` before sampling |
| 2 | ~~Minimap cells too small (14×7 px)~~ | `CW, CH` bumped to 20×11 in `ui.draw_minimap` |
| 3 | ~~GoblinShaman double HP bar~~ | Removed redundant bars; `ui.draw_boss_hpbar()` is sole source of truth |

## Arena Mode

Accessible from the main menu with `A`. A standalone 1v1 (or 1vN) practice mode — no perks, no shop, no floor progression. One optional relic can be chosen before each fight.

### States
- `ARENA_SELECT` — enemy selection screen (6×3 grid of all 18 enemies)
- `ARENA_RELIC_SELECT` — relic pick screen (choose 1 relic or go in with none)
- `ARENA` — sealed room fight (all doors locked, no upgrades/coins)
- `ARENA_WIN` — all enemies defeated overlay
- `ARENA_DEAD` — player died overlay

### Selection screen (`game.py: _ARENA_ENTRIES`, `ui.py: draw_arena_select`)
- 12 regular enemies + 6 bosses
- Count 1–`max_count` (regular max 4–10; boss max 2–3)
- Arrow keys to navigate; `-`/`=` or mouse scroll to change count; Enter/Space → goes to relic select

### Relic select screen (`game.py: _handle_arena_relic_select_event`, `ui.py: draw_arena_relic_select`)
- Full grid of all 20 relics + a "No Relic" option (default)
- Click or arrow-key to select; Enter/Space to confirm and start the fight
- Esc returns to enemy select; clicking a card immediately starts the fight

### Arena fight (`game.py: _update_arena`)
- Fresh `Player` (3 HP, no perks) each fight; chosen relic is applied via `relic.apply(player)`
- All relic effects active: Venom Gland, Echoing Shot, Leech Stone, Bloodlust, etc.
- Uses a `Dungeon(floor=1)` start room; all doors permanently locked
- Boss HP bar shown for boss enemies; HUD shows `⚔ EnemyName ×N` label
- Boss summons (Shaman, Matriarch, Sovereign) work normally
- Burn patches, spore auras, void field all active
- `ARENA_WIN` when enemies list empties; `ARENA_DEAD` when player HP = 0
- Press `R` to return to main menu from either result screen

## Design ideas (not implemented)

| Idea | Description |
|---|---|
| **Rebound enemy** | Dashes toward player the moment it takes a hit — punishes reckless shooting |
| **Mid-dash steering** | Blend held movement keys into dash direction at ~30%/frame during active window |
