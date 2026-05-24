"""Runtime config — key layout and other tweakable settings.

Changed by main.py before the game starts (e.g. via --keys flag).
"""

from __future__ import annotations
import pygame

# ── Key layout ────────────────────────────────────────────────────────────────
# Valid values: "arrows" | "wasd" | "zqsd"
KEY_LAYOUT: str = "zqsd"

_LAYOUTS: dict[str, dict[str, int]] = {
    "arrows": {
        "up":    pygame.K_UP,
        "down":  pygame.K_DOWN,
        "left":  pygame.K_LEFT,
        "right": pygame.K_RIGHT,
        "dash":  pygame.K_SPACE,
    },
    "wasd": {
        "up":    pygame.K_w,
        "down":  pygame.K_s,
        "left":  pygame.K_a,
        "right": pygame.K_d,
        "dash":  pygame.K_SPACE,
    },
    "zqsd": {
        "up":    pygame.K_z,
        "down":  pygame.K_s,
        "left":  pygame.K_q,
        "right": pygame.K_d,
        "dash":  pygame.K_SPACE,
    },
}


def get_keys() -> dict[str, int]:
    """Return the active key-binding dict."""
    return _LAYOUTS[KEY_LAYOUT]
