"""Procedural audio synthesis — works with zero asset files.

All sounds are generated at startup via simple PCM synthesis and cached.
To replace any sound with a real file, drop  <name>.ogg  (or .wav) in
  src/gamejam_may_2026/assets/sounds/
and it will be loaded automatically instead of the synthesised version.

Public API
----------
    sounds.init()              # call once after pygame.mixer.init()
    sounds.init_music()        # call after init() to generate music loops
    sounds.play("name")        # play an SFX (respects sfx_vol)
    sounds.play_music("name")  # switch looping background track (respects music_vol)
    sounds.play_sting("name")  # play a short one-shot sting (boss_defeat / death)
    sounds.stop_music()        # fade out background music
    sounds.music_vol           # float 0-1, user-adjustable music volume
    sounds.sfx_vol             # float 0-1, user-adjustable SFX volume
    sounds.set_music_vol(v)    # update music_vol and apply immediately
    sounds.set_sfx_vol(v)      # update sfx_vol
"""

from __future__ import annotations

import array
import math
import pathlib
import random
import sys
import threading

import pygame

# ── Internal state ────────────────────────────────────────────────────────────
_sounds: dict[str, pygame.mixer.Sound] = {}
_SAMPLE_RATE = 44100
_MASTER_VOL = 0.38
_ASSET_DIR = pathlib.Path(__file__).parent / "assets" / "sounds"

# ── Volume controls (user-adjustable, 0.0–1.0) ───────────────────────────────
music_vol: float = 0.7
sfx_vol: float = 0.7

# ── Music state ───────────────────────────────────────────────────────────────
_music_sounds: dict[str, pygame.mixer.Sound] = {}
_music_channels: list[pygame.mixer.Channel | None] = [None, None]
_music_active: int = 0        # index of the currently-playing channel slot
_current_music: str = "\x00"  # sentinel = "never set";  "" = stopped
_sting_channel: pygame.mixer.Channel | None = None

# ── Note frequencies (Hz) — D natural minor + extensions ─────────────────────
_D2 = 73.42
_E2, _F2, _G2, _A2, _Bb2, _C3 = 82.41, 87.31, 98.00, 110.00, 116.54, 130.81
_D3, _E3, _F3, _G3, _A3, _Bb3, _C4, _D4 = (
    146.83, 164.81, 174.61, 196.00, 220.00, 233.08, 261.63, 293.66
)
_A4, _D5 = 440.00, 587.33
# D major (victory sting)
_Fsharp3, _B3 = 185.00, 246.94
# D Phrygian b2 (boss track tension)
_Eb3 = 155.56


# ── PCM SFX helpers ───────────────────────────────────────────────────────────


def _env(t: float, attack: float, decay_rate: float) -> float:
    if t < attack:
        return t / attack
    return math.exp(-decay_rate * (t - attack))


def _synth(
    *,
    duration: float,
    freq: float = 440.0,
    freq_end: float | None = None,
    shape: str = "sine",
    volume: float = 0.25,
    attack: float = 0.005,
    decay_rate: float = 12.0,
    vibrato_hz: float = 0.0,
    vibrato_rate: float = 8.0,
) -> pygame.mixer.Sound:
    n = int(_SAMPLE_RATE * duration)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        t = i / _SAMPLE_RATE
        env = _env(t, attack, decay_rate)
        if freq_end is not None and freq > 0:
            f = freq * ((freq_end / freq) ** (t / duration))
        else:
            f = freq
        if vibrato_hz > 0:
            f += vibrato_hz * math.sin(2 * math.pi * vibrato_rate * t)
        if shape == "sine":
            w = math.sin(phase)
        elif shape == "square":
            w = 1.0 if math.sin(phase) >= 0 else -1.0
        else:
            w = random.uniform(-1.0, 1.0)
        phase += 2 * math.pi * f / _SAMPLE_RATE
        val = max(-32768, min(32767, int(32767 * volume * _MASTER_VOL * env * w)))
        buf.append(val)
        buf.append(val)
    return pygame.mixer.Sound(buffer=buf)


