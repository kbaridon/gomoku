"""What the search already knows about a position.

The same position is reached by many different move orders -- playing A then
B leaves the goban exactly as playing B then A does -- so a plain tree search
re-solves the same node over and over. The table remembers the answer under
its Zobrist key, and every later path that lands on it stops there.

It survives from one move of the game to the next, which is as close as a
searcher gets to "keeping the tree". The literal tree cannot be kept: the
opponent's reply moves the root and invalidates the ply numbering under it.
What is worth keeping is not its shape but its *conclusions*, and those are
keyed by position, not by path -- so whatever the opponent plays, everything
the previous search proved about the positions that are still reachable is
still there, and still used.

Each entry stores how the value relates to the window it was found in:

- ``EXACT``  the search saw every move and this is the value;
- ``LOWER``  a beta cutoff: the real value is at least this much;
- ``UPPER``  nothing beat alpha: the real value is at most this much.

An entry is only trusted when it was produced by a search at least as deep as
the one asking, and a bound is only trusted when it actually settles the
current window.
"""

EXACT, LOWER, UPPER = 0, 1, 2


class TranspositionTable:
    """Zobrist-keyed cache of searched positions."""

    __slots__ = ("_entries", "_capacity", "hits", "stores")

    def __init__(self, capacity):
        self._entries = {}
        self._capacity = capacity
        self.hits = 0
        self.stores = 0

    def __len__(self):
        return len(self._entries)

    def get(self, key):
        """The stored ``(depth, value, flag, move)``, or None."""
        entry = self._entries.get(key)
        if entry is not None:
            self.hits += 1
        return entry

    def store(self, key, depth, value, flag, move):
        """Keep this result, unless a deeper one is already filed under it."""
        entries = self._entries
        previous = entries.get(key)
        if previous is not None and previous[0] > depth:
            return
        if previous is None and len(entries) >= self._capacity:
            # Full. Starting over costs one allocation and loses history;
            # evicting entry by entry would cost more than it saves at the
            # rate this table is written to.
            entries.clear()
        entries[key] = (depth, value, flag, move)
        self.stores += 1

    def clear(self):
        self._entries.clear()
        self.hits = 0
        self.stores = 0
