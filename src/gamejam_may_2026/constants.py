# ── Display ──────────────────────────────────────────────────────────────────
SCREEN_W = 1280
SCREEN_H = 720
FPS = 60

# ── Layout ────────────────────────────────────────────────────────────────────
HUD_H = 80                           # bottom strip reserved for the HUD
PLAYFIELD_H = SCREEN_H - HUD_H      # 640 px  — the room lives here

# ── Tiles ─────────────────────────────────────────────────────────────────────
TILE_SIZE = 32
ROOM_TILE_W = SCREEN_W // TILE_SIZE      # 40
ROOM_TILE_H = PLAYFIELD_H // TILE_SIZE   # 20
ROOM_PIXEL_W = ROOM_TILE_W * TILE_SIZE   # 1280
ROOM_PIXEL_H = ROOM_TILE_H * TILE_SIZE   # 640

TILE_FLOOR = 0
TILE_WALL  = 1

# ── Colour palette (forest-ruins) ────────────────────────────────────────────
C_BG          = (12,  20,  10)
C_FLOOR       = (36,  56,  28)
C_FLOOR_ALT   = (42,  65,  33)
C_WALL        = (74,  56,  40)
C_WALL_DARK   = (48,  36,  24)
C_WALL_LIT    = (95,  74,  54)

C_PLAYER      = (225, 220, 200)
C_PLAYER_DARK = (160, 150, 130)
C_DASH_TRAIL  = (140, 210, 255)

C_ARROW       = (205, 165,  75)
C_ARROW_TIP   = (245, 215, 105)

C_ENEMY_PROJ  = (220,  90,  40)

C_HUD_BG      = (20,  15,  10)
C_HUD_BORDER  = (58,  44,  32)
C_HEART_FULL  = (215,  55,  55)
C_HEART_EMPTY = (75,   28,  28)
C_COIN        = (255, 200,  10)
C_COIN_DARK   = (180, 130,   0)

# Enemies
C_GOBLIN      = (110, 175,  75)
C_GOBLIN_DARK = (75,  118,  50)
C_WOLF        = (148, 132, 118)

# Particles
C_SPARK_A  = (255, 205,  55)
C_SPARK_B  = (255, 138,  25)
C_LEAF_A   = (88,  168,  55)
C_LEAF_B   = (55,  115,  35)
C_BLOOD_A  = (205,  42,  42)
C_BLOOD_B  = (142,  18,  18)

# ── Player stats ─────────────────────────────────────────────────────────────
PLAYER_SPEED          = 200    # px / s
PLAYER_DASH_SPEED     = 620    # px / s during dash
PLAYER_DASH_DURATION  = 0.14   # s
PLAYER_DASH_COOLDOWN  = 0.65   # s
PLAYER_IFRAMES        = 0.75   # s  (invincibility after a hit)
PLAYER_MAX_HP         = 3
PLAYER_SHOOT_COOLDOWN = 0.22   # s
PLAYER_RADIUS         = 12     # px (collision circle)

# ── Arrow (player) ───────────────────────────────────────────────────────────
ARROW_SPEED    = 520   # px / s
ARROW_DAMAGE   = 1
ARROW_LIFETIME = 1.8   # s

# ── Enemy projectile ─────────────────────────────────────────────────────────
EPROJ_SPEED    = 220
EPROJ_DAMAGE   = 1
EPROJ_LIFETIME = 2.2

# ── Goblin Runner ─────────────────────────────────────────────────────────────
GOBLIN_SPEED      = 88
GOBLIN_HP         = 3
GOBLIN_DAMAGE     = 1
GOBLIN_RADIUS     = 13
GOBLIN_COIN_DROP  = 2

# ── Goblin Archer ─────────────────────────────────────────────────────────────
ARCHER_SPEED        = 60
ARCHER_HP           = 2
ARCHER_DAMAGE       = 1
ARCHER_RADIUS       = 12
ARCHER_PREF_DIST    = 250   # preferred distance from player
ARCHER_SHOOT_CD     = 2.2   # s between shots
ARCHER_COIN_DROP    = 3

