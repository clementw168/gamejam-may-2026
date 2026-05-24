"""Entry point — initialise pygame and run the game loop."""

from __future__ import annotations
import argparse
import sys
import pygame
from gamejam_may_2026 import constants as C
from gamejam_may_2026 import config
from gamejam_may_2026 import sounds
from gamejam_may_2026.game import Game


def _parse_args() -> None:
    parser = argparse.ArgumentParser(
        prog="verdant-depths",
        description="Verdant Depths — forest-ruins roguelite",
    )
    parser.add_argument(
        "--keys",
        choices=["arrows", "wasd", "zqsd"],
        default="zqsd",
        help="Key layout for movement  (default: zqsd)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode: infinite dash, HP floor 1, K kills all enemies",
    )
    args = parser.parse_args()
    config.KEY_LAYOUT = args.keys
    config.DEBUG      = args.debug


def main() -> None:
    _parse_args()

    pygame.mixer.pre_init(44100, -16, 2, 512)  # 44 kHz, 16-bit signed, stereo
    pygame.init()
    pygame.mixer.init()
    sounds.init()   # generate / load all sounds
    pygame.display.set_caption("Verdant Depths")
    screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H))
    pygame.mouse.set_visible(True)
    clock = pygame.time.Clock()

    game = Game(screen)

    while True:
        dt = clock.tick(C.FPS) / 1000.0
        dt = min(dt, 0.05)  # cap delta to avoid physics spiral on focus loss

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if game.state == "MENU":
                    pygame.quit()
                    sys.exit()
                # All other states: forward to game (Esc toggles pause)
            game.handle_event(event)

        game.update(dt)
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()
