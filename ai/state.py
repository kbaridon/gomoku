"""A cheap, undoable copy of a game, used as the search node.

`Game` is built for a real match: it keeps timers, messages and history.
The search needs none of that but needs to play and take back thousands of
moves per second, so it works on this stripped down mirror instead. The rule
set is identical -- captures, capture win, and the "align five, survive one
turn" endgame are all reproduced here.
"""

from board import ALL_DIRECTIONS, DIRECTIONS, EMPTY, Board, opponent
from game import CAPTURE_WIN_THRESHOLD

from .evaluation import Evaluator, capture_score

ALIGNMENT_LENGTH = 5


class Move:
    """Everything needed to take a move back."""

    __slots__ = ("r", "c", "color", "captured", "pending_owner", "pending",
                 "winner")

    def __init__(self, r, c, color, captured, pending_owner, pending, winner):
        self.r = r
        self.c = c
        self.color = color
        self.captured = captured
        self.pending_owner = pending_owner
        self.pending = pending
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
        self.winner = game.winner
        self.evaluator = Evaluator(self.board)

    # ---------- board mutation ----------

    def _set(self, r, c, value):
        self.board.set(r, c, value)
        self.evaluator.set_cell(r, c, value)

    # ---------- move flow ----------

    def play(self, r, c):
        """Play `self.current` at (r, c); return the record needed to undo."""
        color = self.current
        move = Move(r, c, color, [], self.pending_owner, self.pending,
                    self.winner)

        self._set(r, c, color)
        move.captured = self.board.find_captures(r, c, color)
        for pr, pc in move.captured:
            self._set(pr, pc, EMPTY)
        self.captures[color] += len(move.captured)

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

        alignments = self._alignments_through(r, c, color)
        if not alignments:
            return
        unbreakable = any(not self._is_breakable(aln, color)
                          for aln in alignments)
        if unbreakable and not self._opponent_is_close_to_capture_win(color):
            # No capture can save the opponent: it is already over.
            self.winner = color
            return
        # The opponent gets one turn to break the line -- or to win outright
        # by capture, which `Game` resolves first.
        self.pending_owner = color
        self.pending = alignments

    def _opponent_is_close_to_capture_win(self, color):
        """True if a single capture would end the game in the opponent's favour.

        Winning by capture is checked before the alignment is resolved, so an
        unbreakable five is not a win yet when the opponent sits at eight
        captured stones.
        """
        return self.captures[opponent(color)] >= CAPTURE_WIN_THRESHOLD - 2

    def _pending_still_intact(self):
        owner = self.pending_owner
        return any(
            all(self.board.get(pr, pc) == owner for pr, pc in aln)
            for aln in self.pending
        )

    # ---------- alignments ----------

    def _alignments_through(self, r, c, color):
        """Alignments of five or more created by the stone at (r, c).

        Only that stone can have created one, so the whole board never needs
        to be scanned.
        """
        alignments = []
        for dr, dc in DIRECTIONS:
            cells = [(r, c)]
            for step in (1, -1):
                rr, cc = r + step * dr, c + step * dc
                while self.board.in_bounds(rr, cc) and self.board.get(rr, cc) == color:
                    cells.append((rr, cc))
                    rr, cc = rr + step * dr, cc + step * dc
            if len(cells) >= ALIGNMENT_LENGTH:
                alignments.append(frozenset(cells))
        return alignments

    def _is_breakable(self, alignment, color):
        """True if the opponent can capture a stone of `alignment` at once.

        A capturing move is never rejected by the double-three rule, so an
        empty cell in range is enough to make the capture legal.
        """
        return any(self._is_capturable(r, c, color) for r, c in alignment)

    def _is_capturable(self, r, c, color):
        """True if the stone at (r, c) can be taken by the next opponent move."""
        opp = opponent(color)
        board = self.board
        for dr, dc in ALL_DIRECTIONS:
            mate = (r + dr, c + dc)
            behind = (r - dr, c - dc)
            front = (r + 2 * dr, c + 2 * dc)
            if not (board.in_bounds(*mate) and board.in_bounds(*behind)
                    and board.in_bounds(*front)):
                continue
            if board.get(*mate) != color:
                continue
            # opp - (r, c) - mate - empty  =>  playing the empty cell captures.
            if board.get(*behind) == opp and board.get(*front) == EMPTY:
                return True
        return False

    # ---------- evaluation ----------

    def evaluate(self, color):
        """Static score of the position from `color`'s point of view."""
        opp = opponent(color)
        own = (self.evaluator.pattern_score(color)
               + capture_score(self.captures[color]))
        theirs = (self.evaluator.pattern_score(opp)
                  + capture_score(self.captures[opp]))
        return own - theirs