# ── File-or-synth loader ──────────────────────────────────────────────────────


def _load(name: str, factory) -> pygame.mixer.Sound:
    for ext in (".ogg", ".wav"):
        p = _ASSET_DIR / (name + ext)
        if p.exists():
            try:
                return pygame.mixer.Sound(str(p))
            except pygame.error:
                pass
    return factory()


# ── SFX init ──────────────────────────────────────────────────────────────────


def init() -> None:
    """Generate or load all game sounds. Call once after pygame.mixer.init()."""
    if not pygame.mixer.get_init():
        return
    try:
        _sounds["shoot"] = _load(
            "shoot",
            lambda: _synth(duration=0.09, freq=900, freq_end=580, shape="sine",
                           volume=0.22, attack=0.002, decay_rate=20),
        )
        _sounds["dash"] = _load(
            "dash",
            lambda: _synth(duration=0.13, freq=700, freq_end=220, shape="sine",
                           volume=0.20, attack=0.003, decay_rate=14),
        )
        _sounds["hit_wall"] = _load(
            "hit_wall",
            lambda: _synth(duration=0.06, freq=300, shape="noise",
                           volume=0.14, decay_rate=35),
        )
        _sounds["hit_enemy"] = _load(
            "hit_enemy",
            lambda: _synth(duration=0.10, freq=280, freq_end=180, shape="square",
                           volume=0.22, attack=0.003, decay_rate=22),
        )
        _sounds["enemy_death"] = _load(
            "enemy_death",
            lambda: _synth(duration=0.30, freq=360, freq_end=90, shape="sine",
                           volume=0.24, attack=0.008, decay_rate=7,
                           vibrato_hz=18, vibrato_rate=14),
        )
        _sounds["player_hurt"] = _load(
            "player_hurt",
            lambda: _synth(duration=0.22, freq=220, freq_end=110, shape="square",
                           volume=0.30, attack=0.005, decay_rate=9),
        )
        _sounds["coin"] = _load(
            "coin",
            lambda: _synth(duration=0.15, freq=1500, freq_end=1900, shape="sine",
                           volume=0.18, attack=0.003, decay_rate=22),
        )
        _sounds["spore_shoot"] = _load(
            "spore_shoot",
            lambda: _synth(duration=0.14, freq=260, freq_end=160, shape="sine",
                           volume=0.16, attack=0.010, decay_rate=15),
        )
        _sounds["room_clear"] = _load(
            "room_clear",
            lambda: _synth(duration=0.50, freq=523, freq_end=784, shape="sine",
                           volume=0.22, attack=0.015, decay_rate=4),
        )
        _sounds["wolf_lunge"] = _load(
            "wolf_lunge",
            lambda: _synth(duration=0.12, freq=500, freq_end=150, shape="square",
                           volume=0.20, attack=0.002, decay_rate=16),
        )
        _sounds["upgrade"] = _load(
            "upgrade",
            lambda: _synth(duration=0.35, freq=880, freq_end=1320, shape="sine",
                           volume=0.28, attack=0.010, decay_rate=5,
                           vibrato_hz=8, vibrato_rate=12),
        )
    except Exception:
        pass


# ── Music layer primitives ────────────────────────────────────────────────────

_MUSIC_ABS_VOL = 0.28  # hard ceiling applied by _to_sound (never changes)


def _to_sound(buf_f: list, vol: float = _MUSIC_ABS_VOL) -> pygame.mixer.Sound:
    """Convert float list → stereo int16 Sound with peak normalisation (no distortion)."""
    n = len(buf_f)
    out = array.array("h", [0] * (n * 2))
    if not buf_f:
        return pygame.mixer.Sound(buffer=out)
    peak = max(abs(v) for v in buf_f)
    if peak < 1e-9:
        return pygame.mixer.Sound(buffer=out)
    scale = vol * 32767.0 / peak
    for i in range(n):
        val = max(-32768, min(32767, int(buf_f[i] * scale)))
        out[i * 2]     = val
        out[i * 2 + 1] = val
    return pygame.mixer.Sound(buffer=out)


