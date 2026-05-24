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
| `game.py` | State machine: **MENU** / PLAYING ↔ TRANSITIONING / UPGRADE / SHOP / FLOOR_CLEAR / VICTORY / DEAD; dungeon nav, gate blocking, coin drops, floor progression, boss spawn, summon drain, run-stats tracking, high-score I/O |
| `camera.py` | World↔screen transform + screen shake |
| `rooms.py` | Tile grid, 5 templates, collision, `find_spawn_near_centre`, door tile cuts |
| `dungeon.py` | DFS room graph (5–7 rooms), BFS boss detection (connection-graph BFS), `DungeonRoom` nodes |
| `player.py` | Movement, dash (SPACE, i-frames), shoot (LMB), per-run stats (speed/damage/…), sounds |
| `perks.py` | 12 `Perk` dataclasses; each has `apply(player)` callback |
| `enemies.py` | GoblinRunner, GoblinArcher, Wolf, SporePlant, **GoblinShaman**, **AncientTree** + Enemy base; StoneCrawler, VenomfangBat, CrystalTurret, ShadowWraith, BoneArcher, MagmaSlug, VoidShrieker |
| `relics.py` | 20 `Relic` dataclasses; each has `apply(player)` callback; `RELIC_POOL` list |
| `projectiles.py` | Arrow (speed/damage/piercing kwargs, hit_enemies set), EnemyProjectile |
| `particles.py` | Lightweight particle pool, named presets (inc. boss death/phase-2 bursts) |
| `ui.py` | HUD, minimap, **main menu**, death/victory/floor-clear screens (with run stats + high score), upgrade chooser, shop screen, **boss HP bar**, **boss-gate hint** |

## Layout

- Screen: 1280×720
- Tile: 32 px — room is exactly 40×20 tiles = 1280×640
- Bottom 80 px = HUD strip
- Border wall: **1 tile thick** (row 0 / row 19 / col 0 / col 39)
- Door opening: 3 tiles wide, centred — cols 19–21 (N/S) or rows 9–11 (E/W)
- Camera offset = (0, 0) per room; shake handled by `Camera`; smooth-step pan during TRANSITIONING

## Dungeon

- DFS random walk from (0,0) → `max(5,floor+4)`–`min(14,floor+6)` rooms per floor, tree topology
- Boss room = BFS-farthest node from start (**BFS follows actual door connections, not raw grid adjacency**); shop room = random non-start, non-boss room
- Each `DungeonRoom` tracks: `visited`, `cleared`, `is_start`, `is_boss`, `is_shop`, `connections`, `shop_items`
- Room transitions: PLAYING → TRANSITIONING (0.38 s smooth-step pan) → PLAYING (or SHOP for shop rooms)
- Minimap: top-right overlay; gold = current, green = visited/cleared, red = boss, **teal = shop**
- 7 floors total; advancing requires clearing the boss room; player stats persist across floors

## Door rules

- **Closed** (room not cleared): gate bars drawn flush with the border tile; player blocked at wall face (`ts + radius = 44 px`) **only inside the door opening** — tile walls handle the rest
- **Open** (room cleared): player walks through; exit triggers when centre enters the 3-tile opening AND crosses the wall face threshold
- Exit detection checks **lateral position** (x for N/S, y for E/W) to prevent wall-corner false triggers
- **Boss gate**: door leading to boss room shows extra bars and blocks movement until ALL non-boss rooms are cleared; unlocks automatically once met
- **Boss-gate hint**: bumping a boss-locked door while the room is cleared shows a fading tooltip — *"⚔  Clear every room to open the gate"* — for 2.5 s

## Enemies

| Enemy | Type | Floor | Notes |
|---|---|---|---|
| GoblinRunner | melee chaser | all | straight-line rush, contact damage; HP 3/4/5, speed ~88/95/102 across floors |
| GoblinArcher | ranged | all | keeps distance, wind-up telegraph before shot |
| Wolf | melee flanker | all | wobble approach + lunge dash when ≤130 px; HP 2/3/4 |
| SporePlant | stationary ranged | all | alternating 4-way spore volleys (0°/45°); HP 5/7/9 |
| **StoneCrawler** | melee chaser | **4+** | Armoured: first 3 arrow hits deflected (shell ring + pips); 2 dmg/contact; HP 8+; drops 4 coins |
| **VenomfangBat** | fast melee | **4+** | Arc wobble movement (120 px/s perp.); poisons player for 3 s on contact; HP 2; drops 3 coins |
| **CrystalTurret** | stationary ranged | **5+** | Rotating 3-way crystal volleys; immune from front ±60°, double damage from back; HP 10+; drops 5 coins |
| **ShadowWraith** | teleporting caster | **5+** | Teleports every 4 s (>300 px from player); fires 2-way homing projectiles; HP 4; drops 5 coins |
| **BoneArcher** | ranged | **6+** | 3-way spread every 1.4 s; every 4th shot is a slow bone spike (dmg 2); HP 4+; drops 4 coins |
| **MagmaSlug** | slow melee | **6+** | 2 dmg contact; drops orange burn patches every 0.5 s (1 dmg/s while standing); HP 14+; drops 6 coins |
| **VoidShrieker** | fast melee | **7** | Erratic high-speed movement; void flash + camera shake on attack; 8-way death burst; HP 3; drops 6 coins |
| **GoblinShaman** | **boss** | **1–2** | Bolt bursts + minion summons; 2 phases; see below |
| **AncientTree** | **boss** | **3** | Root volleys + thorn rings; 2 phases; see below |

