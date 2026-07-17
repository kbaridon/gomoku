from game import Game
from ui import GomokuUI


def main():
    """Entrypoint of the program"""
    game = Game()
    ui = GomokuUI(game)
    ui.run()


if __name__ == "__main__":
    main()
