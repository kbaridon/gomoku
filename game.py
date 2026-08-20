import time

from board import BLACK, WHITE, EMPTY, STONE_NAME, Board, opponent
from rules import alignment_is_breakable, is_legal

CAPTURE_WIN_THRESHOLD = 10

# Stones one move is assumed able to capture. A move can flank a pair in
# several directions at once, and three is already exotic; the number is only
# used to decide whether an opponent still has a chance to win by capture on
# the turn they would otherwise be given, so erring high only costs a turn
# that changes nothing.
MOST_CAPTURED_IN_A_MOVE = 6


class Game:
    """Drives a game between two players.

    Win conditions handled:
    - A player captures 10 opponent stones -> immediate win by capture.
    - A player aligns 5+ stones. The opponent is owed one turn to break it,
      but only when breaking it is actually possible: an alignment no capture
      can reach, against an opponent too far from a capture win to end the
      game on that turn, decides the game there and then. Otherwise the win
      is "pending" and resolves after the opponent has moved.
    """

    def __init__(self):
        self.board = Board()
        self.current = BLACK
        self.captures = {BLACK: 0, WHITE: 0}
        self.pending_alignment_owner = None
        self.pending_alignment = None
        self.winner = None
        self.win_reason = None
        self.move_times = {BLACK: [], WHITE: []}
        self.last_move = None
        self.last_captured = []
        self._turn_started = time.perf_counter()

    # ---------- queries ----------

    def is_over(self):
        return self.winner is not None

    def elapsed_current_turn(self):
        return time.perf_counter() - self._turn_started

    def is_pending_defense(self):
        return self.pending_alignment_owner == opponent(self.current)

    def winner_name(self):
        return STONE_NAME.get(self.winner)

    def _times(self, color=None):
        if color is None:
            return self.move_times[BLACK] + self.move_times[WHITE]
        return self.move_times[color]

    def average_time(self, color=None):
        times = self._times(color)
        if not times:
            return 0.0
        return sum(times) / len(times)

    def last_move_time(self, color):
        times = self.move_times[color]
        return times[-1] if times else None

    def move_count(self, color=None):
        return len(self._times(color))

    # ---------- move flow ----------

    def play(self, r, c):
        """Attempt a move; return (success, message)."""
        if self.is_over():
            return False, "Game already over"

        mover = self.current
        legal, reason = is_legal(self.board, r, c, mover)
        if not legal:
            return False, reason

        self._record_move_time(mover)
        self._apply_move(r, c, mover)

        if self._check_capture_win(mover):
            return True, ""
        if self._resolve_pending_alignment(mover):
            return True, ""

        if self._register_new_alignments(mover):
            return True, ""
        self._switch()
        return True, ""

    def _record_move_time(self, mover):
        duration = time.perf_counter() - self._turn_started
        self.move_times[mover].append(duration)

    def _apply_move(self, r, c, mover):
        self.board.set(r, c, mover)
        captured = self.board.find_captures(r, c, mover)
        for pr, pc in captured:
            self.board.set(pr, pc, EMPTY)
        self.captures[mover] += len(captured)
        self.last_move = (r, c)
        self.last_captured = list(captured)

    def _check_capture_win(self, mover):
        if self.captures[mover] < CAPTURE_WIN_THRESHOLD:
            return False
        self._declare_winner(mover, "capture")
        return True

    def _resolve_pending_alignment(self, mover):
        owner = self.pending_alignment_owner
        if owner != opponent(mover):
            return False
        if self._alignment_still_intact(owner):
            self._declare_winner(owner, "alignment")
            return True
        self.pending_alignment_owner = None
        self.pending_alignment = None
        return False

    def _alignment_still_intact(self, owner):
        return any(
            all(self.board.get(pr, pc) == owner for pr, pc in aln)
            for aln in self.pending_alignment
        )

    def _register_new_alignments(self, mover):
        """Record a new five, or win outright if nothing can answer it.

        Returns True when the game is over. Handing the opponent a turn they
        cannot use is a turn spent proving what is already true, so it is only
        given when they can actually break the line -- or when they are close
        enough to ten captured stones to end the game on it instead, which the
        rules resolve before the alignment.
        """
        alignments = self.board.find_all_alignments(mover)
        if not alignments:
            return False
        unbreakable = any(
            not alignment_is_breakable(self.board, alignment, mover)
            for alignment in alignments
        )
        if unbreakable and not self._opponent_may_win_by_capture(mover):
            self._declare_winner(mover, "alignment")
            return True
        self.pending_alignment_owner = mover
        self.pending_alignment = alignments
        return False

    def _opponent_may_win_by_capture(self, mover):
        """Could the opponent still reach ten captured stones in one move?"""
        return (self.captures[opponent(mover)]
                >= CAPTURE_WIN_THRESHOLD - MOST_CAPTURED_IN_A_MOVE)

    def _declare_winner(self, winner, reason):
        self.winner = winner
        self.win_reason = reason

    def _switch(self):
        self.current = opponent(self.current)
        self._turn_started = time.perf_counter()
