from board import ALL_DIRECTIONS, DIRECTIONS, EMPTY, opponent

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


def is_capturable(board, r, c, color):
    """Can the `color` stone at (r, c) be taken by a single opponent move?

    A capture needs the pattern opponent - stone - mate - empty along one
    direction: playing the empty cell flanks the pair. A capturing move is
    never rejected by the double-three rule, so an empty cell in range is
    enough to make it legal and no legality check is needed here.
    """
    opp = opponent(color)
    for dr, dc in ALL_DIRECTIONS:
        mate = (r + dr, c + dc)
        behind = (r - dr, c - dc)
        front = (r + 2 * dr, c + 2 * dc)
        if not (board.in_bounds(*mate) and board.in_bounds(*behind)
                and board.in_bounds(*front)):
            continue
        if board.get(*mate) != color:
            continue
        if board.get(*behind) == opp and board.get(*front) == EMPTY:
            return True
    return False


def alignment_is_breakable(board, alignment, color):
    """Can the opponent take a stone out of `alignment` in one move?

    Breaking it is the opponent's only answer to five in a row, so an
    alignment no capture reaches has already decided the game.
    """
    return any(is_capturable(board, r, c, color) for r, c in alignment)
