"""Game state: turn order, timers, capture counts, win detection."""

import time

from board import BLACK, WHITE, EMPTY, STONE_NAME, Board, opponent
from rules import is_legal


class Game:
    """Drives a single hotseat game between two players.

    Win conditions handled:
    - A player captures 10 opponent stones -> immediate win by capture.
    - A player aligns 5+ stones -> "pending" win that only resolves after
      the opponent's next move. If the opponent can break every alignment
      with a capture (or win by capture themselves), the pending win is
      cancelled; otherwise the aligning player wins.
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

    def _switch(self):
        self.current = opponent(self.current)
        self._turn_started = time.perf_counter()

    def elapsed_current_turn(self):
        return time.perf_counter() - self._turn_started

    def is_over(self):
        return self.winner is not None

    def play(self, r, c):
        """Attempt a move; return (success, message)."""
        if self.is_over():
            return False, "Game already over"

        mover = self.current
        legal, reason = is_legal(self.board, r, c, mover)
        if not legal:
            return False, reason

        # Record the time spent thinking BEFORE mutating state so that a
        # failed move (rejected above) never gets timed.
        duration = time.perf_counter() - self._turn_started
        self.move_times[mover].append(duration)

        self.board.set(r, c, mover)
        captured = self.board.find_captures(r, c, mover)
        for pr, pc in captured:
            self.board.set(pr, pc, EMPTY)
        self.captures[mover] += len(captured)
        self.last_move = (r, c)
        self.last_captured = list(captured)

        # Immediate win by capture takes precedence over anything else,
        # including any pending 5-alignment by the opponent.
        if self.captures[mover] >= 10:
            self.winner = mover
            self.win_reason = "capture"
            return True, ""

        # If the opponent had a pending alignment, this move was their
        # single chance to break it. Anything still intact wins for them.
        if self.pending_alignment_owner == opponent(mover):
            owner = self.pending_alignment_owner
            still_intact = any(
                all(self.board.get(pr, pc) == owner for pr, pc in aln)
                for aln in self.pending_alignment
            )
            if still_intact:
                self.winner = owner
                self.win_reason = "alignment"
                return True, ""
            self.pending_alignment_owner = None
            self.pending_alignment = None

        # Does the mover themselves have a fresh 5+ alignment? Store it;
        # it will be resolved on the opponent's next move.
        my_alignments = self.board.find_all_alignments(mover)
        if my_alignments:
            self.pending_alignment_owner = mover
            self.pending_alignment = my_alignments

        self._switch()
        return True, ""

    def average_time(self, color=None):
        if color is None:
            times = self.move_times[BLACK] + self.move_times[WHITE]
        else:
            times = self.move_times[color]
        if not times:
            return 0.0
        return sum(times) / len(times)

    def last_move_time(self, color):
        if not self.move_times[color]:
            return None
        return self.move_times[color][-1]

    def move_count(self, color=None):
        if color is None:
            return len(self.move_times[BLACK]) + len(self.move_times[WHITE])
        return len(self.move_times[color])

    def is_pending_defense(self):
        """True if the current player is under a pending-alignment threat."""
        return self.pending_alignment_owner == opponent(self.current)

    def winner_name(self):
        return STONE_NAME.get(self.winner)