### Spawn progression (`_spawn_wave` in `game.py`)

| Room | Enemies |
|---|---|
| 1 | 2 runners + 1 wolf |
| 2 | + 1 archer |
| 3+ | + 1 spore plant |
| Floor 2+ | counts scale up; HP/speed scale via `floor` kwarg |

All enemy constructors accept `floor=N` (default 1); `_spawn_wave` passes the current floor.

## Bosses

### Goblin Shaman (floors 1–2)

- HP 20 (floor 1) / 26 (floor 2), radius 22, orbits player at 120–200 px
- **Phase 1**: 3-way magic bolt burst (25° spread, 2.2 s CD, 0.5 s wind-up); summons 2 GoblinRunners every 10 s
- **Phase 2** (≤ 50 % HP): 5-way burst (40° spread, 1.5 s CD, 0.35 s wind-up); summons 2 runners + 1 archer every 6 s; pulsing purple aura
- Staff arm rotates to track player; telegraph = expanding purple circle
- Phase-2 transition: `emit_shaman_phase2` burst + 14 px camera shake
- Drops 10 coins

### Ancient Tree (floor 3)

- HP 30, radius 30, **stationary** (spawns at room centre), speed 0
- **Attack 1 – Root burst**: 4-way (P1) / 8-way (P2) slow brown projectiles alternating 0°/45°; 2.5 s / 1.8 s CD; 0.7 s wind-up (brown glow)
- **Attack 2 – Thorn ring**: 8 fast green thorns in a full ring; P2 adds a second offset ring of 8; 5.0 s / 3.5 s CD; 0.85 s wind-up (green glow)
- Slowly-rotating root-tendril decoration
- Phase-2 transition: `emit_tree_phase2` burst + 14 px camera shake
- Drops 15 coins

### Boss HP bar

Centred 380×14 px bar near the top of the playfield (y = 10), with boss name label above.  
Colour: red (phase 1) → orange (phase 2). Drawn by `ui.draw_boss_hpbar()`.

### Summon system

`GoblinShaman` holds a `_summon_queue: list[Enemy]`.  
After each enemy-update loop in `game.py`, the queue is drained into `self.enemies` so summoned minions are treated as normal enemies (room only clears when **all** — boss + minions — are dead).

## Sounds (10 tracks, procedurally synthesised)

`shoot` · `dash` · `hit_enemy` · `enemy_death` · `player_hurt` · `coin` ·
`room_clear` · `wolf_lunge` · `spore_shoot` · `hit_wall`

Override any track: drop `<name>.ogg` (or `.wav`) in `src/gamejam_may_2026/assets/sounds/`.

## Day plan

