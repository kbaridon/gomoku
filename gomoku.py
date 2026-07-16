#!/usr/bin/env python3
"""Gomoku hotseat game — entry point.

Launches a matplotlib window driving a 19x19 Gomoku game for two local
players. See `info.md` for design notes and rules coverage.
"""

from game import Game
from ui import GomokuUI


def main():
    game = Game()
    ui = GomokuUI(game)
    ui.run()


if __name__ == "__main__":
    main()