def _bfade(buf_f: list, fade_sec: float = 0.06) -> None:
    """In-place loop-boundary fade to suppress click artefacts."""
    n = len(buf_f)
    k = int(fade_sec * _SAMPLE_RATE)
    for i in range(min(k, n)):
        f = i / k
        buf_f[i]         *= f
        buf_f[n - 1 - i] *= f


def _add_pad(buf_f: list, chord_freqs: list, detune: float = 1.1,
             lfo_hz: float = 0.06, lfo_depth: float = 0.30,
             gain: float = 0.28) -> None:
    """Detuned chord pad: two oscillators per chord note + slow amplitude LFO."""
    n = len(buf_f)
    tp = 2.0 * math.pi
    osc_freqs = [f + d * detune for f in chord_freqs for d in (-0.5, 0.5)]
    n_osc = len(osc_freqs)
    phases = [0.0] * n_osc
    scale = gain / n_osc
    for i in range(n):
        t = i / _SAMPLE_RATE
        lfo = 1.0 - lfo_depth * (0.5 - 0.5 * math.sin(tp * lfo_hz * t))
        s = sum(math.sin(phases[k]) for k in range(n_osc))
        buf_f[i] += s * lfo * scale
        for k in range(n_osc):
            phases[k] += tp * osc_freqs[k] / _SAMPLE_RATE


def _add_drone(buf_f: list, freq: float, tremolo_hz: float = 0.05,
               tremolo_depth: float = 0.15, gain: float = 0.45) -> None:
    """Bass drone: fundamental + octave + fifth with slow tremolo."""
    n = len(buf_f)
    tp = 2.0 * math.pi
    p1 = p2 = p5 = 0.0
    for i in range(n):
        t = i / _SAMPLE_RATE
        trem = 1.0 - tremolo_depth * math.sin(tp * tremolo_hz * t)
        s = math.sin(p1) * 0.55 + math.sin(p2) * 0.28 + math.sin(p5) * 0.17
        buf_f[i] += s * trem * gain
        p1 += tp * freq       / _SAMPLE_RATE
        p2 += tp * freq * 2.0 / _SAMPLE_RATE
        p5 += tp * freq * 1.5 / _SAMPLE_RATE


def _add_notes(buf_f: list, pattern: list, beat_dur: float,
               wave: str = "sine", gain: float = 0.35,
               atk: float = 0.02, rel: float = 0.05) -> None:
    """Render melodic/harmonic notes from [(beat, freq_hz, dur_beats), ...]."""
    n = len(buf_f)
    tp = 2.0 * math.pi
    for beat, freq, dur_beats in pattern:
        i0 = int(beat * beat_dur * _SAMPLE_RATE)
        dur_sec = dur_beats * beat_dur
        dur_i = int(dur_sec * _SAMPLE_RATE)
        phase = 0.0
        for j in range(dur_i):
            i = i0 + j
            if i >= n:
                break
            t = j / _SAMPLE_RATE
            if t < atk:
                env = t / atk
            elif t > dur_sec - rel:
                env = max(0.0, (dur_sec - t) / rel)
            else:
                env = 1.0
            if wave == "sine":
                w = math.sin(phase)
            elif wave == "square":
                raw = math.sin(phase)
                w = 0.65 * (1.0 if raw >= 0 else -1.0) + 0.35 * raw
            else:
                w = math.sin(phase)
            buf_f[i] += w * env * gain
            phase += tp * freq / _SAMPLE_RATE


def _add_kicks(buf_f: list, beats: list, beat_dur: float,
               gain: float = 0.70) -> None:
    """Kick: sine frequency sweep 80→38 Hz with fast exponential envelope."""
    n = len(buf_f)
    tp = 2.0 * math.pi
    f0, tau, fc = 80.0, 0.07, 38.0
    for b in beats:
        i0 = int(b * beat_dur * _SAMPLE_RATE)
        dur_i = min(int(0.30 * _SAMPLE_RATE), n - i0)
        if dur_i <= 0:
            continue
        phase = 0.0
        for j in range(dur_i):
            i = i0 + j
            if i >= n:
                break
            t = j / _SAMPLE_RATE
            env = math.exp(-t / 0.065)
            freq = f0 * math.exp(-t / tau) + fc
            buf_f[i] += math.sin(phase) * env * gain
            phase += tp * freq / _SAMPLE_RATE


