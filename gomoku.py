import argparse

from ai import print_search_summary
from board import BLACK, WHITE
from game import Game
from ui import GomokuUI, select_mode


MODES = {
    "pvp":        {BLACK: "human", WHITE: "human"},
    "pvai-black": {BLACK: "human", WHITE: "ai"},
    "pvai-white": {BLACK: "ai",    WHITE: "human"},
    "aivai":      {BLACK: "ai",    WHITE: "ai"},
}


def parse_args():
    parser = argparse.ArgumentParser(description="Gomoku")
    parser.add_argument(
        "--mode",
        choices=list(MODES),
        default=None,
        help="Skip the start screen and jump straight into this mode.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    mode = args.mode if args.mode is not None else select_mode()
    if mode is None:
        return

    game = Game()
    ui = GomokuUI(game, players=MODES[mode])
    ui.run()
    print_search_summary()


if __name__ == "__main__":
    main()