# ── Wolf ──────────────────────────────────────────────────────────────────────
WOLF_SPEED        = 128
WOLF_HP           = 2
WOLF_RADIUS       = 12
WOLF_LUNGE_SPEED  = 390    # px/s during lunge dash
WOLF_LUNGE_DUR    = 0.18   # s
WOLF_LUNGE_CD     = 2.2    # s between lunges
WOLF_LUNGE_RANGE  = 130    # px; triggers lunge when closer than this
WOLF_COIN_DROP    = 2

# ── Spore Plant ───────────────────────────────────────────────────────────────
SPLANT_HP         = 5
SPLANT_RADIUS     = 16
SPLANT_SHOOT_CD   = 2.8    # s between volleys
SPLANT_COIN_DROP  = 4

# ── Spore projectile (fired by Spore Plant) ───────────────────────────────────
C_SPORE           = (75, 185, 55)    # bright green
SPORE_SPEED       = 145
SPORE_LIFETIME    = 3.5
SPORE_DAMAGE      = 1

# ── Boss: Goblin Shaman (floors 1–2) ─────────────────────────────────────────
SHAMAN_HP           = 20
SHAMAN_HP_F2        = 26
SHAMAN_RADIUS       = 22
SHAMAN_SPEED        = 50
SHAMAN_COIN_DROP    = 10
SHAMAN_BOLT_CD      = 2.2     # s between bolt volleys (phase 1)
SHAMAN_BOLT_CD_P2   = 1.5     # phase 2
SHAMAN_SUMMON_CD    = 10.0    # s between minion summons (phase 1)
SHAMAN_SUMMON_CD_P2 =  6.0    # phase 2

C_SHAMAN       = (165,  90, 210)
C_SHAMAN_DARK  = (100,  52, 138)
C_SHAMAN_BOLT  = (205, 100, 255)

# ── Boss: Ancient Tree (floor 3) ─────────────────────────────────────────────
TREE_HP          = 30
TREE_RADIUS      = 30
TREE_COIN_DROP   = 15
TREE_ROOT_CD     = 2.5    # s between root volleys (phase 1)
TREE_ROOT_CD_P2  = 1.8    # phase 2
TREE_THORN_CD    = 5.0    # s between thorn rings (phase 1)
TREE_THORN_CD_P2 = 3.5    # phase 2

C_TREE      = (38,  80, 25)
C_TREE_DARK = (22,  50, 14)
C_TREE_ROOT = (88,  55, 20)
C_THORN     = (130, 195, 55)

# ── Stone Crawler (floor 4+) ──────────────────────────────────────────────────
CRAWLER_HP         = 8
CRAWLER_RADIUS     = 16
CRAWLER_SPEED      = 55.0
CRAWLER_DAMAGE     = 2
CRAWLER_COIN_DROP  = 4
CRAWLER_SHELL_HITS = 3    # arrow deflects before shell breaks

C_CRAWLER      = (138, 118, 92)
C_CRAWLER_DARK = ( 85,  72, 56)

# ── Venom Bat (floor 4+) ─────────────────────────────────────────────────────
BAT_HP         = 2
BAT_RADIUS     = 10
BAT_SPEED      = 160.0
BAT_COIN_DROP  = 3
BAT_POISON_DUR = 3.0     # seconds of poison applied to player on contact

C_BAT      = ( 95,  65, 135)
C_BAT_DARK = ( 55,  38,  85)

# ── Crystal Turret (floor 5+) ────────────────────────────────────────────────
TURRET_HP         = 10
TURRET_RADIUS     = 18
TURRET_SHOOT_CD   = 2.5
TURRET_PROJ_SPEED = 220.0
TURRET_COIN_DROP  = 5

C_TURRET      = ( 95, 180, 215)
C_TURRET_DARK = ( 60, 115, 145)
C_TURRET_BEAM = (175, 230, 255)
