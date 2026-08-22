"""A cheap, undoable copy of a game, used as the search node.

`Game` is built for a real match: it keeps timers, messages and history.
The search needs none of that but needs to play and take back thousands of
moves per second, so it works on this stripped down mirror instead. The rule
set is identical -- captures, capture win, and the "align five, survive one
turn" endgame are all reproduced here.

Three things travel with the board, all maintained the same way: touched only
where a move touches them, and restored exactly on undo.

- the *evaluation*, one score per line (see `ai.evaluation`);
- the *position key*, the Zobrist hash the transposition table is indexed by;
- the *proximity counts*, how crowded each empty cell's surroundings are.

Keeping the last one here instead of recomputing it at every node is what
turns move generation from a sweep of the whole search window into a set
lookup.
"""

from board import DIRECTIONS, EMPTY, Board, opponent
from game import CAPTURE_WIN_THRESHOLD, MOST_CAPTURED_IN_A_MOVE
from rules import alignment_is_breakable

from .config import DEFENCE_WEIGHT
from .evaluation import Evaluator, capture_score
from .lines import NEIGHBOURHOOD
from .zobrist import CAPTURE_KEYS, CELL_KEYS, SIDE_KEYS, pending_key

ALIGNMENT_LENGTH = 5


class Move:
    """Everything needed to take a move back."""

    __slots__ = ("r", "c", "color", "captured", "pending_owner", "pending",
                 "pending_key", "winner")

    def __init__(self, r, c, color, captured, pending_owner, pending,
                 pending_key, winner):
        self.r = r
        self.c = c
        self.color = color
        self.captured = captured
        self.pending_owner = pending_owner
        self.pending = pending
        self.pending_key = pending_key
        self.winner = winner


