"""Minimax with alpha-beta pruning, driven by iterative deepening.

The search is written in its negamax form: one player's gain is the other's
loss, so a single routine handles both sides by negating the value returned
by the deeper call. Alpha-beta cuts every branch that cannot change the
result, which is only worth much if the good moves are tried first -- so most
of the machinery here is about trying good moves first.

Depth is not fixed. The engine searches depth 2, then 4, then 6... and keeps
the best move of the last *completed* depth. When the time budget runs out
mid-search the partial result is thrown away and the previous answer is
played, so the move is always the product of a full search.

Ordering a node means playing and evaluating a dozen candidates, which is by
far the most expensive thing here -- so the guesses that cost nothing are
tried first, and a node whose first move causes a cutoff never pays for the
ranking at all:

1. the *transposition table*'s move for this exact position, tried before
   anything is generated;
2. the *killer moves*, the two that most recently caused a cutoff at this
   ply -- but only when the table has nothing to say, since the table's move
   is the better guess and displacing it costs more than the killers save;
3. the *principal variation*, the best move of the previous iteration, put
   first at the root;
4. failing all that, the full static ranking of `search_space.ranked_moves`.

Beyond the first move of a node, the rest are searched with a null window
(principal variation search): proving a move is *not* better than the one
already found is much cheaper than measuring how good it is, and only the
rare move that beats it is searched again for real.
"""

from time import perf_counter

from board import EMPTY
from rules import is_legal

from .config import (BRANCHING_BY_PLY, DEEP_BRANCHING, MAX_DEPTH,
                     ROOT_BRANCHING_DEEP, ROOT_NARROWS_AT, TABLE_CAPACITY,
                     TIME_BUDGET)
from .patterns import WIN_SCORE
from .reporting import REPORT
from .search_space import ranked_moves, search_space, try_move
from .state import SearchState
from .transposition import EXACT, LOWER, UPPER, TranspositionTable

WIN_VALUE = 1_000 * WIN_SCORE
# Above this, a value is a proven win rather than an estimate. No sum of
# static pattern scores can reach it, so the test never fires by accident.
MATE_FLOOR = WIN_VALUE // 2
INFINITY = float("inf")

# Killers are indexed by ply; sized well past anything a search can reach.
_MAX_PLY = 64

TABLE = TranspositionTable(TABLE_CAPACITY)
_killers = [[None, None] for _ in range(_MAX_PLY + 1)]
_stones_last_move = -1


class SearchTimeout(Exception):
    """Raised deep in the tree when the move budget is spent."""


def reset_tables():
    """Forget everything learned so far: a new game starts from nothing."""
    global _stones_last_move
    TABLE.clear()
    for pair in _killers:
        pair[0] = pair[1] = None
    _stones_last_move = -1


def choose_move(game, time_budget=TIME_BUDGET, max_depth=MAX_DEPTH):
    """Best move for the player to play in `game`, or None if there is none."""
    if game.is_over():
        return None

    state = SearchState(game)
    _keep_or_drop_table(state)
    REPORT.start_move(state.current)
    started = perf_counter()
    move = _best_move(state, time_budget, max_depth)
    REPORT.finish_move(move, perf_counter() - started)
    return move


def _keep_or_drop_table(state):
    """Carry the table over to this move; drop it when a new game starts.

    Entries stay valid across a move -- they describe positions, not paths --
    which is what lets the search reuse them, and is worth about a ply: over
    twenty moves of a real game, keeping the table averaged 8.6 plies against
    7.9 with it cleared every move.

    Keeping entries from an *earlier* game would not be wrong either, since
    they still describe their own positions correctly; it would only waste
    room. So the test for a new game is the unambiguous one -- an empty or
    nearly empty board. Counting stones and watching for the number to fall
    would be wrong: a capture takes two off, and that is not a new game. The
    UI also calls `reset_tables` outright when it restarts.
    """
    global _stones_last_move
    stones = sum(1 for row in state.board.grid for cell in row if cell != EMPTY)
    if stones <= 1 and _stones_last_move > 1:
        reset_tables()
    _stones_last_move = stones
    # Killers are indexed by distance from *this* root, so last move's are
    # about the wrong plies. The table is not: it is keyed by position.
    for pair in _killers:
        pair[0] = pair[1] = None


