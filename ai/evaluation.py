"""Incremental board evaluation.

Scoring the whole goban costs far too much to do it at every node, so the
evaluator keeps one score per line and refreshes only the lines a changed
cell belongs to (four at most). Playing a move therefore costs a handful of
line re-scores instead of a full board scan, and taking it back costs the
same.
"""

from board import BLACK, WHITE

from .lines import CELL_LINES, LINES
from .patterns import CELL_CHARS, WIN_SCORE, five_gaps, score_line

# What having captured 0, 1, ... 5 pairs is worth. Five pairs is ten stones,
# which is the game.
#
# The old scale ran 0, 800, 2 400, 6 000, 20 000 and then jumped straight to
# the win, which made eight captured stones -- one pair from the end -- worth
# exactly as much as a single open three, and a twentieth of a closed four.
# The engine felt no urgency at all until the game was already over.
#
# It ramps steeply now, ending between a closed four (60 000) and an open one
# (500 000): four pairs is a standing threat over every pair the opponent
# owns, which is a serious advantage but not yet a won game, since it is only
# cashed if a capture is actually available.
#
# MEASURED: 18 wins out of 24 against the old scale, over twelve varied
# openings with colours swapped.
CAPTURE_SCORES = (0, 1_000, 5_000, 25_000, 120_000, WIN_SCORE)


class Evaluator:
    """Keeps the pattern score of both players up to date, line by line."""

    def __init__(self, board):
        # Public, and the only representation of a line there is: the pattern
        # scorer and `ai.shapes` both read these strings, so neither
        # ever walks the board. The edges are part of the string -- a four
        # against the border is not an open four -- which also means cell `i`
        # of a line sits at index `i + 1` of its text.
        self.text = [
            "#" + "".join(CELL_CHARS[board.get(r, c)] for r, c in cells) + "#"
            for cells in LINES
        ]
        self._scores = [self._score_line(index) for index in range(len(LINES))]
        self.totals = {
            BLACK: sum(black for black, _ in self._scores),
            WHITE: sum(white for _, white in self._scores),
        }
        # Lines on which one more stone of that colour would make five. Kept
        # as line ids rather than cells: a line either has such a gap or it
        # does not, so the set is a two-line update per changed line, and it
        # is empty in the overwhelming majority of positions.
        self.five_lines = {BLACK: set(), WHITE: set()}
        for index in range(len(LINES)):
            self._refresh_five_lines(index)

    def _score_line(self, index):
        line = self.text[index]
        return score_line(line, BLACK), score_line(line, WHITE)

    def _refresh_five_lines(self, index):
        black, white = five_gaps(self.text[index])
        for color, gaps in ((BLACK, black), (WHITE, white)):
            if gaps:
                self.five_lines[color].add(index)
            else:
                self.five_lines[color].discard(index)

    def decisive_cells(self):
        """Every empty cell that ends the game at once, for either colour.

        The move that completes a five, and the move that stops the
        opponent's -- they are the same cells. The move generator ranks
        candidates by how crowded their surroundings are, which puts these at
        the bottom (see `patterns.five_gaps`), so it needs them named.

        Nearly always empty, and then this costs two set tests.
        """
        cells = set()
        for color in (BLACK, WHITE):
            index = 0 if color == BLACK else 1
            for line_id in self.five_lines[color]:
                gaps = five_gaps(self.text[line_id])[index]
                line = LINES[line_id]
                cells.update(line[at] for at in gaps)
        return cells

    def set_cell(self, r, c, value):
        """Mirror a board change and refresh the lines through (r, c)."""
        char = CELL_CHARS[value]
        text = self.text
        scores = self._scores
        totals = self.totals
        for line_id, position in CELL_LINES[(r, c)]:
            # Substituting one character beats rebuilding the line from a
            # list of them, and this runs a few times per move played.
            line = text[line_id]
            at = position + 1
            text[line_id] = line[:at] + char + line[at + 1:]
            old_black, old_white = scores[line_id]
            new_black, new_white = self._score_line(line_id)
            scores[line_id] = (new_black, new_white)
            totals[BLACK] += new_black - old_black
            totals[WHITE] += new_white - old_white
            self._refresh_five_lines(line_id)

    def pattern_score(self, color):
        return self.totals[color]


def capture_score(captured_stones):
    """Value of having captured `captured_stones` opponent stones."""
    pairs = min(captured_stones // 2, len(CAPTURE_SCORES) - 1)
    return CAPTURE_SCORES[pairs]
