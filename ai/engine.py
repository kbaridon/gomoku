"""Minimax with alpha-beta pruning, driven by iterative deepening.

The search is written in its negamax form: one player's gain is the other's
loss, so a single routine handles both sides by negating the value returned
by the deeper call. Alpha-beta cuts every branch that cannot change the
result, which is only worth much if the good moves are tried first -- hence
the ordering done in `search_space.ranked_moves`.

Depth is not fixed. The engine searches depth 1, then 2, then 3... and keeps
the best move of the last *completed* depth. When the time budget runs out
mid-search the partial result is thrown away and the previous answer is
played, so the move is always the product of a full search.
"""

from time import perf_counter

from board import EMPTY
from rules import is_legal

from .config import BRANCHING, MAX_DEPTH, ROOT_BRANCHING, TIME_BUDGET
from .patterns import WIN_SCORE
from .reporting import REPORT
from .search_space import ranked_moves, search_windows
from .state import SearchState

WIN_VALUE = 10 * WIN_SCORE
INFINITY = float("inf")


class SearchTimeout(Exception):
    """Raised deep in the tree when the move budget is spent."""


def choose_move(game, time_budget=TIME_BUDGET, max_depth=MAX_DEPTH):
    """Best move for the player to play in `game`, or None if there is none."""
    if game.is_over():
        return None

    state = SearchState(game)
    REPORT.start_move(state.current)
    started = perf_counter()
    move = _best_move(state, time_budget, max_depth)
    REPORT.finish_move(move, perf_counter() - started)
    return move


def _best_move(state, time_budget, max_depth):
    """Iterative deepening: search depth 1, then 2, then 3..."""
    if _board_is_empty(state):
        centre = state.board.size // 2
        return (centre, centre)

    # The windows are computed once: the few stones the search adds all fall
    # inside them or in their margin, so they stay valid for the whole tree.
    windows = search_windows(state.board)

    best = None
    deadline = perf_counter() + time_budget
    for depth in range(1, max_depth + 1):
        try:
            move, value = _search_root(state, windows, depth, deadline, best)
        except SearchTimeout:
            break  # partial depth: keep the answer of the last complete one
        if move is None:
            break
        best = move
        REPORT.depth_completed(depth)
        if abs(value) >= WIN_VALUE - 1000:
            # Win or loss proven: deeper search cannot say anything new.
            break

    return best if best is not None else _any_legal_move(state)


def _search_root(state, windows, depth, deadline, previous_best):
    """One full alpha-beta pass at `depth`; returns (move, value)."""
    moves = ranked_moves(state, windows, ROOT_BRANCHING)
    if not moves:
        return None, 0
    moves = _try_first(moves, previous_best)

    best_move, best_value = moves[0][3], -INFINITY
    alpha = -INFINITY
    for score, wins, loses, move in moves:
        value = _move_value(state, windows, move, score, wins, loses,
                            depth, alpha, INFINITY, ply=0, deadline=deadline)
        if value > best_value:
            best_value, best_move = value, move
            alpha = max(alpha, value)
    return best_move, best_value


def _negamax(state, windows, depth, alpha, beta, ply, deadline):
    """Value of the position for the player to move, from `state`."""
    if perf_counter() > deadline:
        raise SearchTimeout

    moves = ranked_moves(state, windows, BRANCHING)
    if not moves:
        return 0

    best = -INFINITY
    for score, wins, loses, move in moves:
        value = _move_value(state, windows, move, score, wins, loses,
                            depth, alpha, beta, ply, deadline)
        if value > best:
            best = value
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break  # the opponent would never let us reach this node
    return best


def _move_value(state, windows, move, score, wins, loses, depth,
                alpha, beta, ply, deadline):
    """Value of one candidate, expanding it only when it is worth it."""
    if wins:
        # Prefer a win now over the same win three moves later.
        return WIN_VALUE - ply
    if loses:
        return -WIN_VALUE + ply
    if depth <= 1:
        # `score` already is the static value of the position after the move.
        return score

    played = state.play(*move)
    try:
        return -_negamax(state, windows, depth - 1, -beta, -alpha,
                         ply + 1, deadline)
    finally:
        state.undo(played)


def _try_first(moves, preferred):
    """Put `preferred` in front: the best move of the previous depth is the
    most likely to be best again, and alpha-beta thrives on that."""
    if preferred is None:
        return moves
    for index, entry in enumerate(moves):
        if entry[3] == preferred:
            return [entry] + moves[:index] + moves[index + 1:]
    return moves


def _board_is_empty(state):
    board = state.board
    return all(board.get(r, c) == EMPTY
               for r in range(board.size) for c in range(board.size))


def _any_legal_move(state):
    """Last resort: the windows produced nothing playable."""
    board = state.board
    for r in range(board.size):
        for c in range(board.size):
            if board.get(r, c) == EMPTY and is_legal(board, r, c, state.current)[0]:
                return (r, c)
    return None
