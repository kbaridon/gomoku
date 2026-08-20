"""Questions about local shape, answered from the evaluator's lines.

`rules.is_legal` is the reference implementation and the one the game itself
plays by. It is also, by a wide margin, the most expensive thing the search
does: forbidding a move means proving it does not open two free threes at
once, and the reference proves it by dropping the stone on the board and
re-reading eleven cells along each of the four axes, for every candidate of
every node.

Everything it re-reads is already in memory. `Evaluator.text` holds each line
of the goban as a string, kept up to date move by move, so the eleven cells
around a candidate are a slice -- and the stone itself does not need to be
placed, only substituted into the slice.

That makes the axis test a pure function of an eleven-character string, which
is worth caching: the same local shape comes back over and over as the search
plays and takes back moves.

The same trick answers the other question the search asks about a cell --
how long a line a stone there would make, for either colour -- and for the
same reason: the run through a cell is a property of nine characters of
text, and the text is already there.

The legality verdict is identical to `rules.is_legal`'s; `tests/test_ai.py`
checks it against the reference over random positions.
"""

from functools import lru_cache

from board import BLACK, WHITE
from rules import FREE_THREE_PATTERNS

from .lines import CELL_LINES

# Cells read on each side of the candidate. Five is what the longest pattern
# needs: `.XX.X.` reaches four cells out, and its edge one more.
RADIUS = 5

# Neutral line alphabet ('.', 'B', 'W') -> the point of view of one player.
_VIEWPOINT = {
    BLACK: str.maketrans("BW", "XO"),
    WHITE: str.maketrans("BW", "OX"),
}

_EDGE = "#"


@lru_cache(maxsize=100_000)
def _axis_makes_free_three(line):
    """Does this axis hold a free three *through the candidate*?

    `line` is the 2 * RADIUS + 1 characters centred on the candidate, seen from
    the mover's side, with the candidate itself already set to 'X'. A pattern
    found somewhere else on the axis does not count: the rule only forbids the
    threes the move itself creates.
    """
    for pattern in FREE_THREE_PATTERNS:
        length = len(pattern)
        for start in range(len(line) - length + 1):
            if line[start:start + length] != pattern:
                continue
            offset = RADIUS - start
            if 0 <= offset < length and pattern[offset] == "X":
                return True
    return False


def free_three_count(evaluator, r, c, color, stop_at=2):
    """Free threes the move at (r, c) would open, counted up to `stop_at`.

    Counting stops as soon as `stop_at` is reached: the caller only ever asks
    whether there are two, and the fourth axis costs as much as the first.
    """
    view = _VIEWPOINT[color]
    lines = evaluator.text
    count = 0
    for line_id, index in CELL_LINES[(r, c)]:
        line = lines[line_id]
        # Cell `index` of the line is character `index + 1` of its text, the
        # edge marker sitting in front.
        low, high = index + 1 - RADIUS, index + 2 + RADIUS
        # Running off the text is running off the board: pad with the same
        # edge marker the reference uses.
        segment = (_EDGE * max(0, -low)
                   + line[max(0, low):high]
                   + _EDGE * max(0, high - len(line)))
        segment = segment.translate(view)
        segment = segment[:RADIUS] + "X" + segment[RADIUS + 1:]
        if _axis_makes_free_three(segment):
            count += 1
            if count >= stop_at:
                break
    return count


# Cells read on each side of the candidate for the run question: four, so
# that any five through it fits in the window.
RUN_RADIUS = 4


@lru_cache(maxsize=200_000)
def _segment_run(segment):
    """Longest run *through the centre* either colour would get by filling it.

    `segment` is the 2 * RUN_RADIUS + 1 characters centred on the candidate,
    in the neutral 'B'/'W'/'.'/'#' alphabet -- neutral because the answer
    matters whoever the stone would belong to. A run elsewhere in the window
    does not count: the question is what *this* cell is worth.
    """
    longest = 0
    for stone in ("B", "W"):
        filled = segment[:RUN_RADIUS] + stone + segment[RUN_RADIUS + 1:]
        run = 1
        at = RUN_RADIUS - 1
        while at >= 0 and filled[at] == stone:
            run += 1
            at -= 1
        at = RUN_RADIUS + 1
        while at < len(filled) and filled[at] == stone:
            run += 1
            at += 1
        if run > longest:
            longest = run
    return longest


def longest_run(evaluator, r, c):
    """The longest line a stone at (r, c) would make, for whichever colour.

    This is what the proximity ranking cannot see. Proximity counts
    neighbours in every direction alike, so it scores the cells *beside* a
    line far above the cells that *extend* it: the end of a three has one
    neighbour, a cell alongside it has three. Yet extending the three is the
    move that wins or loses the game, and the cell alongside decides nothing.
    """
    lines = evaluator.text
    longest = 0
    for line_id, index in CELL_LINES[(r, c)]:
        line = lines[line_id]
        low = index + 1 - RUN_RADIUS
        high = index + 2 + RUN_RADIUS
        segment = (_EDGE * max(0, -low)
                   + line[max(0, low):high]
                   + _EDGE * max(0, high - len(line)))
        run = _segment_run(segment)
        if run > longest:
            longest = run
    return longest


def is_playable(state, r, c, captured):
    """Is (r, c) a legal move for the player to play, given its captures?

    The cell is assumed empty and inside the board -- the candidate generator
    only ever offers such cells. A capturing move is never forbidden, which is
    also what keeps the common case cheap.
    """
    if captured:
        return True
    return free_three_count(state.evaluator, r, c, state.current) < 2
