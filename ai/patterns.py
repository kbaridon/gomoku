"""Pattern table and line scoring.

A line is handed over as a string seen from one player's point of view:

    'X' own stone     'O' opponent stone     '.' empty     '#' edge of board

Two families of patterns are recognised.

``SHAPE_PATTERNS`` are the offensive shapes, matched from the strongest to
the weakest. Once a shape is matched, its own stones are masked out so that
the same stones cannot be counted twice (a five is not also a four, a three
and two twos). Masking keeps the score of a line proportional to what is
really on it.

``THREAT_PATTERNS`` are matched independently, without masking, because a
weakness overlaps the shape it weakens: a pair that is part of a strong
three can still be captured, and both facts must show up in the score.
"""

from functools import lru_cache

from board import BLACK, EMPTY, WHITE

WIN_SCORE = 10_000_000

# Stones in a row that win the game.
ALIGNMENT_LENGTH = 5

# Character used to blank out stones already accounted for.
MASK = "_"

SHAPE_PATTERNS = (
    # Five in a row: the game is decided.
    ("XXXXX", WIN_SCORE),
    # Open four: unstoppable, both extensions win.
    (".XXXX.", 500_000),
    # Fours with a single completion point (closed or broken).
    ("XXXX.", 60_000),
    (".XXXX", 60_000),
    ("XX.XX", 60_000),
    ("XXX.X", 60_000),
    ("X.XXX", 60_000),
    # Free threes: they become an open four if left alone.
    (".XXX.", 20_000),
    (".XX.X.", 12_000),
    (".X.XX.", 12_000),
    # Blocked threes.
    ("XXX.", 2_000),
    (".XXX", 2_000),
    ("XX.X", 1_500),
    ("X.XX", 1_500),
    # Development moves.
    (".XX.", 600),
    (".X.X.", 300),
    ("XX", 100),
    (".X.", 20),
)

THREAT_PATTERNS = (
    # An own pair flanked by an opponent stone with a free cell behind it is
    # one move away from being captured.
    ("OXX.", -1_500),
    (".XXO", -1_500),
)

# Board values -> the neutral alphabet stored per line.
CELL_CHARS = {EMPTY: ".", BLACK: "B", WHITE: "W"}

_VIEWPOINT = {
    BLACK: str.maketrans("BW", "XO"),
    WHITE: str.maketrans("BW", "OX"),
}


def _score_shapes(line):
    total = 0
    for pattern, value in SHAPE_PATTERNS:
        start = 0
        while True:
            at = line.find(pattern, start)
            if at < 0:
                break
            total += value
            end = at + len(pattern)
            # Consume the stones, leave the empty cells available.
            line = line[:at] + line[at:end].replace("X", MASK) + line[end:]
            start = at + 1
    return total


def _score_threats(line):
    total = 0
    for pattern, value in THREAT_PATTERNS:
        start = 0
        while True:
            at = line.find(pattern, start)
            if at < 0:
                break
            total += value
            start = at + 1
    return total


@lru_cache(maxsize=200_000)
def five_gaps(line):
    """Where each colour would align five on `line`; returns (black, white).

    Each is a tuple of *cell* indexes -- the edge marker in front of the text
    is already discounted, so they index the line's cells directly.

    This is the one shape the move generator may never miss, and the reason
    it needs its own answer rather than the pattern score's. Candidates are
    ranked by how crowded their surroundings are, and the cell that completes
    a five is one of the loneliest on the board: it sits at the end of a row
    with a single stone beside it, while the cells in the middle of any crowd
    have six or eight. It was measured to fall past the promotion window and
    out of the shortlist -- so a forced win three plies down was invisible,
    and every score along that line was wrong. See `search_space.shortlist`.

    Read off the line text, so no stone is placed and nothing is evaluated;
    cached like the pattern score, on the same keys.
    """
    found = []
    for stone in ("B", "W"):
        gaps = []
        for at in range(1, len(line) - 1):
            if line[at] != ".":
                continue
            run = 1
            before = at - 1
            while line[before] == stone:      # the edge marker stops this
                run += 1
                before -= 1
            after = at + 1
            while line[after] == stone:
                run += 1
                after += 1
            if run >= ALIGNMENT_LENGTH:
                gaps.append(at - 1)
        found.append(tuple(gaps))
    return tuple(found)


@lru_cache(maxsize=200_000)
def score_line(line, color):
    """Score `line` (a 'B'/'W'/'.' string, edges included) for `color`.

    Results are cached: the same line content shows up again and again while
    the search plays and takes back moves.
    """
    own = line.translate(_VIEWPOINT[color])
    return _score_shapes(own) + _score_threats(own)
