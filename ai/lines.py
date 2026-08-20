"""Pre-computed line geometry of the goban.

The evaluator scores the board one *line* at a time, a line being a maximal
sequence of cells along one of the four axes (row, column, both diagonals).
The layout never changes, so it is computed once at import time:

- ``LINES[i]``       -> the cells of line ``i``, in order.
- ``CELL_LINES[cell]`` -> the ``(line_id, index)`` pairs the cell belongs to.

With that table, changing one stone means re-scoring at most four lines
instead of the whole board.
"""

from board import BOARD_SIZE

AXES = ((0, 1), (1, 0), (1, 1), (1, -1))

# Lines shorter than this cannot hold any pattern worth scoring.
MIN_LINE_LENGTH = 5


def _build(size):
    lines = []
    cell_lines = {(r, c): [] for r in range(size) for c in range(size)}

    def inside(r, c):
        return 0 <= r < size and 0 <= c < size

    for dr, dc in AXES:
        for r in range(size):
            for c in range(size):
                # Only start a line at a cell with no predecessor on this axis.
                if inside(r - dr, c - dc):
                    continue
                cells = []
                rr, cc = r, c
                while inside(rr, cc):
                    cells.append((rr, cc))
                    rr, cc = rr + dr, cc + dc
                if len(cells) < MIN_LINE_LENGTH:
                    continue
                line_id = len(lines)
                lines.append(cells)
                for index, cell in enumerate(cells):
                    cell_lines[cell].append((line_id, index))
    return lines, cell_lines


LINES, CELL_LINES = _build(BOARD_SIZE)


# ---------- neighbourhood ----------

# Weights of the cells around a stone, by Chebyshev ray distance. A stone one
# step away makes a cell far more interesting than one two steps away.
PROXIMITY_WEIGHTS = ((1, 4), (2, 1))


def _build_neighbourhood(size):
    """cell -> the (row, col, weight) it radiates onto, bounds already checked.

    `SearchState` keeps a proximity count per cell and refreshes it whenever a
    stone appears or disappears. Pre-resolving the geometry here means that
    refresh is a flat loop over a tuple, with no arithmetic and no bounds test.
    """
    rays = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            if (dr, dc) != (0, 0)]
    table = {}
    for r in range(size):
        for c in range(size):
            around = []
            for dr, dc in rays:
                for distance, weight in PROXIMITY_WEIGHTS:
                    rr, cc = r + dr * distance, c + dc * distance
                    if 0 <= rr < size and 0 <= cc < size:
                        around.append((rr, cc, weight))
            table[(r, c)] = tuple(around)
    return table


NEIGHBOURHOOD = _build_neighbourhood(BOARD_SIZE)
