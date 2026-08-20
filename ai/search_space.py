"""Where the engine is allowed to look, and in which order.

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

That geometry only depends on the stones already on the board, so it is built
once per move and handed down the tree as a `SearchSpace`, whose flattened
cell set is what every node actually intersects against.

The candidate moves are the empty cells of that space which have a stone in
reach, ranked so that alpha-beta sees the promising ones first. Ranking is
what makes the pruning work, and it is also the single most expensive thing
the search does, so it happens in two stages: a free one first -- the
proximity counts `SearchState` already maintains -- then the real one, which
plays each surviving candidate and reads the incremental evaluation back.
"""

from board import BLACK, DIRECTIONS, EMPTY, WHITE, opponent
from game import CAPTURE_WIN_THRESHOLD, MOST_CAPTURED_IN_A_MOVE

from .config import (CLUSTER_RADIUS, CRITICAL_RUN, MAX_WASTE_RATIO,
                     SHORTLIST_MARGIN, TACTICAL_TAIL, WINDOW_MARGIN)
from .shapes import is_playable, longest_run
from .state import ALIGNMENT_LENGTH


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


class SearchSpace:
    """The windows of one move, flattened once for the whole tree.

    Every node has to answer "is this cell in bounds of the search?", and it
    answers it by intersecting the state's set of cells-with-a-stone-in-reach
    with `cells`. Both are sets, so the whole question is one C-level
    operation, and neither of them is rebuilt on the way down.
    """

    __slots__ = ("windows", "cells")

    def __init__(self, windows):
        self.windows = list(windows)
        self.cells = frozenset(window_cells(self.windows))

    def __repr__(self):
        return f"SearchSpace({self.windows!r})"


def search_space(board, **kwargs):
    """The `SearchSpace` a search from `board` is confined to."""
    return SearchSpace(search_windows(board, **kwargs))


# ---------- candidate moves ----------


def _capture_wins(state, cells):
    """Cells among `cells` where a capture would end the game there and then.

    The other way to win. `Evaluator.decisive_cells` knows where a five could
    be completed because a five is a property of a line; a capture is not, so
    it needs asking separately -- and it was missed for exactly as long as the
    five was, and in exactly the same way. The cell that completes a capture
    sits at the end of a pair with one stone beside it, which puts it near the
    bottom of a ranking that counts neighbours and below the run threshold
    that rescues four-makers. With the opponent at eight captured stones the
    engine would answer somewhere else entirely and lose on the spot.

    Only asked when somebody is close enough for one move to finish it, which
    is rare, because it costs a capture scan per cell for each side in range.
    """
    close = [color for color in (BLACK, WHITE)
             if state.captures[color] >= CAPTURE_WIN_THRESHOLD - MOST_CAPTURED_IN_A_MOVE]
    if not close:
        return frozenset()

    board = state.board
    found = set()
    for _, r, c in cells:
        for color in close:
            taken = board.find_captures(r, c, color)
            if (taken and state.captures[color] + len(taken)
                    >= CAPTURE_WIN_THRESHOLD):
                found.add((r, c))
                break
    return found


def shortlist(state, space, size):
    """The `size` most promising empty cells of `space`.

    Promise is measured by the proximity counts `SearchState` already keeps up
    to date, so the common case touches the board not at all. But proximity
    counts neighbours in every direction alike, which rewards a blob of stones
    and says nothing about a line -- and the move that completes or blocks a
    five is often a lonely cell at the end of a row, ranked below a dozen
    cells in the middle of a crowd.

    So before anything is thrown away, the cells about to be cut are checked
    for that one thing, and a cell that would make a line of `CRITICAL_RUN`
    for either colour goes to the front instead of over the edge.

    Only the cut-off tail is examined, and only `TACTICAL_TAIL` of it: a
    narrow node keeps four candidates out of fifty, and walking the other
    forty-six at every node costs more than the whole search saves.

    That window is a compromise, and it is not good enough for the one move
    that must never be missed. A cell completing a *five* was measured
    twentieth by proximity in an ordinary middlegame -- one place past the
    window -- so
    the search played on unaware that the game was already over three plies
    down, and every value along that line was wrong. Those cells come from
    `Evaluator.decisive_cells`, which knows where they are without ranking
    anything, and they are taken from wherever they sit in the tail. They
    cost nothing to ask for: nearly every position has no four on it at all.
    """
    proximity = state.proximity
    grid = state.board.grid
    scored = [
        (proximity[r][c], r, c)
        for r, c in state.nearby.intersection(space.cells)
        if grid[r][c] == EMPTY
    ]
    scored.sort(reverse=True)
    if len(scored) <= size:
        return scored

    evaluator = state.evaluator
    tail = scored[size:]
    urgent = [entry for entry in tail[:TACTICAL_TAIL]
              if longest_run(evaluator, entry[1], entry[2]) >= CRITICAL_RUN]
    decisive = evaluator.decisive_cells() | _capture_wins(state, tail)
    if decisive:
        seen = {(r, c) for _, r, c in urgent}
        urgent = [entry for entry in tail
                  if (entry[1], entry[2]) in decisive
                  and (entry[1], entry[2]) not in seen] + urgent
    if not urgent:
        del scored[size:]
        return scored
    return urgent[:size] + scored[:max(0, size - len(urgent))]


