"""Where the engine is allowed to look.

Considering the 361 intersections of an empty goban is hopeless, and the
usual trick -- one bounding box around every stone -- wastes a huge amount
of space as soon as the fight spreads to two corners of the board.

So the space is described by *several* rectangular windows instead:

1. stones close to each other are grouped into clusters;
2. each cluster gives one rectangle, its bounding box;
3. two rectangles are merged only while the merge wastes little area, so a
   local fight stays in its own small window;
4. every window is then grown by a margin, the border where the next stone
   is likely to be played.

The candidate moves are the empty cells of those windows, ranked so that
alpha-beta sees the promising ones first.
"""

from board import ALL_DIRECTIONS, EMPTY
from rules import is_legal

from .config import (BRANCHING, CLUSTER_RADIUS, MAX_WASTE_RATIO,
                     SHORTLIST_SIZE, WINDOW_MARGIN)


class Window:
    """An inclusive rectangle of the goban."""

    __slots__ = ("r0", "c0", "r1", "c1")

    def __init__(self, r0, c0, r1, c1):
        self.r0, self.c0, self.r1, self.c1 = r0, c0, r1, c1

    @property
    def area(self):
        return (self.r1 - self.r0 + 1) * (self.c1 - self.c0 + 1)

    def union(self, other):
        return Window(min(self.r0, other.r0), min(self.c0, other.c0),
                      max(self.r1, other.r1), max(self.c1, other.c1))

    def overlap_area(self, other):
        rows = min(self.r1, other.r1) - max(self.r0, other.r0) + 1
        cols = min(self.c1, other.c1) - max(self.c0, other.c0) + 1
        if rows <= 0 or cols <= 0:
            return 0
        return rows * cols

    def grown(self, margin, size):
        return Window(max(0, self.r0 - margin), max(0, self.c0 - margin),
                      min(size - 1, self.r1 + margin),
                      min(size - 1, self.c1 + margin))

    def cells(self):
        for r in range(self.r0, self.r1 + 1):
            for c in range(self.c0, self.c1 + 1):
                yield r, c

    def __repr__(self):
        return f"Window({self.r0}, {self.c0}, {self.r1}, {self.c1})"


def _clusters(stones, radius):
    """Group stones that are within `radius` (Chebyshev) of each other."""
    groups = []
    for stone in stones:
        r, c = stone
        touched = [
            group for group in groups
            if any(max(abs(r - gr), abs(c - gc)) <= radius for gr, gc in group)
        ]
        merged = [stone]
        for group in touched:
            merged.extend(group)
            groups.remove(group)
        groups.append(merged)
    return groups


def _bounding_window(stones):
    rows = [r for r, _ in stones]
    cols = [c for _, c in stones]
    return Window(min(rows), min(cols), max(rows), max(cols))


def _wasted_area(a, b):
    """Area the union of `a` and `b` adds without covering any stone group."""
    return a.union(b).area - (a.area + b.area - a.overlap_area(b))


def _merge_cheap_pairs(windows, max_waste_ratio):
    """Merge windows as long as merging them wastes little space."""
    windows = list(windows)
    while len(windows) > 1:
        best = None
        for i in range(len(windows)):
            for j in range(i + 1, len(windows)):
                union = windows[i].union(windows[j])
                waste = _wasted_area(windows[i], windows[j])
                if waste > max_waste_ratio * union.area:
                    continue
                if best is None or waste < best[0]:
                    best = (waste, i, j, union)
        if best is None:
            break
        _, i, j, union = best
        windows.pop(j)
        windows.pop(i)
        windows.append(union)
    return windows


def search_windows(board, margin=WINDOW_MARGIN, radius=CLUSTER_RADIUS,
                   max_waste_ratio=MAX_WASTE_RATIO):
    """The rectangular windows covering the interesting part of the board."""
    stones = [
        (r, c)
        for r in range(board.size)
        for c in range(board.size)
        if board.get(r, c) != EMPTY
    ]
    if not stones:
        centre = board.size // 2
        return [Window(centre, centre, centre, centre)]

    boxes = [_bounding_window(group) for group in _clusters(stones, radius)]
    boxes = _merge_cheap_pairs(boxes, max_waste_ratio)
    return [box.grown(margin, board.size) for box in boxes]


def window_cells(windows):
    """Every cell of `windows`, each one listed once."""
    cells = set()
    for window in windows:
        cells.update(window.cells())
    return cells


# ---------- candidate moves ----------

# A neighbour one step away matters much more than one two steps away.
_PROXIMITY_WEIGHTS = ((1, 4), (2, 1))


def _proximity(board, r, c):
    """How crowded the surroundings of an empty cell are."""
    score = 0
    for dr, dc in ALL_DIRECTIONS:
        for distance, weight in _PROXIMITY_WEIGHTS:
            rr, cc = r + dr * distance, c + dc * distance
            if board.in_bounds(rr, cc) and board.get(rr, cc) != EMPTY:
                score += weight
    return score


def shortlist(state, windows, size=SHORTLIST_SIZE):
    """Legal moves of the windows, roughly ranked, cut down to `size`.

    This first pass is deliberately cheap: it only looks at how close a cell
    is to existing stones. The expensive ranking happens afterwards, on the
    few cells that survive here.
    """
    board = state.board
    scored = []
    for r, c in window_cells(windows):
        if board.get(r, c) != EMPTY:
            continue
        proximity = _proximity(board, r, c)
        if proximity == 0:
            continue
        scored.append((proximity, (r, c)))

    scored.sort(key=lambda item: -item[0])

    moves = []
    for _, (r, c) in scored:
        if not is_legal(board, r, c, state.current)[0]:
            continue
        moves.append((r, c))
        if len(moves) >= size:
            break
    return moves


def ranked_moves(state, windows, limit=BRANCHING):
    """The best `limit` moves, strongest first, with their static value.

    Each candidate is played and taken back -- which is cheap thanks to the
    incremental evaluator -- so the returned score is the real value of the
    resulting position, and immediate wins are detected on the way.

    Returns a list of ``(score, wins, (row, col))`` sorted by decreasing
    score, from the point of view of the player to move.
    """
    color = state.current
    evaluated = []
    for r, c in shortlist(state, windows):
        move = state.play(r, c)
        wins = state.winner == color
        loses = state.winner is not None and not wins
        score = state.evaluate(color)
        state.undo(move)
        evaluated.append((score, wins, loses, (r, c)))

    evaluated.sort(key=lambda item: (item[1], not item[2], item[0]),
                   reverse=True)
    return [(score, wins, loses, move)
            for score, wins, loses, move in evaluated[:limit]]
