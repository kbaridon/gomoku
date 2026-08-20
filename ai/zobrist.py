"""Zobrist hashing: one 64-bit key per position, updated incrementally.

A transposition table needs to recognise a position it has already searched.
Re-hashing the whole goban would cost more than the lookup saves, so every
component of the position owns a table of random keys and the position key is
their exclusive-or. Flipping one component -- a stone appearing, a capture
counter moving on, the turn changing hands -- is then a single xor, and xor is
its own inverse, so taking a move back costs exactly as much as playing it.

The seed is fixed: two runs on the same position search the same tree, which
matters when comparing timings.
"""

from random import Random

from board import BLACK, BOARD_SIZE, WHITE

_rng = Random(20260219)


def _grid():
    return [[_rng.getrandbits(64) for _ in range(BOARD_SIZE)]
            for _ in range(BOARD_SIZE)]


# One key per (colour, cell). An empty cell needs none: it is the absence of
# both colours, and xoring a key out is what empties it.
CELL_KEYS = {BLACK: _grid(), WHITE: _grid()}

# Whose turn it is is part of the position: the same stones with the other
# player to move is a different node.
SIDE_KEYS = {BLACK: _rng.getrandbits(64), WHITE: _rng.getrandbits(64)}

# Captured stones, counted well past the ten that end the game so that a move
# taking several pairs at once can never run off the end of the table.
MAX_CAPTURES = 32
CAPTURE_KEYS = {
    color: [_rng.getrandbits(64) for _ in range(MAX_CAPTURES + 1)]
    for color in (BLACK, WHITE)
}

# A five waiting to be broken is part of the position too: the same stones
# with and without that debt are not the same node.
PENDING_KEYS = _grid()


def pending_key(alignments):
    """Key of the alignments the opponent still owes an answer to."""
    if not alignments:
        return 0
    key = 0
    for alignment in alignments:
        for r, c in alignment:
            key ^= PENDING_KEYS[r][c]
    return key