def _add_snares(buf_f: list, beats: list, beat_dur: float,
                gain: float = 0.40) -> None:
    """Snare: noise burst with exponential decay."""
    n = len(buf_f)
    dur_i = int(0.18 * _SAMPLE_RATE)
    for b in beats:
        i0 = int(b * beat_dur * _SAMPLE_RATE)
        for j in range(min(dur_i, n - i0)):
            t = j / _SAMPLE_RATE
            buf_f[i0 + j] += random.uniform(-1.0, 1.0) * math.exp(-t / 0.058) * gain


def _add_hihats(buf_f: list, beats: list, beat_dur: float,
                gain: float = 0.16) -> None:
    """Hi-hat: very short noise transient."""
    n = len(buf_f)
    dur_i = int(0.045 * _SAMPLE_RATE)
    for b in beats:
        i0 = int(b * beat_dur * _SAMPLE_RATE)
        for j in range(min(dur_i, n - i0)):
            t = j / _SAMPLE_RATE
            buf_f[i0 + j] += random.uniform(-1.0, 1.0) * math.exp(-t / 0.012) * gain


def _add_metal_clang(buf_f: list, beats: list, beat_dur: float,
                     gain: float = 0.28) -> None:
    """Metallic dungeon hit: pitched sine (180 Hz) + noise for a chain/gate sound."""
    n = len(buf_f)
    tp = 2.0 * math.pi
    dur_i = int(0.40 * _SAMPLE_RATE)
    for b in beats:
        i0 = int(b * beat_dur * _SAMPLE_RATE)
        phase = 0.0
        for j in range(min(dur_i, n - i0)):
            t = j / _SAMPLE_RATE
            env = math.exp(-t / 0.11)
            tone  = math.sin(phase) * 0.35
            noise = random.uniform(-1.0, 1.0) * 0.65
            buf_f[i0 + j] += (tone + noise) * env * gain
            phase += tp * 180.0 / _SAMPLE_RATE


# ── Track builders ────────────────────────────────────────────────────────────


def _gen_menu_music() -> pygame.mixer.Sound:
    """Eerie forest ambience: detuned D-minor pad + bass drone + sparse shimmer.
    No rhythm — suitable for menu and calm moments."""
    n = int(10.0 * _SAMPLE_RATE)
    buf = [0.0] * n

    _add_pad(buf, [_D3, _F3, _A3], lfo_hz=0.055, lfo_depth=0.38,
             detune=1.0, gain=0.34)
    _add_drone(buf, _D2, tremolo_hz=0.04, tremolo_depth=0.18, gain=0.42)
    # Sparse shimmer notes (positions are in seconds, beat_dur=1.0)
    _add_notes(buf, [
        (1.9,  _A4,      1.4),
        (5.0,  _D5,      0.9),
        (7.8,  _C4 * 2,  1.3),  # C5
        (9.2,  _A4,      0.6),
    ], beat_dur=1.0, wave="sine", atk=0.35, rel=0.50, gain=0.13)

    _bfade(buf)
    return _to_sound(buf)


