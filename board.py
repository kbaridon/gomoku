EMPTY = 0
BLACK = 1
WHITE = 2
BOARD_SIZE = 19

STONE_NAME = {BLACK: "Black", WHITE: "White"}

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]

ALL_DIRECTIONS = [
    (dr, dc)
    for dr in (-1, 0, 1)
    for dc in (-1, 0, 1)
    if (dr, dc) != (0, 0)
]


def opponent(color):
    if color == BLACK:
        return WHITE
    return BLACK


_CAPTURE_RAYS = {}


def _capture_rays(size):
    """cell -> the (r1, c1, r2, c2, r3, c3) triples a capture could use.

    Only the directions where all three cells stay on the board are kept, so
    the caller never has to test bounds. Built once per board size.
    """
    rays = _CAPTURE_RAYS.get(size)
    if rays is not None:
        return rays
    rays = {}
    for r in range(size):
        for c in range(size):
            here = []
            for dr, dc in ALL_DIRECTIONS:
                cells = [(r + i * dr, c + i * dc) for i in (1, 2, 3)]
                if all(0 <= pr < size and 0 <= pc < size for pr, pc in cells):
                    here.append((cells[0][0], cells[0][1],
                                 cells[1][0], cells[1][1],
                                 cells[2][0], cells[2][1]))
            rays[(r, c)] = tuple(here)
    _CAPTURE_RAYS[size] = rays
    return rays


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
        """Return positions captured if `color` is placed at (r, c).

        A capture flanks exactly two adjacent opponent stones on a line —
        pattern is (color, opp, opp, color) starting from the placed stone.
        Single stones and triples are never captured.

        The AI calls this once per candidate move at every node it searches,
        so the geometry — which three cells to read in each direction, and
        which directions stay on the board at all — is resolved once in
        `_capture_rays` and only the three reads are left here.
        """
        opp = opponent(color)
        grid = self.grid
        captured = []
        for r1, c1, r2, c2, r3, c3 in _capture_rays(self.size)[(r, c)]:
            if (grid[r1][c1] == opp and grid[r2][c2] == opp
                    and grid[r3][c3] == color):
                captured.append((r1, c1))
                captured.append((r2, c2))
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