class SearchState:
    """Board + capture counters + endgame state, with play/undo."""

    def __init__(self, game):
        self.board = Board(game.board.size)
        self.board.grid = [row[:] for row in game.board.grid]
        self.captures = dict(game.captures)
        self.current = game.current
        self.pending_owner = game.pending_alignment_owner
        self.pending = game.pending_alignment
        self.pending_key = pending_key(self.pending)
        self.winner = game.winner
        self.evaluator = Evaluator(self.board)

        size = self.board.size
        self.proximity = [[0] * size for _ in range(size)]
        # Every cell with at least one stone in reach. The candidate generator
        # starts from this set rather than sweeping the search windows.
        self.nearby = set()
        self.board_key = 0
        for r in range(size):
            for c in range(size):
                color = self.board.grid[r][c]
                if color != EMPTY:
                    self.board_key ^= CELL_KEYS[color][r][c]
                    self._radiate(r, c, 1)

    # ---------- position key ----------

    def position_key(self):
        """Zobrist key of the whole position, side to move included."""
        captures = self.captures
        return (self.board_key
                ^ SIDE_KEYS[self.current]
                ^ CAPTURE_KEYS[1][captures[1]]
                ^ CAPTURE_KEYS[2][captures[2]]
                ^ self.pending_key)

    # ---------- board mutation ----------

    def _radiate(self, r, c, sign):
        """Add, or take back, the influence a stone at (r, c) has around it."""
        proximity, nearby = self.proximity, self.nearby
        for rr, cc, weight in NEIGHBOURHOOD[(r, c)]:
            row = proximity[rr]
            before = row[cc]
            after = before + sign * weight
            row[cc] = after
            if before == 0:
                nearby.add((rr, cc))
            elif after == 0:
                nearby.discard((rr, cc))

    def _set(self, r, c, value):
        """Mirror a board change into every structure that tracks it."""
        previous = self.board.grid[r][c]
        if previous == value:
            return
        if previous != EMPTY:
            self.board_key ^= CELL_KEYS[previous][r][c]
            self._radiate(r, c, -1)
        self.board.grid[r][c] = value
        if value != EMPTY:
            self.board_key ^= CELL_KEYS[value][r][c]
            self._radiate(r, c, 1)
        self.evaluator.set_cell(r, c, value)

    # ---------- move flow ----------

    def play(self, r, c, captured=None):
        """Play `self.current` at (r, c); return the record needed to undo.

        `captured` may be handed in when the caller already worked it out --
        the candidate generator does, to decide whether the move is legal --
        which saves scanning the eight directions a second time.
        """
        color = self.current
        move = Move(r, c, color, (), self.pending_owner, self.pending,
                    self.pending_key, self.winner)

        self._set(r, c, color)
        if captured is None:
            captured = self.board.find_captures(r, c, color)
        move.captured = captured
        for pr, pc in captured:
            self._set(pr, pc, EMPTY)
        self.captures[color] += len(captured)

        self._resolve_endgame(r, c, color)
        self.current = opponent(color)
        return move

    def undo(self, move):
        self.captures[move.color] -= len(move.captured)
        opp = opponent(move.color)
        for pr, pc in move.captured:
            self._set(pr, pc, opp)
        self._set(move.r, move.c, EMPTY)

        self.current = move.color
        self.pending_owner = move.pending_owner
        self.pending = move.pending
        self.pending_key = move.pending_key
        self.winner = move.winner

    def _resolve_endgame(self, r, c, color):
        """Apply the win conditions in the same order as `Game.play`."""
        if self.captures[color] >= CAPTURE_WIN_THRESHOLD:
            self.winner = color
            return

        # The opponent aligned five last turn: this move had to break it.
        if self.pending_owner == opponent(color):
            if self._pending_still_intact():
                self.winner = self.pending_owner
                return
            self.pending_owner = None
            self.pending = None
            self.pending_key = 0

        alignments = self._alignments_through(r, c, color)
        if not alignments:
            return
        unbreakable = any(
            not alignment_is_breakable(self.board, alignment, color)
            for alignment in alignments
        )
        if unbreakable and not self._opponent_is_close_to_capture_win(color):
            # No capture can save the opponent: it is already over.
            self.winner = color
            return
        # The opponent gets one turn to break the line -- or to win outright
        # by capture, which `Game` resolves first.
        self.pending_owner = color
        self.pending = alignments
        self.pending_key = pending_key(alignments)

    def _opponent_is_close_to_capture_win(self, color):
        """True if the opponent could still win by capture on their turn.

        Winning by capture is checked before the alignment is resolved, so an
        unbreakable five is not a win yet when the opponent is within one
        move of ten captured stones. Same rule, same constant, as `Game`.
        """
        return (self.captures[opponent(color)]
                >= CAPTURE_WIN_THRESHOLD - MOST_CAPTURED_IN_A_MOVE)

    def _pending_still_intact(self):
        owner = self.pending_owner
        return any(
            all(self.board.get(pr, pc) == owner for pr, pc in aln)
            for aln in self.pending
        )

    # ---------- alignments ----------

    def _alignments_through(self, r, c, color):
        """Five-in-a-row windows through the stone at (r, c).

        Only that stone can have created one, so the whole board never needs
        to be scanned. A run longer than five yields one window per five
        consecutive stones it contains -- see `Board.find_all_alignments` for
        why a run can't be treated as a single block.
        """
        grid = self.board.grid
        size = self.board.size
        alignments = []
        for dr, dc in DIRECTIONS:
            # Measure first. Almost every move is part of no alignment at all,
            # and counting how far the run reaches costs nothing to allocate.
            back = forward = 0
            rr, cc = r + dr, c + dc
            while 0 <= rr < size and 0 <= cc < size and grid[rr][cc] == color:
                forward += 1
                rr, cc = rr + dr, cc + dc
            rr, cc = r - dr, c - dc
            while 0 <= rr < size and 0 <= cc < size and grid[rr][cc] == color:
                back += 1
                rr, cc = rr - dr, cc - dc
            length = back + forward + 1
            if length < ALIGNMENT_LENGTH:
                continue
            for start in range(length - 4):
                step0 = start - back
                alignments.append(frozenset(
                    (r + (step0 + i) * dr, c + (step0 + i) * dc)
                    for i in range(5)
                ))
        return alignments


    # ---------- evaluation ----------

    def evaluate(self, color):
        """Static score of the position from `color`'s point of view.

        The opponent's half is weighted up: see `DEFENCE_WEIGHT`.
        """
        opp = opponent(color)
        own = (self.evaluator.pattern_score(color)
               + capture_score(self.captures[color]))
        theirs = (self.evaluator.pattern_score(opp)
                  + capture_score(self.captures[opp]))
        return own - int(theirs * DEFENCE_WEIGHT)