def _gen_dungeon_music() -> pygame.mixer.Sound:
    """Heavy dungeon stomp: deep kick, sparse metal clang, D-Phrygian bass + melody.
    4 bars at 85 BPM ≈ 11.3 s loop. No hi-hat — silence adds weight."""
    BPM = 85
    bd = 60.0 / BPM
    bars, bpb = 4, 4
    total_beats = bars * bpb
    n = int(total_beats * bd * _SAMPLE_RATE)
    buf = [0.0] * n

    Eb2 = _D2 * 2 ** (1 / 12)   # Phrygian b2 in the bass register

    # Kick: asymmetric 7-hit pattern, standard helper keeps gain modest
    _add_kicks(buf, [0, 2.5, 4, 6, 8, 10.5, 12], bd, gain=0.45)

    # Metal clang snare — only twice per loop (maximum dread)
    _add_metal_clang(buf, [3, 11], bd, gain=0.20)

    # Bass: slow chromatic movement, sine wave (no square-wave buzz)
    _add_notes(buf, [
        (0,    _D2,  2.2),
        (2,    _D2,  2.2),
        (4,    _C3,  2.0),
        (6,    _Bb2, 2.0),
        (8,    _G2,  2.0),
        (10,   _F2,  1.5),
        (11.5, Eb2,  0.8),    # Phrygian b2 — chromatic dread
        (12,   _D2,  4.0),
    ], bd, wave="sine", atk=0.02, rel=0.25, gain=0.22)

    # Melody: sparse half-notes, Phrygian b2 for dungeon tension
    _add_notes(buf, [
        (0,    _D3,  1.7),
        (2,    _F3,  1.5),
        (4,    _Eb3, 1.7),    # Phrygian b2 — key darkness
        (6,    _D3,  1.0),
        (7,    _A3,  1.0),
        (8,    _G3,  2.0),
        (10,   _F3,  1.0),
        (11,   _Eb3, 1.0),
        (12,   _D3,  2.0),
        (14,   _C4,  2.2),    # unresolved as loop restarts
    ], bd, wave="sine", atk=0.04, rel=0.35, gain=0.20)

    _bfade(buf)
    return _to_sound(buf)


def _gen_boss_music() -> pygame.mixer.Sound:
    """Chaotic intensity: complex kick, 16th hi-hats, D-Phrygian bass, fast melody.
    4 bars at 155 BPM ≈ 6.19 s loop."""
    BPM = 155
    bd = 60.0 / BPM
    bars, bpb = 4, 4
    total_beats = bars * bpb
    n = int(total_beats * bd * _SAMPLE_RATE)
    buf = [0.0] * n

    Eb2 = _D2 * 2 ** (1 / 12)

    kick_beats  = [b * bpb + k for b in range(bars) for k in (0, 0.75, 2, 2.5)]
    snare_beats = [b * bpb + k for b in range(bars) for k in (1, 2, 3)]
    hihat_beats = [i * 0.25 for i in range(total_beats * 4)]
    _add_kicks(buf,  kick_beats,  bd, gain=0.70)
    _add_snares(buf, snare_beats, bd, gain=0.42)
    _add_hihats(buf, hihat_beats, bd, gain=0.12)

    _add_notes(buf, [
        (0,    _D2,  0.35), (0.5,  _D2,  0.35), (1,    Eb2,  0.35), (1.5,  _D2,  0.35),
        (2,    _F2,  0.35), (2.5,  _G2,  0.35), (3,    _F2,  0.35), (3.5,  _D2,  0.35),
        (4,    _D2,  0.35), (4.5,  _D2,  0.35), (5,    Eb2,  0.35), (5.5,  Eb2,  0.35),
        (6,    _F2,  0.35), (6.5,  _A2,  0.35), (7,    _G2,  0.35), (7.5,  _F2,  0.35),
        (8,    _D2,  0.35), (8.5,  Eb2,  0.35), (9,    _F2,  0.35), (9.5,  _G2,  0.35),
        (10,   _A2,  0.35), (10.5, _Bb2, 0.35), (11,   _A2,  0.35), (11.5, _G2,  0.35),
        (12,   _F2,  0.35), (12.5, _G2,  0.35), (13,   _A2,  0.35), (13.5, _Bb2, 0.35),
        (14,   _A2,  0.35), (14.5, _G2,  0.35), (15,   _F2,  0.35), (15.5, Eb2,  0.35),
    ], bd, wave="square", atk=0.005, rel=0.03, gain=0.24)

    _add_notes(buf, [
        (0,    _D3,  0.25), (0.5,  _Eb3, 0.25), (1,    _F3,  0.50),
        (2,    _A3,  0.25), (2.5,  _Bb3, 0.25), (3,    _A3,  0.50),
        (4,    _G3,  0.25), (4.5,  _F3,  0.25), (5,    _G3,  0.25), (5.5,  _A3,  0.25),
        (6,    _Bb3, 0.50), (7,    _A3,  0.50),
        (8,    _D3,  0.25), (8.5,  _F3,  0.25), (9,    _A3,  0.25), (9.5,  _D4,  0.25),
        (10,   _C4,  0.25), (10.5, _Bb3, 0.25), (11,   _A3,  0.25), (11.5, _G3,  0.25),
        (12,   _F3,  0.25), (12.5, _G3,  0.25), (13,   _A3,  0.50),
        (14,   _Bb3, 0.25), (14.5, _A3,  0.25), (15,   _G3,  0.50),
    ], bd, wave="sine", atk=0.015, rel=0.05, gain=0.26)

    # Raw noise burst on every beat for additional aggression
    dur_i = int(0.07 * _SAMPLE_RATE)
    for b in range(total_beats):
        i0 = int(b * bd * _SAMPLE_RATE)
        for j in range(min(dur_i, n - i0)):
            t = j / _SAMPLE_RATE
            buf[i0 + j] += random.uniform(-1.0, 1.0) * math.exp(-t / 0.022) * 0.09

    _bfade(buf)
    return _to_sound(buf)


