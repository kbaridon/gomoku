from board import DIRECTIONS, EMPTY

FREE_THREE_PATTERNS = (
    ".XXX.",
    ".XX.X.",
    ".X.XX.",
)


def _line_around(board, r, c, dr, dc, color, radius=5):
    """Return an 11-char string of the line centered on (r, c) along (dr, dc).

    - 'X' means the player's own color
    - 'O' means the opponent
    - '.' means empty
    - '#' means out of bounds
    The center cell is at index `radius` in the returned string.
    """
    chars = []
    for i in range(-radius, radius + 1):
        rr, cc = r + i * dr, c + i * dc
        if not board.in_bounds(rr, cc):
            chars.append("#")
            continue
        v = board.get(rr, cc)
        if v == EMPTY:
            chars.append(".")
        elif v == color:
            chars.append("X")
        else:
            chars.append("O")
    return "".join(chars)


def _direction_makes_free_three(board, r, c, dr, dc, color):
    line = _line_around(board, r, c, dr, dc, color, radius=5)
    center = 5
    for pattern in FREE_THREE_PATTERNS:
        plen = len(pattern)
        for start in range(len(line) - plen + 1):
            if line[start:start + plen] != pattern:
                continue
            offset = center - start
            if 0 <= offset < plen and pattern[offset] == "X":
                return True
    return False


def count_free_threes(board, r, c, color):
    """Number of distinct free-threes the move at (r, c) would create.

    We temporarily place the stone, count over the four axes, then revert.
    """
    original = board.get(r, c)
    board.set(r, c, color)
    try:
        count = 0
        for dr, dc in DIRECTIONS:
            if _direction_makes_free_three(board, r, c, dr, dc, color):
                count += 1
        return count
    finally:
        board.set(r, c, original)


def is_legal(board, r, c, color):
    """Return (True, "") if the move is legal, else (False, reason)."""
    if not board.in_bounds(r, c):
        return False, "Out of bounds"
    if not board.is_empty(r, c):
        return False, "Cell already occupied"
    captures = board.find_captures(r, c, color)
    if not captures and count_free_threes(board, r, c, color) >= 2:
        return False, "Forbidden double-three"
    return True, ""
