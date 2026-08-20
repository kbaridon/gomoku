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


def breakable_five():
    """Black one move from five, with a capture available against it.

    On the diagonal, white (8, 4) - black (9, 5) - black (10, 6) - empty
    (11, 7): white playing (11, 7) flanks the pair and takes (9, 5) out of
    the row.
    """
    g = Game()
    for c in range(5, 9):
        g.board.set(9, c, BLACK)
    g.board.set(10, 6, BLACK)
    g.board.set(8, 4, WHITE)
    return g


def test_an_alignment_nothing_can_break_wins_at_once():
    """No turn is given when the turn could not be used.

    Five isolated stones cannot be captured out of, so handing white a move
    would only be asking it to prove what is already true.
    """
    g = Game()
    for c in range(5, 9):
        g.board.set(9, c, BLACK)
    ok, _ = g.play(9, 9)
    assert ok
    assert g.winner == BLACK
    assert g.win_reason == "alignment"
    assert g.pending_alignment_owner is None


def test_a_breakable_alignment_still_owes_the_opponent_a_turn():
    g = breakable_five()
    ok, _ = g.play(9, 9)
    assert ok
    assert g.winner is None
    assert g.pending_alignment_owner == BLACK
    assert g.current == WHITE


def test_a_breakable_alignment_wins_when_it_is_not_broken():
    g = breakable_five()
    g.play(9, 9)
    g.play(0, 0)          # white looks away
    assert g.winner == BLACK
    assert g.win_reason == "alignment"


def test_breaking_the_alignment_cancels_the_win():
    g = breakable_five()
    g.play(9, 9)
    ok, msg = g.play(11, 7)      # white captures (9, 5) and (10, 6)
    assert ok, msg
    assert g.winner is None
    assert g.pending_alignment_owner is None
    assert g.captures[WHITE] == 2


def test_a_five_waits_when_the_opponent_could_still_win_by_capture():
    """Winning by capture is resolved before the alignment, so an opponent
    within one move of ten stones keeps their turn even against a five
    nothing can break."""
    g = Game()
    for c in range(5, 9):
        g.board.set(9, c, BLACK)
    g.captures[WHITE] = 8
    g.play(9, 9)
    assert g.winner is None
    assert g.pending_alignment_owner == BLACK


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