def _gen_boss_defeat_sting() -> pygame.mixer.Sound:
    """Snare roll → ascending D-major arpeggio → cymbal crash → held chord. ~4.5 s."""
    n = int(4.5 * _SAMPLE_RATE)
    buf = [0.0] * n
    tp = 2.0 * math.pi

    # Crescendo snare roll: 0 → 0.50 s (quiet → loud)
    n_roll = 10
    roll_step = 0.050
    snare_dur_i = int(0.14 * _SAMPLE_RATE)
    for k in range(n_roll):
        i0 = int(k * roll_step * _SAMPLE_RATE)
        prog = k / (n_roll - 1)
        hit_gain = 0.10 + 0.48 * prog
        for j in range(min(snare_dur_i, n - i0)):
            t = j / _SAMPLE_RATE
            buf[i0 + j] += random.uniform(-1.0, 1.0) * math.exp(-t / 0.05) * hit_gain

    # Ascending D-major arpeggio: 0.54 → 1.38 s  (beat_dur=1.0 → beats = seconds)
    _add_notes(buf, [
        (0.54, _D3,      0.22),
        (0.75, _Fsharp3, 0.22),
        (0.96, _A3,      0.22),
        (1.17, _D4,      0.22),
        (1.38, _D5,      0.55),   # high top-note, rings into crash
    ], beat_dur=1.0, wave="sine", atk=0.018, rel=0.12, gain=0.44)

    # Lower harmony line (a 3rd below the arpeggio) for thickness
    _add_notes(buf, [
        (0.54, _Bb2,     0.22),
        (0.75, _D3,      0.22),
        (0.96, _Fsharp3, 0.22),
        (1.17, _Bb3,     0.22),
    ], beat_dur=1.0, wave="sine", atk=0.018, rel=0.12, gain=0.22)

    # Kick + cymbal crash at t=1.70 (the landing)
    t_land = 1.70
    _add_kicks(buf, [t_land], 1.0, gain=0.92)
    i_crash = int(t_land * _SAMPLE_RATE)
    crash_dur = int(2.2 * _SAMPLE_RATE)
    for j in range(min(crash_dur, n - i_crash)):
        t = j / _SAMPLE_RATE
        env = math.exp(-t / 0.52)
        buf[i_crash + j] += random.uniform(-1.0, 1.0) * env * 0.40

    # Held D-major chord after crash
    _add_notes(buf, [
        (1.70, _D3,      2.5),
        (1.70, _Fsharp3, 2.5),
        (1.70, _A3,      2.5),
        (1.70, _D4,      2.5),
    ], beat_dur=1.0, wave="sine", atk=0.04, rel=0.80, gain=0.30)

    # Warm pad under held chord (full buf — also softens the arpeggio section)
    _add_pad(buf, [_D3, _Fsharp3, _A3], lfo_hz=0.10, lfo_depth=0.12,
             detune=0.7, gain=0.09)

    # Fade out: last 1.2 s
    fade_n = int(1.2 * _SAMPLE_RATE)
    for i in range(fade_n):
        j = n - 1 - i
        if j >= 0:
            buf[j] *= i / fade_n

    return _to_sound(buf, vol=_MUSIC_ABS_VOL * 1.25)


