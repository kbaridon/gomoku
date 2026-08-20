"""Straightforward implementations of what the engine does cleverly.

Nothing here is used to play. Each function is the obvious way to compute
something the engine computes some faster way, and exists so the visualiser
can put a number on the difference instead of asserting there is one.

They are written the way the code would look if the optimisation had never
been made -- readable, correct, and slow.
"""

from board import ALL_DIRECTIONS, EMPTY, opponent

from ai.config import CRITICAL_RUN, DEFENCE_WEIGHT, TACTICAL_TAIL
from ai.evaluation import Evaluator
from ai.patterns import (MASK, SHAPE_PATTERNS, THREAT_PATTERNS, _VIEWPOINT)
from ai.shapes import longest_run

# A neighbour one step away matters more than one two steps away.
PROXIMITY_WEIGHTS = ((1, 4), (2, 1))


def find_captures(board, r, c, color):
    """`Board.find_captures` without the pre-resolved ray table."""
    opp = opponent(color)
    captured = []
    for dr, dc in ALL_DIRECTIONS:
        positions = [(r + i * dr, c + i * dc) for i in (1, 2, 3)]
        if not all(board.in_bounds(pr, pc) for pr, pc in positions):
            continue
        if (board.get(*positions[0]) == opp
                and board.get(*positions[1]) == opp
                and board.get(*positions[2]) == color):
            captured.append(positions[0])
            captured.append(positions[1])
    return captured


def proximity(board, r, c):
    """How crowded the surroundings of a cell are, counted on the spot.

    The engine keeps this number up to date as stones appear and disappear;
    this is what computing it from the board costs instead.
    """
    score = 0
    for dr, dc in ALL_DIRECTIONS:
        for distance, weight in PROXIMITY_WEIGHTS:
            rr, cc = r + dr * distance, c + dc * distance
            if board.in_bounds(rr, cc) and board.get(rr, cc) != EMPTY:
                score += weight
    return score


def shortlist(state, space, size):
    """`search_space.shortlist` with the proximity counted per node.

    Deliberately identical in every other respect -- the same cut, the same
    tactical promotion, the same order -- so that the difference between this
    and the real one is the incremental counting and nothing else. An ablation
    that quietly removed two things at once would credit the wrong one.
    """
    board = state.board
    scored = []
    for r, c in space.cells:
        if board.get(r, c) != EMPTY:
            continue
        weight = proximity(board, r, c)
        if weight:
            scored.append((weight, r, c))
    scored.sort(reverse=True)
    if len(scored) <= size:
        return scored

    evaluator = state.evaluator
    tail = scored[size:]
    urgent = [entry for entry in tail[:TACTICAL_TAIL]
              if longest_run(evaluator, entry[1], entry[2]) >= CRITICAL_RUN]
    decisive = evaluator.decisive_cells()
    if decisive:
        seen = {(r, c) for _, r, c in urgent}
        urgent = [entry for entry in tail
                  if (entry[1], entry[2]) in decisive
                  and (entry[1], entry[2]) not in seen] + urgent
    if not urgent:
        del scored[size:]
        return scored
    return urgent[:size] + scored[:max(0, size - len(urgent))]


def evaluate(state, color):
    """`SearchState.evaluate` with the whole goban re-scored from scratch.

    Same answer, `DEFENCE_WEIGHT` included: the only difference is that the
    running totals are thrown away and rebuilt.
    """
    from ai.evaluation import capture_score

    fresh = Evaluator(state.board)
    opp = opponent(color)
    own = fresh.pattern_score(color) + capture_score(state.captures[color])
    theirs = fresh.pattern_score(opp) + capture_score(state.captures[opp])
    return own - int(theirs * DEFENCE_WEIGHT)


def matched_shapes(line, color):
    """Which patterns `ai.patterns.score_line` found on this line, and where.

    `score_line` returns one number. This walks the same two pattern lists in
    the same order, with the same masking of stones already accounted for, and
    returns the pieces the number is made of, so a visualiser can name the
    shape instead of quoting a total.

    Returns ``(index, pattern, value)`` triples, positions being indices into
    the line as given -- edges included, so cell `i` of the line is at `i + 1`.
    `tests/test_viz.py` checks the pieces add up to `score_line`'s answer.
    """
    own = line.translate(_VIEWPOINT[color])
    masked = own
    found = []
    for pattern, value in SHAPE_PATTERNS:
        start = 0
        while True:
            at = masked.find(pattern, start)
            if at < 0:
                break
            found.append((at, pattern, value))
            end = at + len(pattern)
            masked = (masked[:at]
                      + masked[at:end].replace("X", MASK)
                      + masked[end:])
            start = at + 1
    # Threats are matched on the line as it stands: a pair inside a strong
    # three is still capturable, and `score_line` scores both.
    for pattern, value in THREAT_PATTERNS:
        start = 0
        while True:
            at = own.find(pattern, start)
            if at < 0:
                break
            found.append((at, pattern, value))
            start = at + 1
    found.sort()
    return found