# ---------- iterative deepening ----------


def _best_move(state, time_budget, max_depth):
    """Search depth 2, then 4, then 6... keeping the last complete answer."""
    if not state.nearby:
        centre = state.board.size // 2
        return (centre, centre)

    # The space is computed once: the few stones the search adds all fall
    # inside it or in its margin, so it stays valid for the whole tree.
    space = search_space(state.board)

    best = None
    deadline = perf_counter() + time_budget
    # Even depths only, for two reasons that happen to agree.
    #
    # A leaf is scored right after somebody moved, and the evaluation has no
    # idea a reply is coming: the side that moved last always looks better
    # than it is. An odd-depth search ends on *our* move and inherits that
    # flattery whole -- the same position swings by a factor of two hundred
    # between depth 9 and depth 10. Ending on the opponent's reply cancels it,
    # because both sides have then had their say.
    #
    # It costs nothing to do so. Halving the number of iterations pays for
    # the coarser steps: measured over eight positions at the real budget,
    # the two reach the same depth to within a tenth of a ply. The reason to
    # prefer even is the bias above, not speed.
    for depth in range(2, max(max_depth, 2) + 1, 2):
        try:
            move, value = _search_root(state, space, depth, deadline, best)
        except SearchTimeout:
            break  # partial depth: keep the answer of the last complete one
        if move is None:
            break
        best = move
        REPORT.depth_completed(depth)
        if abs(value) >= MATE_FLOOR:
            # Win or loss proven: deeper search cannot say anything new.
            break

    return best if best is not None else _any_legal_move(state)


def _root_width(depth):
    """How many root moves this iteration looks at.

    Wide while the iterations are cheap, so that every candidate is seen and
    ranked at least once; narrow once the depth is expensive, by which point
    the ranking to narrow by has already been earned.
    """
    if depth < ROOT_NARROWS_AT:
        return _branching(0)
    return min(_branching(0), ROOT_BRANCHING_DEEP)


def _search_root(state, space, depth, deadline, previous_best):
    """One full alpha-beta pass at `depth`; returns (move, value)."""
    moves = ranked_moves(state, space, _root_width(depth))
    if not moves:
        return None, 0
    moves = _try_first(moves, previous_best)

    best_move, best_value = moves[0][3], -INFINITY
    alpha = -INFINITY
    for score, wins, loses, move, captured in moves:
        if best_value == -INFINITY:
            value = _search_move(state, space, move, captured, score, wins,
                                 loses, depth, alpha, INFINITY, 0, deadline)
        else:
            # Everything after the first candidate only has to prove it is
            # not better; the rare one that is gets a real search.
            value = _search_move(state, space, move, captured, score, wins,
                                 loses, depth, alpha, alpha + 1, 0, deadline)
            if value > alpha:
                value = _search_move(state, space, move, captured, score,
                                     wins, loses, depth, alpha, INFINITY, 0,
                                     deadline)
        if value > best_value:
            best_value, best_move = value, move
            if value > alpha:
                alpha = value
    return best_move, best_value


# ---------- the tree ----------


def _branching(ply):
    """How many moves the node at `ply` expands: the beam, narrowing as it goes."""
    if ply < len(BRANCHING_BY_PLY):
        return BRANCHING_BY_PLY[ply]
    return DEEP_BRANCHING


