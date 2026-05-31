"""Entry point — initialise pygame and run the game loop."""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure this directory is on sys.path so flat imports work whether we're
# running as a package (uv run) or directly (pygbag web build).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

import config  # type: ignore[import-not-found]
import constants as C  # type: ignore[import-not-found]
import sounds  # type: ignore[import-not-found]
from game import Game  # type: ignore[import-not-found]

DEBUG = False


async def main() -> None:
    config.DEBUG = DEBUG
    pygame.mixer.pre_init(44100, -16, 2, 512)  # 44 kHz, 16-bit signed, stereo
    pygame.init()
    pygame.mixer.init()
    sounds.init()  # generate / load all sounds
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
                if game.state == "MENU" and sys.platform != "emscripten":
                    pygame.quit()
                    sys.exit()
                # All other states: forward to game (Esc toggles pause)
            game.handle_event(event)

        game.update(dt)
        game.draw()
        pygame.display.flip()
        await asyncio.sleep(0)


asyncio.run(main())
