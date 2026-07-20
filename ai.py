import random

from board import BOARD_SIZE, EMPTY
from rules import is_legal


def choose_move(game):
    # ici random, algo a implementer
    board = game.board
    color = game.current
    legal = [
        (r, c)
        for r in range(BOARD_SIZE)
        for c in range(BOARD_SIZE)
        if board.get(r, c) == EMPTY and is_legal(board, r, c, color)[0]
    ]
    if not legal:
        return None
    return random.choice(legal)