def _negamax(state, space, depth, alpha, beta, ply, deadline):
    """Value of the position for the player to move, from `state`."""
    if perf_counter() > deadline:
        raise SearchTimeout

    key = state.position_key()
    alpha_origin = alpha
    entry = TABLE.get(key)
    table_move = None
    if entry is not None:
        stored_depth, stored_value, flag, table_move = entry
        if stored_depth >= depth:
            value = _from_table(stored_value, ply)
            if flag == EXACT:
                return value
            if flag == LOWER:
                if value > alpha:
                    alpha = value
            elif value < beta:
                beta = value
            if alpha >= beta:
                return value

    best = -INFINITY
    best_move = None
    searched = 0

    for move, captured, score, wins, loses in _ordered_moves(
            state, space, ply, table_move):
        if searched == 0:
            # The first move is the one alpha-beta measures properly; every
            # other only has to prove it is not better.
            value = _search_move(state, space, move, captured, score, wins,
                                 loses, depth, alpha, beta, ply, deadline)
        else:
            value = _search_move(state, space, move, captured, score, wins,
                                 loses, depth, alpha, alpha + 1, ply, deadline)
            if alpha < value < beta:
                value = _search_move(state, space, move, captured, score,
                                     wins, loses, depth, alpha, beta, ply,
                                     deadline)
        searched += 1
        if value > best:
            best, best_move = value, move
            if value > alpha:
                alpha = value
        if alpha >= beta:
            _remember_killer(ply, move)
            break

    if best_move is None:
        return 0  # nothing playable here: treat it as a dead end

    _store(key, depth, best, best_move, alpha_origin, beta, ply)
    return best


def _search_move(state, space, move, captured, score, wins, loses, depth,
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

    played = state.play(move[0], move[1], captured)
    try:
        return -_negamax(state, space, depth - 1, -beta, -alpha, ply + 1,
                         deadline)
    finally:
        state.undo(played)


# ---------- move ordering ----------


def _ordered_moves(state, space, ply, table_move):
    """Every move of this node, best guess first, generated as late as possible.

    The point of the generator is what it does *not* do. Ranking a node means
    playing and evaluating a dozen candidates, and a node whose first move
    causes a cutoff never needs any of that -- so the cheap guesses (the
    table's move, then the killers) are yielded one at a time, and the full
    ranking is only paid for if the caller comes back for more.

    The guesses count against the beam rather than adding to it. They are
    moves like any other, and letting them widen the node instead would undo
    the narrowing the beam exists for: one extra move per ply is half again
    as wide, which compounds to fifty times over ten plies.
    """
    width = _branching(ply)
    guesses = []
    grid = state.board.grid
    cells = space.cells
    hints = (table_move,) if table_move is not None else tuple(_killers[ply])
    for move in hints:
        if move is None or move in guesses:
            continue
        r, c = move
        if grid[r][c] != EMPTY or move not in cells:
            continue
        outcome = try_move(state, r, c)
        if outcome is None:
            continue
        guesses.append(move)
        score, wins, loses, captured = outcome
        yield move, captured, score, wins, loses
        if len(guesses) >= width:
            return

    for score, wins, loses, move, captured in ranked_moves(
            state, space, width - len(guesses), skip=guesses):
        yield move, captured, score, wins, loses


def _remember_killer(ply, move):
    """A move that caused a cutoff here is worth trying first next time."""
    if ply > _MAX_PLY:
        return
    pair = _killers[ply]
    if pair[0] != move:
        pair[1] = pair[0]
        pair[0] = move


def _try_first(moves, preferred):
    """Put `preferred` in front: the best move of the previous depth is the
    most likely to be best again, and alpha-beta thrives on that."""
    if preferred is None:
        return moves
    for index, entry in enumerate(moves):
        if entry[3] == preferred:
            return [entry] + moves[:index] + moves[index + 1:]
    return moves


# ---------- transposition table ----------


def _store(key, depth, value, move, alpha_origin, beta, ply):
    if value <= alpha_origin:
        flag = UPPER
    elif value >= beta:
        flag = LOWER
    else:
        flag = EXACT
    TABLE.store(key, depth, _to_table(value, ply), flag, move)


def _to_table(value, ply):
    """Make a proven win independent of where in the tree it was found.

    A mate is scored by distance from the root, so the same position reached
    at another ply would read the wrong number back. Stored relative to the
    node, it means the same thing everywhere.
    """
    if value >= MATE_FLOOR:
        return value + ply
    if value <= -MATE_FLOOR:
        return value - ply
    return value


def _from_table(value, ply):
    if value >= MATE_FLOOR:
        return value - ply
    if value <= -MATE_FLOOR:
        return value + ply
    return value


# ---------- fallback ----------


def _any_legal_move(state):
    """Last resort: the search space produced nothing playable."""
    board = state.board
    for r in range(board.size):
        for c in range(board.size):
            if board.get(r, c) == EMPTY and is_legal(board, r, c, state.current)[0]:
                return (r, c)
    return None
