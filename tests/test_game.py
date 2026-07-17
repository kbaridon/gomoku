from board import BLACK, WHITE
from game import Game, CAPTURE_WIN_THRESHOLD


def test_new_game_black_to_play():
    g = Game()
    assert g.current == BLACK
    assert g.winner is None
    assert g.captures == {BLACK: 0, WHITE: 0}


def test_alternating_turns():
    g = Game()
    ok, _ = g.play(9, 9)
    assert ok
    assert g.current == WHITE
    ok, _ = g.play(3, 3)
    assert ok
    assert g.current == BLACK


def test_cannot_play_on_occupied():
    g = Game()
    g.play(9, 9)
    ok, _ = g.play(9, 9)
    assert not ok


def test_capture_increments_counter():
    g = Game()
    g.board.set(9, 10, WHITE)
    g.board.set(9, 11, WHITE)
    g.board.set(9, 12, BLACK)
    ok, _ = g.play(9, 9)
    assert ok
    assert g.captures[BLACK] == 2
    assert g.board.get(9, 10) == 0
    assert g.board.get(9, 11) == 0


def test_win_by_capture():
    g = Game()
    g.captures[BLACK] = CAPTURE_WIN_THRESHOLD - 2
    g.board.set(9, 10, WHITE)
    g.board.set(9, 11, WHITE)
    g.board.set(9, 12, BLACK)
    ok, _ = g.play(9, 9)
    assert ok
    assert g.winner == BLACK
    assert g.win_reason == "capture"


def test_alignment_creates_pending_win():
    g = Game()
    for c in range(5, 9):
        g.board.set(9, c, BLACK)
    ok, _ = g.play(9, 9)
    assert ok
    assert g.winner is None
    assert g.pending_alignment_owner == BLACK
    assert g.current == WHITE


def test_pending_alignment_resolves_on_next_turn():
    g = Game()
    for c in range(5, 9):
        g.board.set(9, c, BLACK)
    g.play(9, 9)
    g.play(0, 0)
    assert g.winner == BLACK
    assert g.win_reason == "alignment"


def test_move_time_is_recorded():
    g = Game()
    g.play(9, 9)
    assert len(g.move_times[BLACK]) == 1
    assert g.move_times[BLACK][0] >= 0


def test_no_move_after_game_over():
    g = Game()
    g.captures[BLACK] = CAPTURE_WIN_THRESHOLD
    g._declare_winner(BLACK, "capture")
    ok, msg = g.play(0, 0)
    assert not ok
    assert "over" in msg.lower()