def _completes_five(grid, size, r, c, color):
    """Would `color` reach five in a row by playing (r, c)?

    A cheap board read, no stone placed and nothing evaluated: it is the gate
    that decides whether the real, expensive threat test is worth running.
    """
    for dr, dc in DIRECTIONS:
        total = 1
        for step in (1, -1):
            rr, cc = r + step * dr, c + step * dc
            while 0 <= rr < size and 0 <= cc < size and grid[rr][cc] == color:
                total += 1
                rr += step * dr
                cc += step * dc
        if total >= ALIGNMENT_LENGTH:
            return True
    return False


def forced_replies(state, cells):
    """The cells the opponent would win outright on, if there are any.

    When the opponent has a move that ends the game, the position is not a
    choice between a dozen plans any more: it is answer the threat or lose.
    Recognising that collapses the branching of exactly the deep, sharp lines
    that otherwise cost the most to search.

    "Would win outright" is meant strictly. A five the opponent can complete
    is not a win here if a capture can still break it -- the rules grant one
    turn to do so -- so each suspect is really played and the endgame really
    resolved before it counts. The cheap `_completes_five` gate means that
    only happens in the rare node where a five is one move away.
    """
    opp = opponent(state.current)
    grid = state.board.grid
    size = state.board.size
    suspects = [(r, c) for _, r, c in cells
                if _completes_five(grid, size, r, c, opp)]
    if not suspects:
        return ()

    ours = state.current
    state.current = opp
    try:
        winning = []
        for r, c in suspects:
            move = state.play(r, c)
            if state.winner == opp:
                winning.append((r, c))
            state.undo(move)
    finally:
        state.current = ours
    return frozenset(winning)


def _shortlist_size(limit):
    """How many candidates to pre-rank for a node keeping `limit` of them.

    Wide nodes get the full margin, which they were measured to need. Narrow
    ones do not: past twice the beam, every extra candidate is a full
    play/evaluate/undo whose result is thrown away.
    """
    return min(limit + SHORTLIST_MARGIN, 2 * limit)


def try_move(state, r, c):
    """Play (r, c), read the position off, take it back.

    Returns ``(score, wins, loses, captured)`` from the point of view of the
    player who moved, or None if the move is forbidden. This is the expensive
    half of move ordering; thanks to the incremental evaluator, "expensive"
    means a handful of line re-scores rather than a board scan.
    """
    color = state.current
    captured = state.board.find_captures(r, c, color)
    if not is_playable(state, r, c, captured):
        return None
    move = state.play(r, c, captured)
    wins = state.winner == color
    loses = state.winner is not None and not wins
    score = state.evaluate(color)
    state.undo(move)
    return score, wins, loses, captured


def ranked_moves(state, space, limit, skip=()):
    """The best `limit` moves, strongest first, with their static value.

    Returns a list of ``(score, wins, loses, (row, col), captured)`` sorted by
    decreasing value for the player to move. `skip` holds the cells the caller
    already searched -- the transposition table's move and the killers, which
    the engine tries before paying for any of this.

    A move that wins outright ends the generation on the spot: nothing the
    other candidates could be worth would beat it, so scoring them is waste.
    And when the opponent is the one threatening to win, everything that does
    not answer the threat is dropped -- see `forced_replies`.
    """
    cells = shortlist(state, space, _shortlist_size(limit))
    forced = forced_replies(state, cells)

    evaluated = []
    for _, r, c in cells:
        if (r, c) in skip:
            continue
        outcome = try_move(state, r, c)
        if outcome is None:
            continue
        score, wins, loses, captured = outcome
        if wins:
            return [(score, True, False, (r, c), captured)]
        evaluated.append((score, False, loses, (r, c), captured))

    if forced:
        # Take the threatened cell, or capture a stone so that the five can
        # be broken next turn. Nothing else survives the opponent's reply --
        # unless nothing at all does, and then the ranking stands as it is so
        # the search still returns the least bad line.
        answers = [entry for entry in evaluated
                   if entry[3] in forced or entry[4]]
        if answers:
            evaluated = answers

    # Losing moves last, then by decreasing static value.
    evaluated.sort(key=lambda item: (not item[2], item[0]), reverse=True)
    del evaluated[limit:]
    return evaluated
