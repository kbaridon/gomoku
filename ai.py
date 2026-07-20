import time
from copy import deepcopy

from board import BOARD_SIZE, DIRECTIONS, EMPTY, opponent
from rules import is_legal


MAX_DEPTH = 10
TIME_BUDGET = 0.38
CANDIDATE_RADIUS = 2
CAPTURE_WIN = 10

WIN_SCORE = 10 ** 8
INF = 10 ** 12


class _Timeout(Exception):
    """Raised inside negamax when the deadline is reached."""


def choose_move(game):
    board = deepcopy(game.board)
    captures = dict(game.captures)
    color = game.current
    opp = opponent(color)

    if _is_empty(board):
        return (BOARD_SIZE // 2, BOARD_SIZE // 2)

    ordered = _ordered_candidates(board, color)
    legal_top = [(r, c) for (r, c) in ordered if is_legal(board, r, c, color)[0]]
    if not legal_top:
        return None

    if game.pending_alignment_owner == opp and game.pending_alignment:
        alignment_cells = set()
        for aln in game.pending_alignment:
            alignment_cells.update(aln)
        saving = [
            (r, c) for (r, c) in legal_top
            if _is_saving_move(board, r, c, color, captures, alignment_cells)
        ]
        if saving:
            legal_top = saving

    deadline = time.perf_counter() + TIME_BUDGET
    best_move = legal_top[0]

    for depth in range(1, MAX_DEPTH + 1):
        try:
            _, move = _negamax(
                board, color, depth, -INF, INF, captures, deadline,
                top_moves=legal_top,
            )
        except _Timeout:
            break
        if move is not None:
            best_move = move
    print(depth)
    return best_move


def _is_empty(board):
    for r in range(board.size):
        for c in range(board.size):
            if board.get(r, c) != EMPTY:
                return False
    return True


def _is_saving_move(board, r, c, color, captures, alignment_cells):
    captured = board.find_captures(r, c, color)
    if any(pos in alignment_cells for pos in captured):
        return True
    return captures[color] + len(captured) >= CAPTURE_WIN



def _negamax(board, color, depth, alpha, beta, captures, deadline, top_moves=None):
    if time.perf_counter() > deadline:
        raise _Timeout()

    if captures[color] >= CAPTURE_WIN:
        return WIN_SCORE, None
    opp = opponent(color)
    if captures[opp] >= CAPTURE_WIN:
        return -WIN_SCORE, None
    if depth == 0:
        return _evaluate(board, color, captures), None

    if top_moves is not None:
        moves = top_moves
        skip_legality = True
    else:
        moves = _ordered_candidates(board, color)
        skip_legality = False

    best_score = -INF
    best_move = None
    found_legal = False

    for (r, c) in moves:
        if time.perf_counter() > deadline:
            raise _Timeout()
        if not skip_legality and not is_legal(board, r, c, color)[0]:
            continue
        found_legal = True

        captured = _make(board, r, c, color, captures)
        try:
            score, _ = _negamax(
                board, opp, depth - 1,
                -beta, -alpha, captures, deadline,
            )
            score = -score
        finally:
            _unmake(board, r, c, color, captured, captures)

        if score > best_score:
            best_score = score
            best_move = (r, c)
        if best_score > alpha:
            alpha = best_score
        if alpha >= beta:
            break

    if not found_legal:
        return _evaluate(board, color, captures), None
    return best_score, best_move



def _make(board, r, c, color, captures):
    board.set(r, c, color)
    captured = board.find_captures(r, c, color)
    for pr, pc in captured:
        board.set(pr, pc, EMPTY)
    captures[color] += len(captured)
    return captured


def _unmake(board, r, c, color, captured, captures):
    board.set(r, c, EMPTY)
    opp = opponent(color)
    for pr, pc in captured:
        board.set(pr, pc, opp)
    captures[color] -= len(captured)



def _candidates(board):
    n = board.size
    result = set()
    has_stone = False
    for r in range(n):
        for c in range(n):
            if board.get(r, c) == EMPTY:
                continue
            has_stone = True
            for dr in range(-CANDIDATE_RADIUS, CANDIDATE_RADIUS + 1):
                for dc in range(-CANDIDATE_RADIUS, CANDIDATE_RADIUS + 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < n and 0 <= cc < n and board.get(rr, cc) == EMPTY:
                        result.add((rr, cc))
    if not has_stone:
        return [(BOARD_SIZE // 2, BOARD_SIZE // 2)]
    return list(result)


def _ordered_candidates(board, color):
    cands = _candidates(board)
    if len(cands) <= 1:
        return cands
    scored = [(_score_candidate(board, r, c, color), r, c) for (r, c) in cands]
    scored.sort(reverse=True)
    return [(r, c) for (_, r, c) in scored]


def _score_candidate(board, r, c, color):
    opp = opponent(color)
    score = 0
    score += (len(board.find_captures(r, c, color))
              + len(board.find_captures(r, c, opp))) * CAPTURE_SCORE

    for who in (color, opp):
        their = opponent(who)
        original = board.get(r, c)
        board.set(r, c, who)
        try:
            for dr, dc in DIRECTIONS:
                line = _line_window(board, r, c, dr, dc, who, their)
                for pat, val in PATTERNS:
                    score += line.count(pat) * val
        finally:
            board.set(r, c, original)
    return score


def _line_window(board, r, c, dr, dc, me, opp, radius=5):
    chars = []
    for i in range(-radius, radius + 1):
        rr, cc = r + i * dr, c + i * dc
        if not board.in_bounds(rr, cc):
            chars.append("#")
        else:
            v = board.get(rr, cc)
            chars.append("X" if v == me else ("O" if v == opp else "."))
    return "".join(chars)


PATTERNS = (
    ("XXXXX",   1_000_000),
    (".XXXX.",    100_000),
    ("XXXX.",      10_000),
    (".XXXX",      10_000),
    (".XXX.",       5_000),
    (".XX.X.",      2_500),
    (".X.XX.",      2_500),
    (".XX.",          200),
)

THREAT_THRESHOLD = 2_500
DOUBLE_THREAT_BONUS = 50_000

CAPTURE_SCORE = 500


def _evaluate(board, color, captures):
    """Score the position from `color`'s point of view."""
    opp = opponent(color)
    return (
        _color_score(board, color, opp)
        - _color_score(board, opp, color)
        + _capture_score(captures[color])
        - _capture_score(captures[opp])
    )


def _color_score(board, me, opp):
    score = 0
    threats = 0
    for line in _cached_lines(board.size):
        s = _line_to_str(board, line, me, opp)
        for pat, val in PATTERNS:
            hits = s.count(pat)
            if not hits:
                continue
            score += hits * val
            if val >= THREAT_THRESHOLD:
                threats += hits
    if threats >= 2:
        score += DOUBLE_THREAT_BONUS
    return score


def _capture_score(n):
    return n * CAPTURE_SCORE + n * n * 100


def _line_to_str(board, coords, me, opp):
    buf = []
    for r, c in coords:
        v = board.get(r, c)
        if v == me:
            buf.append("X")
        elif v == opp:
            buf.append("O")
        else:
            buf.append(".")
    return "".join(buf)


_LINES_CACHE = {}


def _cached_lines(n):
    lines = _LINES_CACHE.get(n)
    if lines is not None:
        return lines
    lines = []
    for r in range(n):
        lines.append([(r, c) for c in range(n)])
    for c in range(n):
        lines.append([(r, c) for r in range(n)])
    for d in range(-(n - 1), n):
        lines.append([(i, i + d) for i in range(max(0, -d), min(n, n - d))])
    for d in range(2 * n - 1):
        lines.append([(i, d - i) for i in range(max(0, d - n + 1), min(n, d + 1))])
    _LINES_CACHE[n] = lines
    return lines