def _gen_death_sting() -> pygame.mixer.Sound:
    """Death knell: inharmonic bell toll + sub-bass + vibrato descent + stone-echo. ~5.5 s."""
    n = int(5.5 * _SAMPLE_RATE)
    buf = [0.0] * n
    tp = 2.0 * math.pi

    # Impact at t=0: kick thud + short noise crack
    _add_kicks(buf, [0], 1.0, gain=0.80)
    for j in range(int(0.10 * _SAMPLE_RATE)):
        t = j / _SAMPLE_RATE
        buf[j] += random.uniform(-1.0, 1.0) * math.exp(-t / 0.030) * 0.50

    # Sub-bass rumble at 28 Hz (physical weight, decays quickly)
    phase_sub = 0.0
    for j in range(min(int(0.55 * _SAMPLE_RATE), n)):
        t = j / _SAMPLE_RATE
        buf[j] += math.sin(phase_sub) * math.exp(-t / 0.20) * 0.42
        phase_sub += tp * 28.0 / _SAMPLE_RATE

    # Inharmonic bell at D3: 3 partials with staggered decay → real bell timbre
    # (bright transient on impact that quickly settles to the warm fundamental)
    for freq_mul, tau, amp in [(1.00, 1.30, 0.55), (2.00, 0.40, 0.24), (2.76, 0.18, 0.16)]:
        phase = 0.0
        for j in range(min(int(tau * 5 * _SAMPLE_RATE), n)):
            t = j / _SAMPLE_RATE
            buf[j] += math.sin(phase) * math.exp(-t / tau) * amp
            phase += tp * (_D3 * freq_mul) / _SAMPLE_RATE

    # Ghost bell an octave below (D2) — body under the D3 toll
    phase_b2 = 0.0
    for j in range(min(int(2.8 * _SAMPLE_RATE), n)):
        t = j / _SAMPLE_RATE
        buf[j] += math.sin(phase_b2) * math.exp(-t / 0.60) * 0.30
        phase_b2 += tp * _D2 / _SAMPLE_RATE

    # Mournful descent with vibrato + stone echo (0.18 s delay, 35% amplitude)
    # Notes start at 1.3 s — letting the bell toll breathe first
    melody = [
        (1.30, _D4,  0.80),
        (2.30, _Bb3, 0.78),
        (3.20, _G3,  0.75),
        (4.10, _Eb3, 2.00),  # Phrygian b2 — hangs unresolved until global fade
    ]
    echo_di = int(0.18 * _SAMPLE_RATE)
    for t_start, freq, dur_sec in melody:
        i0 = int(t_start * _SAMPLE_RATE)
        dur_i = int(dur_sec * _SAMPLE_RATE)
        phase_m = 0.0
        phase_e = 0.0
        for j in range(dur_i):
            i_m = i0 + j
            i_e = i0 + j + echo_di
            if i_m >= n and i_e >= n:
                break
            t = j / _SAMPLE_RATE
            atk = 0.09
            rel_start = dur_sec - 0.40
            if t < atk:
                env = t / atk
            elif t > rel_start:
                env = max(0.0, (dur_sec - t) / 0.40)
            else:
                env = 1.0
            # Vibrato builds in gradually after the attack
            vib = math.sin(tp * 4.8 * t) * 1.8 * min(t / 0.25, 1.0)
            f_vib = freq + vib
            if i_m < n:
                buf[i_m] += math.sin(phase_m) * env * 0.45
            if i_e < n:
                buf[i_e] += math.sin(phase_e) * env * 0.16  # stone echo, no vibrato
            phase_m += tp * f_vib / _SAMPLE_RATE
            phase_e += tp * freq  / _SAMPLE_RATE

    # Very quiet bass drone throughout for gravity
    _add_drone(buf, _D2, tremolo_hz=0.03, tremolo_depth=0.08, gain=0.10)

    # Fade out: last 1.2 s
    fade_n = int(1.2 * _SAMPLE_RATE)
    for i in range(fade_n):
        j = n - 1 - i
        if j >= 0:
            buf[j] *= i / fade_n

    return _to_sound(buf, vol=_MUSIC_ABS_VOL * 1.30)


