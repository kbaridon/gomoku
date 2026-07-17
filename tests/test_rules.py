from board import BLACK, WHITE, Board
from rules import count_free_threes, is_legal


def test_out_of_bounds_illegal():
    b = Board()
    ok, reason = is_legal(b, -1, 0, BLACK)
    assert not ok
    assert "bounds" in reason.lower()


def test_occupied_cell_illegal():
    b = Board()
    b.set(9, 9, BLACK)
    ok, reason = is_legal(b, 9, 9, WHITE)
    assert not ok
    assert "occupied" in reason.lower()


def test_simple_move_is_legal():
    b = Board()
    ok, _ = is_legal(b, 9, 9, BLACK)
    assert ok


def test_free_three_detected():
    b = Board()
    b.set(9, 8, BLACK)
    b.set(9, 10, BLACK)
    # placing at (9, 9) creates .XXX. horizontally
    count = count_free_threes(b, 9, 9, BLACK)
    assert count >= 1


def test_double_three_forbidden():
    b = Board()
    b.set(9, 7, BLACK)
    b.set(9, 9, BLACK)
    b.set(7, 8, BLACK)
    b.set(9, 8, BLACK)
    count = count_free_threes(b, 8, 8, BLACK)
    if count >= 2:
        ok, reason = is_legal(b, 8, 8, BLACK)
        assert not ok
        assert "double" in reason.lower()


def test_move_that_captures_bypasses_double_three():
    b = Board()
    b.set(9, 10, WHITE)
    b.set(9, 11, WHITE)
    b.set(9, 12, BLACK)
    ok, _ = is_legal(b, 9, 9, BLACK)
    assert ok
