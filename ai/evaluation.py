"""Incremental board evaluation.

Scoring the whole goban costs far too much to do it at every node, so the
evaluator keeps one score per line and refreshes only the lines a changed
cell belongs to (four at most). Playing a move therefore costs a handful of
line re-scores instead of a full board scan, and taking it back costs the
same.
"""

from board import BLACK, WHITE

from .lines import CELL_LINES, LINES
from .patterns import CELL_CHARS, WIN_SCORE, score_line

# 0, 1, ... 5 captured pairs. Five pairs is ten stones, i.e. a win.
CAPTURE_SCORES = (0, 800, 2_400, 6_000, 20_000, WIN_SCORE)


class Evaluator:
    """Keeps the pattern score of both players up to date, line by line."""

    def __init__(self, board):
        self._chars = [
            [CELL_CHARS[board.get(r, c)] for r, c in cells] for cells in LINES
        ]
        self._scores = [self._score_line(index) for index in range(len(LINES))]
        self.totals = {
            BLACK: sum(black for black, _ in self._scores),
            WHITE: sum(white for _, white in self._scores),
        }

    def _score_line(self, index):
        # The edges are part of the string: a four against the border is not
        # an open four.
        line = "#" + "".join(self._chars[index]) + "#"
        return score_line(line, BLACK), score_line(line, WHITE)

    def set_cell(self, r, c, value):
        """Mirror a board change and refresh the lines through (r, c)."""
        char = CELL_CHARS[value]
        for line_id, position in CELL_LINES[(r, c)]:
            self._chars[line_id][position] = char
            old_black, old_white = self._scores[line_id]
            new_black, new_white = self._score_line(line_id)
            self._scores[line_id] = (new_black, new_white)
            self.totals[BLACK] += new_black - old_black
            self.totals[WHITE] += new_white - old_white

    def pattern_score(self, color):
        return self.totals[color]


def capture_score(captured_stones):
    """Value of having captured `captured_stones` opponent stones."""
    pairs = min(captured_stones // 2, len(CAPTURE_SCORES) - 1)
    return CAPTURE_SCORES[pairs]
