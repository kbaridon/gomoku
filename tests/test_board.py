from board import BLACK, WHITE, EMPTY, Board, opponent


def test_new_board_is_empty():
    b = Board()
    assert b.size == 19
    assert all(b.get(r, c) == EMPTY for r in range(b.size) for c in range(b.size))


def test_in_bounds():
    b = Board()
    assert b.in_bounds(0, 0)
    assert b.in_bounds(18, 18)
    assert not b.in_bounds(-1, 0)
    assert not b.in_bounds(19, 0)
    assert not b.in_bounds(0, 19)


def test_set_and_get():
    b = Board()
    b.set(5, 5, BLACK)
    assert b.get(5, 5) == BLACK
    assert not b.is_empty(5, 5)
    assert b.is_empty(5, 6)


def test_opponent():
    assert opponent(BLACK) == WHITE
    assert opponent(WHITE) == BLACK


def test_find_captures_horizontal():
    b = Board()
    b.set(9, 10, WHITE)
    b.set(9, 11, WHITE)
    b.set(9, 12, BLACK)
    captured = b.find_captures(9, 9, BLACK)
    assert set(captured) == {(9, 10), (9, 11)}


def test_find_captures_no_capture_on_single():
    b = Board()
    b.set(9, 10, WHITE)
    b.set(9, 11, BLACK)
    captured = b.find_captures(9, 9, BLACK)
    assert captured == []


def test_find_captures_no_capture_on_triple():
    b = Board()
    b.set(9, 10, WHITE)
    b.set(9, 11, WHITE)
    b.set(9, 12, WHITE)
    b.set(9, 13, BLACK)
    captured = b.find_captures(9, 9, BLACK)
    assert captured == []


def test_find_captures_diagonal():
    b = Board()
    b.set(10, 10, WHITE)
    b.set(11, 11, WHITE)
    b.set(12, 12, BLACK)
    captured = b.find_captures(9, 9, BLACK)
    assert set(captured) == {(10, 10), (11, 11)}


def test_no_self_capture():
    b = Board()
    b.set(9, 9, BLACK)
    b.set(9, 11, BLACK)
    captured = b.find_captures(9, 10, WHITE)
    assert captured == []


def test_find_all_alignments_five_in_row():
    b = Board()
    for c in range(5, 10):
        b.set(9, c, BLACK)
    alns = b.board_alignments_for_black() if hasattr(b, 'board_alignments_for_black') else b.find_all_alignments(BLACK)
    assert len(alns) == 1
    assert alns[0] == frozenset((9, c) for c in range(5, 10))


def test_find_all_alignments_none_when_only_four():
    b = Board()
    for c in range(5, 9):
        b.set(9, c, BLACK)
    assert b.find_all_alignments(BLACK) == []


def test_find_all_alignments_six_in_row():
    """A run of six is two overlapping five-windows, not one six-stone block:
    a capture can take the run's edge stone without breaking the other five."""
    b = Board()
    for c in range(5, 11):
        b.set(9, c, BLACK)
    alns = b.find_all_alignments(BLACK)
    assert len(alns) == 2
    assert all(len(aln) == 5 for aln in alns)
    assert frozenset((9, c) for c in range(5, 10)) in alns
    assert frozenset((9, c) for c in range(6, 11)) in alns
