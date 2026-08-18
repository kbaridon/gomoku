"""Terminal trace of what the engine is doing.

The board lives in a matplotlib window, so the search has nowhere to show
its progress there. It writes to the terminal instead: one growing line per
move listing the depths as they complete, and one summary at the end of the
session with the deepest search reached.

The engine is called from the UI as plain `choose_move(game)`, with no place
to thread a reporter through, so the reporter is a module-level singleton --
tracing is a side concern, not part of the search interface.
"""

from board import STONE_NAME


class SearchReport:
    """Depths reached by the engine, for the current move and overall."""

    def __init__(self):
        self.max_depth = 0
        self.moves = 0
        self._current_depth = 0

    def start_move(self, color):
        self._current_depth = 0
        print(f"{STONE_NAME[color]:<5} searching:", end="", flush=True)

    def depth_completed(self, depth):
        """Called once a whole depth has been searched, never on a timeout."""
        self._current_depth = depth
        self.max_depth = max(self.max_depth, depth)
        print(f" {depth}", end="", flush=True)

    def finish_move(self, move, seconds):
        self.moves += 1
        depth = f"depth {self._current_depth}" if self._current_depth else "opening"
        print(f"   -> {move} in {seconds:.2f}s ({depth})", flush=True)

    def session_summary(self):
        if not self.moves:
            return
        print(f"\nEngine: {self.moves} moves searched, "
              f"deepest search reached depth {self.max_depth}.")


REPORT = SearchReport()


def print_search_summary():
    """Report the deepest search of the session; called when the game ends."""
    REPORT.session_summary()