| Day | Status | What was built |
|---|---|---|
| 1 | ✅ done | Player (move/dash/shoot), GoblinRunner, GoblinArcher, 5 room templates, particles, camera shake, HUD, coin drops |
| 2 | ✅ done | Wolf (wobble + lunge), SporePlant (4-way volleys), 10 procedural sounds, coin magnet, `--keys` flag, room-num-based spawn progression |
| 3 | ✅ done | Dungeon graph (DFS/BFS), room transitions (smooth-step pan), door gates, minimap, door bug fixes (lateral check, wall-face blocking) |
| 4 | ✅ done | Upgrade/perk selection screen (12 perks, UPGRADE state, piercing arrows, double-shot, per-run Player stats) |
| 5 | ✅ done | 3 floors, boss-gate, shop room (HP vial + 2 perks for coins), FLOOR_CLEAR / VICTORY states, teal minimap for shop |
| 6 | ✅ done | Goblin Shaman + Ancient Tree bosses (2-phase, bolt/summon/root/thorn), boss HP bar, balance pass (floor-scaled enemy HP/speed), BFS deadlock fix, upgrade-click grace period, boss-gate hint tooltip |
| 7 | ✅ done | Main menu (title + controls + best run), run-summary death/victory screens (floor/rooms/coins/time), high score (`~/.verdant-depths/highscore.json`, floors→rooms→coins sort) |
| 8 | ✅ done | **Floor expansion** — 7 floors total; per-floor room count `max(5,floor+4)–min(14,floor+6)`; `_spawn_wave` table extended to floors 4–7; `GoblinArcher` floor-scaled; victory/UI strings updated to `/7` |
| 9 | ✅ done | **New enemies A** — StoneCrawler (armoured melee, deflect shell), VenomfangBat (fast arc mover, applies Poison on contact), CrystalTurret (rotating 3-laser volley, vulnerable from behind); added to `_spawn_wave` floors 4–5; fixed GoblinShaman/AncientTree double HP bar |
| 10 | ✅ done | **New enemies B** — ShadowWraith (teleporting homing-shot caster), BoneArcher (3-way spread + bone spike every 4th shot), MagmaSlug (slow melee + burn-patch DoT floor hazard), VoidShrieker (death burst + void-flash vignette on attack); added floors 5–7; `BurnPatch` class in `game.py`; homing projectile steering in `_update_playing` |
| 11 | ✅ done | **Relic system** — `relics.py` (20 relics); `RELIC` state between `FLOOR_CLEAR` and floor advance (pick 1 of 2 cards); `player.relics` list + icon strip in HUD; all 20 relic effects wired (bone_buckler, temporal_blur clones, runic arrows bounce, void core pulse, overcharged quiver, bloodlust speed, curse of greed, echoing shot, leech stone, spiked shell, hunter's mark, shrapnel tips, phase cloak, coin-fed heart, ancient sigil, petrified heart, wardens mark, iron lungs, venom gland, echo chamber) |
| 12 | 🔜 next | **Status effects** — Poison, Slow, Burn, Stun, Bleed on `Enemy` base class (`tick_status(dt, particles)`) and Burn/Poison on `Player`; coloured status rings in draw; `arrow_poison`, `dash_stun`, `thorns` player flags |
| 13 | 🔜 | **New bosses** — IronWarden (F4, stomp + shrapnel + charge), AbyssalLeech (F5, HP-stealing tendrils), FungalMatriarch (F6, summon Spore Elders + Bats), VoidSovereign (F7, shrinking void field + 8-way bursts) |
| 14 | 🔜 | **Room templates + polish** — 3–4 new underground templates (tight corridor, circular pit, asymmetric rubble, flooded chamber); balance pass floors 4–7; menu tagline updated; final high-score `/7` display |

## Controls

| Key | Action |
|---|---|
| ZQSD / WASD / Arrow | Move (default ZQSD, override with `--keys`) |
| Mouse | Aim |
| Left Click | Shoot arrow |
| Space | Dash (i-frames; cooldown arc shows recharge) |
| R | Return to menu after death / victory |
| Esc | Quit |

## Known Issues

| # | Symptom | Location | Notes |
|---|---|---|---|
| 1 | Flag-based perks (e.g. Piercing Shot, Double Shot) can be offered again after already being applied — the perk pool isn't filtered by what the player already has | `game.py` `_update_playing` / `perks.py` | Fix: before `random.sample(PERK_POOL, 3)` in chest spawn and shop generation, exclude perks whose flag is already `True` on `player` |
| 2 | Minimap cells are too small (14×7 px cells + 2 px gap) — unreadable in practice | `ui.py` `draw_minimap` | Increase `CW`, `CH` and/or `STRIDE_*`; consider scaling based on dungeon extents so large floors don't push it off-screen |
| 3 | ~~GoblinShaman (pink boss) shows a **double HP bar**~~ | ✅ **Fixed (Day 9)** | Removed redundant HP bars from both `GoblinShaman.draw` and `AncientTree.draw`; `ui.draw_boss_hpbar()` is the single source of truth |

## Design Ideas

| Idea | Description |
|---|---|
| **Rebound enemy** | A melee enemy that dashes very fast directly toward the player the moment it takes a hit — punishes reckless up-close shooting; pairs well with the dash i-frame mechanic |
| **Mid-dash direction change** | Allow the player to steer the dash direction during its active window (especially relevant with Phantom Step / longer dashes); one approach: blend current dash dir with held movement keys at ~30 % per frame during the dash |

## Perks (12 total — `perks.py`)

All perk state lives on `Player` as per-run instance attributes (never touches module constants).

| Perk | Effect |
|---|---|
| Vital Surge | +1 max heart, restore 1 HP |
| Swift Boots | +25% movement speed |
| Power Draw | arrows deal +1 damage |
| Rapid Fire | shoot cooldown −30% |
| Piercing Shot | arrows pass through all enemies |
| Double Shot | 2 arrows per click (slight spread) |
| Dash Master | dash cooldown −30% |
| Phantom Step | dash travels 30% further |
| Iron Hide | invincibility window after hit +0.4 s |
| Swift Arrow | arrow speed +35% |
| Coin Magnet | coin pull radius ×2.5 |
| Berserker | dash speed +25% |

Upgrade screen: dim overlay + 3 randomly sampled cards; pick with click or keys `1`/`2`/`3`.  
Shown after every room clear **except** room 1 (the starting room).  
**250 ms click grace period** on open — prevents shoot-click from silently picking a perk.

## Shop (`is_shop` room)

- One room per floor randomly selected (never start, never boss)
- Entered automatically on transition; shop overlay shown immediately
- **Slot 1** Heart Vial — restore 1 HP, 5 coins (reusable while HP < max)
- **Slots 2–3** — two random perks from pool, 8 coins each, one-time purchase
- Minimap: teal cell with small cyan dot
- Press `1`/`2`/`3` to buy; `Space` to leave; shop re-opens on re-entry

## Floor progression

- 3 floors total; boss room on each floor
- Boss gate: door leading to boss shows bars + blocks movement until all non-boss rooms cleared
- Boss cleared → `FLOOR_CLEAR` overlay; `Space` advances to next floor (new `Dungeon`, `room_num` resets, player stats preserved)
- Floor 3 boss cleared → `VICTORY` screen; `R` to return to menu

## Main menu & high score (Day 7)

- **State flow**: game starts in `MENU`; any key → `_new_game()` → `PLAYING`; death/victory `R` → `MENU`
- **Menu screen** (`ui.draw_menu`): title, tagline, controls table, best-run panel
- **Run stats tracked per run**: floors reached, rooms cleared (combat only, not shop), coins collected (gross total, not current), elapsed time
- **Death / victory overlays** now show full stats + "✦ NEW BEST RUN! ✦" banner when applicable
- **High score file**: `~/.verdant-depths/highscore.json` — best run saved on run end; comparison is floors → rooms → coins (time is informational only)

---

# Roadmap — 2-hour run target

## Enemy enhancements (cross-cutting, applies to Days 9–14)

Three quality-of-life and depth improvements that touch `enemies.py`, `rooms.py`, and `game.py`.

### 1 · Pack encounters

Some rooms spawn a single enemy type in large numbers instead of the usual mixed wave. This creates distinct combat *feels* per room — a swarm of bats plays completely differently from the usual mixed group.

**Design:**  
`_spawn_wave` gains a `pack_chance` roll (e.g., 20 % from floor 2+). On a pack roll, instead of the mixed table, spawn 4–7 of one randomly chosen type appropriate to that floor. Examples:

| Pack | Enemies | Why it's interesting |
|---|---|---|
| Wolf pack | 5–7 Wolves | Coordinated lunge timing overwhelms the player |
| Bat swarm | 6–8 VenomfangBats | Fast arcs from all sides; constant Poison threat |
| Turret farm | 3–4 CrystalTurrets | Overlapping rotating-laser coverage |
| Shrieker choir | 5 VoidShriekers | Layered death bursts punish clustering |
| Runner mob | 6–8 GoblinRunners | Pure speed; kiting test |

**Implementation:**  
Add a `_pack_wave(room, floor, pack_type)` helper alongside `_spawn_wave`. `_commit_transition` calls one or the other based on the roll. Pack rooms award +2 coins per enemy to compensate difficulty.

---

### 2 · Safe spawn distance

Entering a room and immediately taking damage because an enemy spawned inside the player is the most jarring unfairness in the current build. Two complementary fixes:

**Fix A — minimum spawn distance from player entry point**  
`room.get_spawn_positions(count, min_dist_from_centre=200.0)` currently keeps enemies away from the room centre, which coincidentally protects the player when entering from the boss fight (centre spawn). But when entering from a door, the player appears near a wall and enemies can be right next to them.

Change: add a `min_dist_from_point(px, py, min_dist)` filter to `get_spawn_positions`:

```python
def get_spawn_positions(self, count, min_dist_from_centre=200.0,
                        exclude_pos=None, exclude_dist=200.0):
    ...
    candidates = [
        (px, py) for (px, py) in candidates
        if exclude_pos is None or
           (px - exclude_pos[0])**2 + (py - exclude_pos[1])**2 >= exclude_dist**2
    ]
```

Pass `exclude_pos=(player.x, player.y)` from `_spawn_wave` (thread the player entry position through `_commit_transition`).

**Fix B — entry grace period (0.5 s iframes on room entry)**  
Even with safe spawns, the player can walk into a waiting enemy. Give the player 0.5 s of iframes immediately after any room transition commits. In `_commit_transition`, after placing the player:

```python
self.player._iframes = max(self.player._iframes, 0.5)   # grace period
```

The `_iframes` mechanism already exists in `Player` (used after taking a hit) — this is a one-liner.

---

### 3 · Smarter + more varied movement

Current enemies walk in a straight line toward the player and get stuck on walls or pillars. Two improvement layers:

**Layer A — obstacle steering (all melee enemies)**  
Each frame, instead of moving directly toward the player, sample **8 candidate directions** (45° apart). Score each by:

```
score(dir) = dot(dir, to_player_unit) − wall_penalty(dir)
```

`wall_penalty(dir)` is 1.0 if the tile 1.5× radius ahead in that direction is a wall, else 0.0. Pick the direction with the highest score. This makes enemies flow around pillars and through corridors naturally without a full pathfinder.

```python
def _steer_toward(self, tx, ty, room):
    """Return (vx, vy) steering around walls toward target (tx, ty)."""
    import math
    dx, dy = tx - self.x, ty - self.y
    dist = math.hypot(dx, dy) or 1.0
    goal = (dx / dist, dy / dist)
    best_score, best_dir = -2.0, goal
    for i in range(8):
        angle = i * math.pi / 4
        d = (math.cos(angle), math.sin(angle))
        probe_x = self.x + d[0] * self.radius * 2
        probe_y = self.y + d[1] * self.radius * 2
        tx2, ty2 = int(probe_x // C.TILE_SIZE), int(probe_y // C.TILE_SIZE)
        wall_hit = (0 <= tx2 < C.ROOM_TILE_W and 0 <= ty2 < C.ROOM_TILE_H and
                    room.tiles[ty2][tx2] == C.TILE_WALL)
        score = d[0]*goal[0] + d[1]*goal[1] - (1.0 if wall_hit else 0.0)
        if score > best_score:
            best_score, best_dir = score, d
    return best_dir[0] * self.speed, best_dir[1] * self.speed
```

Replace `dx/dy` direct movement in `GoblinRunner`, `Wolf` (between lunges), `StoneCrawler`, `MagmaSlug` with `_steer_toward`. Keep the base class implementation; ranged/stationary enemies don't use it.

**Layer B — erratic movement patterns (per-enemy personality)**  
Some enemies deliberately move unpredictably. Implement as an `_erratic` flag + a `_wander_angle` offset that drifts over time:

```python
# In Enemy.__init__ for erratic types:
self._erratic = True
self._wander_angle: float = random.uniform(0, math.pi * 2)
self._wander_t: float = 0.0

# In update, before steering:
if self._erratic:
    self._wander_t += dt
    if self._wander_t > 0.6:           # change wander direction every 0.6 s
        self._wander_t = 0.0
        self._wander_angle += random.uniform(-math.pi/2, math.pi/2)
    vx, vy = self._steer_toward(...)
    # blend: 70% toward player, 30% wander
    wx = math.cos(self._wander_angle)
    wy = math.sin(self._wander_angle)
    vx, vy = vx * 0.7 + wx * self.speed * 0.3, vy * 0.7 + wy * self.speed * 0.3
```

**Enemy movement personalities:**

| Enemy | Movement style | Notes |
|---|---|---|
| GoblinRunner | Direct (uses `_steer_toward`) | Predictable but wall-aware |
| GoblinArcher | Strafe + distance-keep | Already has pref-dist logic; add lateral drift |
| Wolf | Wobble approach (existing) → `_steer_toward` between lunges | Current wobble math kept; steering only during approach |
| SporePlant | Stationary | No movement |
| VenomfangBat | Erratic (`_erratic = True`, large wander amplitude) | Fast + unpredictable = hardest to dodge |
| ShadowWraith | Teleport-only | No frame-to-frame movement |
| MagmaSlug | `_steer_toward` only, very slow | Predictable but relentless |
| VoidShrieker | Erratic (`_erratic = True`, high speed) | Chaos incarnate |
| GoblinRunner pack | Same steering, but `_wander_angle` initialised differently per instance so the pack fans out | Avoids the "conga line" problem where all runners stack on the same path |

## Target run structure

| Floor | Rooms | Enemy density | Boss |
|---|---|---|---|
| 1 | 6–8 | 2 runners + 1 wolf | Goblin Shaman |
| 2 | 7–9 | + archer | Goblin Shaman (harder) |
| 3 | 8–10 | + spore plant | Ancient Tree |
| 4 | 9–11 | + StoneCrawler, VenomfangBat | Iron Warden |
| 5 | 10–12 | + CrystalTurret, ShadowWraith | Abyssal Leech |
| 6 | 11–13 | + BoneArcher, MagmaSlug | Fungal Matriarch |
| 7 | 12–14 | + VoidShrieker, SporeElder | Void Sovereign |

Per-floor room count formula: `random.randint(floor + 4, floor + 6)`, capped at 14.  
Full-run room estimate: ~70–80 rooms × 1.4 min avg = **~100–112 min** (calibrate to hit ~2 h).

## Floor expansion (Day 8)

**`dungeon.py`**  
- `target = random.randint(max(5, floor + 4), min(14, floor + 6))` (replaces hard-coded `5, 7`)

**`game.py`**  
- Victory condition: `floor >= 7` (was `>= 3`)
- `_spawn_wave`: extend FL table to index 7; scale runner/wolf/archer/plant counts for floors 4–7
- Enemy HP/speed multipliers per floor: `HP *= 1 + (floor - 1) * 0.18`, `speed *= 1 + (floor - 1) * 0.07`

**`ui.py`**  
- Replace all `/ 3` in stat displays with `/ 7`
- `draw_floor_clear`: "Descending to floor N…"

## New enemies (Days 9–10)

All new enemies live in `enemies.py`, accept `floor=1` kwarg, follow the existing `Enemy` base pattern.  
`_spawn_wave` in `game.py` adds them for the appropriate `fl` range.

### StoneCrawler (floor 4+)
- HP `8 + (floor-4)*2`, radius 16, speed `55 + (floor-4)*5`
- Melee chaser; deals **2 damage** per contact hit
- Has `_shell_hits: int = 3` — first 3 arrow hits in any iframes window deal 0 damage (deflect; visual: bright grey ring flash). After 3 deflects `_shell_hits` resets on next room entry.
- Drops 4 coins

### VenomfangBat (floor 4+)
- HP 2, radius 10, speed `160 + (floor-4)*8`
- Arc movement: `vx/vy` wobbled by `±sin(t * 4) * 120` on the perpendicular axis (same math as Wolf wobble, larger amplitude)
- On contact: applies **Poison** to player for 3 s; no projectiles
- Drops 3 coins

### CrystalTurret (floor 5+)
- HP `10 + (floor-5)*3`, radius 18, speed 0 (stationary)
- Fires 3-way volley every 2.5 s; volley angle advances +15° each shot (rotating laser ring)
- **Front-face** direction marker drawn on body; arrows from within ±60° of front deal 0 damage; arrows from behind deal double damage (check `math.atan2(arrow.y - self.y, arrow.x - self.x)` vs `self._face_angle`)
- Drops 5 coins

### ShadowWraith (floor 5+)
- HP 4, radius 13, speed 0 (teleports)
- Every 4 s: blinks to a random floor tile >300 px from player (uses `room.get_spawn_positions`)
- Fires 2-way homing projectiles every 2 s; each tick the projectile's `vx/vy` rotates 3° toward player
- Drops 5 coins

### BoneArcher (floor 6+)
- HP `4 + (floor-6)*2`, radius 12, speed 55
- Fires 3-way spread (±20°) every 1.4 s
- Every 4th shot fires a slow **bone spike**: damage 2, speed 140, lifetime 3.5 s (tracked by `_shot_counter`)
- Drops 4 coins

### MagmaSlug (floor 6+)
- HP `14 + (floor-6)*3`, radius 16, speed 45
- Slow melee chaser; deals 2 damage per contact
- Every 0.5 s drops a **BurnPatch** at current position: drawn as orange circle (radius 20 px), lasts 4 s, deals 1 damage/s to player if overlap distance < 20 px
- `BurnPatch` objects managed in `game.py` alongside `coins` (list drained each frame)
- Drops 6 coins

### VoidShrieker (floor 7)
- HP 3, radius 11, speed 140
- On any attack: add 4 px camera shake + brief screen-edge dark flash
- **Death burst**: on `hp <= 0`, fires 8 EnemyProjectiles in a full ring before `alive = False`
- Drops 6 coins

### SporeElder (floor 5+, elite SporePlant)
- Subclass of SporePlant; overrides `_NUM_SPOKES = 8` (8-way simultaneous volleys at 0° AND 45°)
- HP `18 + (floor-5)*3`, same radius/speed as SporePlant
- Periodically emits 6 random-angle spores (slow, lifetime 5 s) — "spore cloud" volley every 7 s
- Drops 7 coins

## Relic system (Day 11)

New file: **`relics.py`** — mirrors `perks.py` structure.

```python
@dataclass
class Relic:
    name:  str
    desc:  str
    icon:  str
    apply: Callable[[Player], None]
```

`Player` gains `self.relics: list[Relic] = []` (for HUD display strip).  
New game state: **`RELIC`** — inserted between `FLOOR_CLEAR` and floor advance.

**State flow:**  
`FLOOR_CLEAR` (Space) → `RELIC` (pick 1 of 2 presented) → apply relic → floor advances

**UI:** `ui.draw_relic_screen(surf, relics, hovered)` — reuses `_upgrade_card_rect` geometry, 2 cards only.  
HUD: small relic icon row below the hearts (up to 7 icons, one per floor cleared).

### Relic pool (20 relics)

| Relic | Icon | Effect |
|---|---|---|
| Warden's Mark | 🛡 | +2 max HP; start each floor at half HP |
| Echoing Shot | ↩ | Arrow kills spawn a reflected arrow aimed at nearest enemy ≤300 px |
| Venom Gland | 🐍 | Arrows apply Poison (1 HP/s, 3 s) to enemies hit |
| Iron Lungs | 💨 | Dash cooldown −50%; dash deals 1 contact damage to enemies passed through |
| Bone Buckler | 🦴 | First hit each room is absorbed completely (`block_charge = 1`, reset on room entry) |
| Coin-Fed Heart | 💰 | Picking up 10 coins restores 1 HP |
| Shrapnel Tips | 💥 | On arrow wall-impact, emit 3 mini-shrapnel in ±30° fan from impact point |
| Phase Cloak | 👻 | Dashing through an enemy stuns it for 0.8 s |
| Leech Stone | 🩸 | Killing 5 enemies restores 1 HP |
| Overcharged Quiver | ⚡ | Every 4th arrow deals triple damage |
| Ancient Sigil | ✦ | Entering a new room grants 1 s of invincibility |
| Echo Chamber | 🔊 | Coin magnet range ×3 |
| Spiked Shell | 🦔 | Taking damage deals 2 to all enemies within 80 px |
| Temporal Blur | 🌀 | Dash leaves 2 afterimage clones that each absorb 1 hit |
| Runic Arrows | 🔮 | Arrows bounce once off walls before expiring |
| Bloodlust | 🔥 | Killing an enemy grants +10% speed for 3 s (stacks ×3) |
| Curse of Greed | 💀 | Enemies drop 2× coins; you start each floor with 0 coins |
| Petrified Heart | 🗿 | Cannot heal above current max HP; take 50% less damage |
| Hunter's Mark | 🎯 | First enemy hit per room takes 3× damage |
| Void Core | 🌑 | Every 10 s, emit a damaging 8-way pulse from player position |

**Implementation anchors:**
- `apply(player)` sets flags like `player.arrow_poison = True`, checked in `game.py`'s arrow-collision block
- Arrow-bounce: in `Arrow.update`, on `TILE_WALL` hit, reflect `vx/vy` if `not self._bounced`; set `self._bounced = True`
- Void pulse: `player._void_t` countdown in `Player.update`; fires synthetic projectiles into `enemy_projectiles` list (or a separate `player_aoe` list to avoid friendly-fire confusion)
- Echoing shot: in `_drop_coins` (or the death block), if `player.echoing_shot` and enemies remain, spawn one `Arrow` aimed at nearest

## Status effects (Day 12)

Added to `Enemy` base class in `enemies.py`:

```python
# In Enemy.__init__:
self._poison_t: float = 0.0
self._slow_t:   float = 0.0
self._burn_t:   float = 0.0
self._stun_t:   float = 0.0
self._bleed_t:  float = 0.0
self._dot_tick: float = 0.0   # shared DoT tick counter

def tick_status(self, dt: float, particles: ParticleSystem) -> None:
    """Call at top of each subclass update(), before movement."""
    self._poison_t = max(0.0, self._poison_t - dt)
    self._slow_t   = max(0.0, self._slow_t   - dt)
    self._burn_t   = max(0.0, self._burn_t   - dt)
    self._stun_t   = max(0.0, self._stun_t   - dt)
    self._bleed_t  = max(0.0, self._bleed_t  - dt)
    if self._poison_t > 0 or self._burn_t > 0 or self._bleed_t > 0:
        self._dot_tick += dt
        if self._dot_tick >= 0.5:
            self._dot_tick = 0.0
            dmg = (1 if self._poison_t > 0 else 0) + \
                  (1 if self._burn_t   > 0 else 0) + \
                  (1 if self._bleed_t  > 0 else 0)
            self.hp -= dmg  # raw HP drain, no particles (status tick)
```

`tick_status` returns early on stun (movement frozen). `_effective_speed` property applies slow multiplier (×0.4 if `_slow_t > 0`).

**Visual feedback** — status rings drawn in `Enemy._draw_body` (or each subclass draw):
- Poison: pulsing green ring (radius `self.radius + 4`)
- Slow: static blue-white ring
- Burn: flickering orange ring (blink at 8 Hz: `int(self._burn_t * 8) % 2`)
- Stun: yellow ring + orbit particles
- Bleed: dark-red drip particles emitted every 0.5 s via `particles.emit`

**Player-side status** — `Player` gets `_burn_t` and `_poison_t`; ticked in `Player.update` using the same 0.5 s tick pattern, calling `self.take_damage(dmg_per_tick)`.

**Application points:**
- Arrow collision block in `game.py`: `if player.arrow_poison: enemy._poison_t = 4.0`
- Enemy contact in `game.py`: VenomfangBat sets `player._poison_t = 3.0`; MagmaSlug burn-patches set `player._burn_t = 2.0`
- Phase Cloak relic dash: `for e in enemies: if overlap(player, e): e._stun_t = 0.8`

## New bosses (Day 13)

All bosses follow the existing protocol: `is_boss_enemy = True`, `boss_name`, `_phase2` property, `phase2_just_triggered` flag, `_summon_queue` for summons.

### Iron Warden (floor 4)
- HP 40, radius 28, speed 60 (patrols, not orbits)
- **Attack 1 – Stomp** (4 s CD, 1 s wind-up): draws expanding shockwave ring on floor for 0.8 s, then deals 1 damage to player if within 60 px of stomp centre (player's current position at cast time)
- **Attack 2 – Shrapnel** (5 s CD, 0.5 s wind-up): 4 EnemyProjectiles in a semicone toward player
- **Phase 2** (≤50%): stomp CD → 2 s; shrapnel becomes 8-way; gains **charge** (1.5 s telegraph arrow drawn, then dashes at `player.x/y` at speed 400 for 0.25 s, like Wolf lunge)
- Phase-2 transition: `emit_warden_phase2` burst (metal sparks) + 14 px shake
- Drops 18 coins

### Abyssal Leech (floor 5)
- HP 35, radius 26, speed 0 (P1) → 30 (P2)
- **Attack 1 – Leeching Tendrils** (6 s CD): fires 3 homing EnemyProjectiles; if any connects with player, `self.hp = min(self.max_hp, self.hp + 3)` (heals boss); projectiles curve toward player each frame (add 4% of (player - proj) direction to velocity)
- **Attack 2 – Void Burst** (5 s CD): 6-way standard burst
- **Phase 2** (≤50%): begins moving; tendril count → 6; void burst CD → 2.5 s
- Drops 20 coins

### Fungal Matriarch (floor 6)
- HP 50, radius 30, stationary
- **Attack 1 – Spore Volley** (3 s CD): 5-way slow spore burst
- **Attack 2 – Summon** (12 s CD): spawns 1 SporeElder via `_summon_queue`; max 3 summons alive
- **Passive**: player within 80 px takes 0.5 HP/s from spore cloud (check in `game.py` enemy-collision block)
- **Phase 2** (≤50%): fire rate → 1.5 s; summon CD → 6 s; summon alternates SporeElder / VenomfangBat
- Phase-2 transition: `emit_matriarch_phase2` burst (green spore cloud) + 14 px shake
- Drops 22 coins

### Void Sovereign (floor 7)
- HP 70, radius 25, speed 65
- **Attack 1 – Void Burst** (1.8 s CD): 5-way bolt burst
- **Attack 2 – Summon** (8 s CD): 2 ShadowWraiths
- **Phase 2** (≤50%): 8-way burst (1.0 s CD); summons VoidShriekers; activates **void field** — `_void_margin: float` grows by 0.5 px/s from 0 up to 128 px; player is clamped to `void_margin < x < ROOM_W - void_margin` (same pattern as door-blocking clamp in `_update_playing`); room edges visually darken via a translucent border rect drawn in `_draw_playing`
- Phase-2 transition: `emit_sovereign_phase2` burst (deep purple/black) + 18 px shake
- Drops 30 coins

## Room templates — planned (Day 14)

3–4 new templates in `rooms.py` themed for underground ruins (floors 4–7):

| Name | Layout idea |
|---|---|
| `_template_corridor` | Two narrow N–S corridors with a connecting E–W passage; 2-tile-wide choke points |
| `_template_pit_ring` | Large impassable void in the centre (no floor) with a ring walkway around it; 4-tile border |
| `_template_rubble_heap` | Asymmetric scatter of 1×2 and 2×1 wall blocks; no symmetry axis |
| `_template_pillars_dense` | 12 single-tile pillars in a 4×3 grid with random offsets; sight-breaking without hard walls |

Template selection: update `Dungeon._generate` to weight deeper-floor dungeons toward the new templates (e.g., `templates = list(range(5 + min(4, floor - 1)))`).

## Implementation notes for the roadmap

### "Boss protocol" (all current + future bosses must follow)
```python
is_boss_enemy = True          # class attribute — used by game.py to find the boss
boss_name = "..."             # class attribute — shown in HP bar
_summon_queue: list[Enemy]    # cleared each frame by game.py's summon-drain loop
phase2_just_triggered: bool   # set in take_hit when HP crosses 50%; consumed by game.py for shake
@property
def _phase2(self) -> bool:
    return self.hp <= self.max_hp // 2
```

### Key extension points in `game.py`
- **Arrow-collision block**: where `arrow_poison`, `venom_gland`, `echoing_shot`, `hunter_mark` are checked
- **Enemy-contact block**: where `player.take_damage` is called — also where VenomfangBat Poison and MagmaSlug Burn are applied to player
- **Room-clear block** (`not self.enemies and not dr.cleared`): where `FLOOR_CLEAR` → `RELIC` transition lands
- **`_commit_transition`**: where `ancient_sigil` i-frames, `coin_floor_reset`, `block_charge` are reset per room

### Dungeon room scaling
```
# In dungeon.py _generate():
target = random.randint(max(5, floor + 4), min(14, floor + 6))
```
This gives: F1→5–7, F2→6–8, F3→7–9, F4→8–10, F5→9–11, F6→10–12, F7→11–13.
