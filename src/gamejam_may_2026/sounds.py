"""Procedural audio synthesis — works with zero asset files.

All sounds are generated at startup via simple PCM synthesis and cached.
To replace any sound with a real file, drop  <name>.ogg  (or .wav) in
  src/gamejam_may_2026/assets/sounds/
and it will be loaded automatically instead of the synthesised version.

Public API
----------
    sounds.init()        # call once after pygame.mixer.init()
    sounds.play("name")  # silently no-ops if mixer is not ready
"""

from __future__ import annotations

import array
import math
import pathlib
import random

import pygame

# ── Internal state ────────────────────────────────────────────────────────────
_sounds: dict[str, pygame.mixer.Sound] = {}
_SAMPLE_RATE = 44100
_MASTER_VOL = 0.38
_ASSET_DIR = pathlib.Path(__file__).parent / "assets" / "sounds"


# ── PCM synthesis helpers ─────────────────────────────────────────────────────


def _env(t: float, attack: float, decay_rate: float) -> float:
    if t < attack:
        return t / attack
    return math.exp(-decay_rate * (t - attack))


def _synth(
    *,
    duration: float,
    freq: float = 440.0,
    freq_end: float | None = None,  # sweep target; None = constant pitch
    shape: str = "sine",  # sine | square | noise
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
        # Envelope
        env = _env(t, attack, decay_rate)
        # Frequency (sweep + optional vibrato)
        if freq_end is not None and freq > 0:
            f = freq * ((freq_end / freq) ** (t / duration))
        else:
            f = freq
        if vibrato_hz > 0:
            f += vibrato_hz * math.sin(2 * math.pi * vibrato_rate * t)
        # Wave
        if shape == "sine":
            w = math.sin(phase)
        elif shape == "square":
            w = 1.0 if math.sin(phase) >= 0 else -1.0
        else:  # noise
            w = random.uniform(-1.0, 1.0)
        phase += 2 * math.pi * f / _SAMPLE_RATE
        val = max(-32768, min(32767, int(32767 * volume * _MASTER_VOL * env * w)))
        buf.append(val)  # L
        buf.append(val)  # R (mono duplicated)
    return pygame.mixer.Sound(buffer=buf)


def _mix(sounds_list: list[pygame.mixer.Sound]) -> pygame.mixer.Sound:
    """Very basic mix: take the first, since pygame doesn't offer in-memory mix."""
    return sounds_list[0]


# ── Load from file or fall back to synthesis ──────────────────────────────────


def _load(name: str, factory) -> pygame.mixer.Sound:
    for ext in (".ogg", ".wav"):
        p = _ASSET_DIR / (name + ext)
        if p.exists():
            try:
                return pygame.mixer.Sound(str(p))
            except pygame.error:
                pass
    return factory()


# ── Public init ───────────────────────────────────────────────────────────────


def init() -> None:
    """Generate or load all game sounds.  Call once after pygame.mixer.init()."""
    if not pygame.mixer.get_init():
        return

    try:
        _sounds["shoot"] = _load(
            "shoot",
            lambda: _synth(
                duration=0.09, freq=900, freq_end=580, shape="sine", volume=0.22, attack=0.002, decay_rate=20
            ),
        )

        _sounds["dash"] = _load(
            "dash",
            lambda: _synth(
                duration=0.13, freq=700, freq_end=220, shape="sine", volume=0.20, attack=0.003, decay_rate=14
            ),
        )

        _sounds["hit_wall"] = _load(
            "hit_wall", lambda: _synth(duration=0.06, freq=300, shape="noise", volume=0.14, decay_rate=35)
        )

        _sounds["hit_enemy"] = _load(
            "hit_enemy",
            lambda: _synth(
                duration=0.10, freq=280, freq_end=180, shape="square", volume=0.22, attack=0.003, decay_rate=22
            ),
        )

        _sounds["enemy_death"] = _load(
            "enemy_death",
            lambda: _synth(
                duration=0.30,
                freq=360,
                freq_end=90,
                shape="sine",
                volume=0.24,
                attack=0.008,
                decay_rate=7,
                vibrato_hz=18,
                vibrato_rate=14,
            ),
        )

        _sounds["player_hurt"] = _load(
            "player_hurt",
            lambda: _synth(
                duration=0.22, freq=220, freq_end=110, shape="square", volume=0.30, attack=0.005, decay_rate=9
            ),
        )

        _sounds["coin"] = _load(
            "coin",
            lambda: _synth(
                duration=0.15, freq=1500, freq_end=1900, shape="sine", volume=0.18, attack=0.003, decay_rate=22
            ),
        )

        _sounds["spore_shoot"] = _load(
            "spore_shoot",
            lambda: _synth(
                duration=0.14, freq=260, freq_end=160, shape="sine", volume=0.16, attack=0.010, decay_rate=15
            ),
        )

        _sounds["room_clear"] = _load(
            "room_clear",
            lambda: _synth(
                duration=0.50, freq=523, freq_end=784, shape="sine", volume=0.22, attack=0.015, decay_rate=4
            ),
        )

        _sounds["wolf_lunge"] = _load(
            "wolf_lunge",
            lambda: _synth(
                duration=0.12, freq=500, freq_end=150, shape="square", volume=0.20, attack=0.002, decay_rate=16
            ),
        )

        _sounds["upgrade"] = _load(
            "upgrade",
            lambda: _synth(
                duration=0.35, freq=880, freq_end=1320, shape="sine", volume=0.28, attack=0.010, decay_rate=5,
                vibrato_hz=8, vibrato_rate=12,
            ),
        )

    except Exception:
        pass  # if synthesis fails for any reason, silently degrade


# ── Public play ───────────────────────────────────────────────────────────────


def play(name: str, volume: float = 1.0) -> None:
    """Play a named sound.  No-ops gracefully if the sound is unavailable."""
    s = _sounds.get(name)
    if s is not None:
        s.set_volume(max(0.0, min(1.0, volume)))
        s.play()