def init_music() -> None:
    """Generate or load all background music and stings. Call once after init().

    On native platforms synthesis runs in a background thread so the game window
    opens immediately; tracks play as soon as they are ready.
    On emscripten (web) synthesis is synchronous (threads unavailable).
    """
    if not pygame.mixer.get_init():
        return

    def _generate() -> None:
        try:
            _music_sounds["menu"]        = _load("music_menu",        _gen_menu_music)
            _music_sounds["dungeon"]     = _load("music_dungeon",     _gen_dungeon_music)
            _music_sounds["boss"]        = _load("music_boss",        _gen_boss_music)
            _music_sounds["boss_defeat"] = _load("music_boss_defeat", _gen_boss_defeat_sting)
            _music_sounds["death"]       = _load("music_death",       _gen_death_sting)
        except Exception:
            pass

    if sys.platform == "emscripten":
        _generate()
    else:
        threading.Thread(target=_generate, daemon=True).start()


# ── Volume control ────────────────────────────────────────────────────────────


def set_music_vol(v: float) -> None:
    """Set music volume (0.0–1.0) and apply immediately to playing channels."""
    global music_vol
    music_vol = max(0.0, min(1.0, v))
    for ch in _music_channels:
        if ch and ch.get_busy():
            ch.set_volume(music_vol)


def set_sfx_vol(v: float) -> None:
    """Set SFX volume (0.0–1.0). Applied on next play() call."""
    global sfx_vol
    sfx_vol = max(0.0, min(1.0, v))


# ── Public music API ──────────────────────────────────────────────────────────


def play_music(name: str) -> None:
    """Switch to a looping background track with crossfade. No-op if already playing."""
    global _current_music, _music_active
    if not pygame.mixer.get_init() or name == _current_music:
        return
    s = _music_sounds.get(name)
    if s is None:
        return
    _current_music = name

    old_ch = _music_channels[_music_active]
    if old_ch and old_ch.get_busy():
        old_ch.fadeout(900)

    _music_active ^= 1
    ch = _music_channels[_music_active]
    if ch is None:
        ch = pygame.mixer.find_channel(True)
        _music_channels[_music_active] = ch
    if ch:
        ch.play(s, loops=-1, fade_ms=1000)
        ch.set_volume(music_vol)


def play_sting(name: str) -> None:
    """Play a short non-looping sting (boss_defeat / death) on a dedicated channel."""
    global _sting_channel
    if not pygame.mixer.get_init():
        return
    s = _music_sounds.get(name)
    if s is None:
        return
    if _sting_channel is None:
        _sting_channel = pygame.mixer.find_channel(True)
    if _sting_channel:
        _sting_channel.play(s, loops=0, fade_ms=50)
        _sting_channel.set_volume(music_vol)


def stop_music(fade_ms: int = 800) -> None:
    """Fade out and stop all looping background music."""
    global _current_music
    if _current_music in ("", "\x00"):
        return
    _current_music = ""
    for ch in _music_channels:
        if ch and ch.get_busy():
            ch.fadeout(fade_ms)


# ── Public SFX play ───────────────────────────────────────────────────────────


def play(name: str, volume: float = 1.0) -> None:
    """Play a named sound effect. No-ops gracefully if unavailable."""
    s = _sounds.get(name)
    if s is not None:
        s.set_volume(max(0.0, min(1.0, volume * sfx_vol)))
        s.play()
