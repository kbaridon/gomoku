"""Board state and low-level stone operations.

The board is a 19x19 grid indexed as `grid[row][col]` where `row = 0` is the
top row and `col = 0` is the left column. Cells hold one of `EMPTY`, `BLACK`
or `WHITE`.
"""

EMPTY = 0
BLACK = 1
WHITE = 2
BOARD_SIZE = 19

STONE_NAME = {BLACK: "Black", WHITE: "White"}

# The four axes on which alignments (and captures) can occur. We only need
# one direction per axis; the reverse is handled by scanning both ways when
# needed.
DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]

# All 8 unit vectors around a cell — used when scanning for captures because
# a capture pattern can start in any of the 8 directions from the placed stone.
ALL_DIRECTIONS = [
    (dr, dc)
    for dr in (-1, 0, 1)
    for dc in (-1, 0, 1)
    if (dr, dc) != (0, 0)
]


def opponent(color):
    return WHITE if color == BLACK else BLACK


class Board:
    def __init__(self, size=BOARD_SIZE):
        self.size = size
        self.grid = [[EMPTY] * size for _ in range(size)]

    def in_bounds(self, r, c):
        return 0 <= r < self.size and 0 <= c < self.size

    def get(self, r, c):
        return self.grid[r][c]

    def set(self, r, c, value):
        self.grid[r][c] = value

    def is_empty(self, r, c):
        return self.in_bounds(r, c) and self.grid[r][c] == EMPTY

    def find_captures(self, r, c, color):
        """Return the positions that get captured if `color` is placed at (r, c).

        A capture flanks exactly two adjacent opponent stones on a line —
        pattern is (color, opp, opp, color) starting from the placed stone.
        Single stones and triples are never captured.
        """
        opp = opponent(color)
        captured = []
        for dr, dc in ALL_DIRECTIONS:
            positions = [(r + i * dr, c + i * dc) for i in (1, 2, 3)]
            if not all(self.in_bounds(pr, pc) for pr, pc in positions):
                continue
            v1 = self.get(*positions[0])
            v2 = self.get(*positions[1])
            v3 = self.get(*positions[2])
            if v1 == opp and v2 == opp and v3 == color:
                captured.append(positions[0])
                captured.append(positions[1])
        return captured

    def _count_run(self, r, c, dr, dc, color):
        n = 0
        while self.in_bounds(r, c) and self.get(r, c) == color:
            n += 1
            r += dr
            c += dc
        return n

    def find_all_alignments(self, color):
        """Return every maximal alignment of length >= 5 for `color`.

        Each alignment is returned as a frozenset of (row, col) positions.
        We de-duplicate by only starting a run at a cell whose predecessor
        on the same axis is not `color`.
        """
        alignments = []
        for r in range(self.size):
            for c in range(self.size):
                if self.get(r, c) != color:
                    continue
                for dr, dc in DIRECTIONS:
                    pr, pc = r - dr, c - dc
                    if self.in_bounds(pr, pc) and self.get(pr, pc) == color:
                        continue
                    length = self._count_run(r, c, dr, dc, color)
                    if length >= 5:
                        positions = frozenset(
                            (r + i * dr, c + i * dc) for i in range(length)
                        )
                        alignments.append(positions)
        return alignments
