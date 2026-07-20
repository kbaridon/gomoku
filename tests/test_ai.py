import time

import pytest

import ai
from board import BLACK, WHITE, Board
from game import Game


def test_choose_move_empty_board_returns_center():
    g = Game()
    assert ai.choose_move(g) == (9, 9)


def test_choose_move_always_returns_a_legal_move():
    g = Game()
    for _ in range(6):
        move = ai.choose_move(g)
        assert move is not None
        ok, _ = g.play(*move)
        assert ok, f"AI returned an illegal move: {move}"


def test_choose_move_respects_time_budget():
    g = Game()
    for r, c in [(9, 9), (9, 10), (10, 10), (10, 9), (11, 11), (8, 8)]:
        g.play(r, c)
    t0 = time.perf_counter()
    ai.choose_move(g)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.55, f"AI took {elapsed*1000:.0f} ms (budget 500 ms)"


def test_candidates_empty_board_returns_only_center():
    b = Board()
    assert ai._candidates(b) == [(9, 9)]


def test_candidates_covers_full_neighborhood_of_a_stone():
    b = Board()
    b.set(5, 5, BLACK)
    cands = set(ai._candidates(b))
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            if dr == 0 and dc == 0:
                continue
            assert (5 + dr, 5 + dc) in cands
    assert (5, 5) not in cands
    assert (10, 10) not in cands


def test_ordered_candidates_puts_winning_move_first():
    b = Board()
    for c in (3, 4, 5, 6):
        b.set(9, c, BLACK)
    ordered = ai._ordered_candidates(b, BLACK)
    assert ordered[0] in ((9, 2), (9, 7))


def _grid_copy(board):
    return [row[:] for row in board.grid]


def test_make_unmake_no_capture_restores_state():
    b = Board()
    b.set(5, 5, BLACK)
    caps = {BLACK: 0, WHITE: 0}
    before = _grid_copy(b)
    captured = ai._make(b, 6, 5, WHITE, caps)
    assert captured == []
    ai._unmake(b, 6, 5, WHITE, captured, caps)
    assert b.grid == before
    assert caps == {BLACK: 0, WHITE: 0}


def test_make_unmake_with_capture_restores_state():
    b = Board()
    b.set(5, 4, WHITE)
    b.set(5, 5, BLACK)
    b.set(5, 6, BLACK)
    caps = {BLACK: 0, WHITE: 0}
    before = _grid_copy(b)

    captured = ai._make(b, 5, 7, WHITE, caps)

    assert set(captured) == {(5, 5), (5, 6)}
    assert caps[WHITE] == 2
    assert b.get(5, 5) == 0 and b.get(5, 6) == 0
    assert b.get(5, 7) == WHITE

    ai._unmake(b, 5, 7, WHITE, captured, caps)

    assert b.grid == before
    assert caps == {BLACK: 0, WHITE: 0}


def test_evaluate_empty_board_is_zero():
    b = Board()
    caps = {BLACK: 0, WHITE: 0}
    assert ai._evaluate(b, BLACK, caps) == 0
    assert ai._evaluate(b, WHITE, caps) == 0


def test_evaluate_is_antisymmetric():
    b = Board()
    b.set(9, 9, BLACK)
    b.set(9, 10, BLACK)
    b.set(9, 11, BLACK)
    caps = {BLACK: 1, WHITE: 0}
    assert ai._evaluate(b, BLACK, caps) == -ai._evaluate(b, WHITE, caps)


def test_evaluate_favors_own_alignment():
    b = Board()
    for c in (5, 6, 7):
        b.set(9, c, BLACK)
    caps = {BLACK: 0, WHITE: 0}
    assert ai._evaluate(b, BLACK, caps) > 0


def test_evaluate_rewards_captures():
    b = Board()
    caps = {BLACK: 4, WHITE: 0}
    assert ai._evaluate(b, BLACK, caps) > 0
    caps_close = {BLACK: 9, WHITE: 0}
    caps_low = {BLACK: 4, WHITE: 0}
    assert (
        ai._evaluate(b, BLACK, caps_close)
        > 2 * ai._evaluate(b, BLACK, caps_low)
    )


def test_evaluate_double_threat_bonus():
    b_single = Board()
    for c in (5, 6, 7):
        b_single.set(9, c, BLACK)

    b_double = Board()
    for c in (5, 6, 7):
        b_double.set(9, c, BLACK)
    for r in (5, 6, 7):
        b_double.set(r, 12, BLACK)

    caps = {BLACK: 0, WHITE: 0}
    single = ai._evaluate(b_single, BLACK, caps)
    double = ai._evaluate(b_double, BLACK, caps)
    assert double - single >= 50_000


def _play_sequence(game, moves):
    for r, c in moves:
        ok, msg = game.play(r, c)
        assert ok, f"setup move {(r, c)} rejected: {msg}"


def test_ai_completes_open_four_to_win():
    g = Game()
    _play_sequence(g, [
        (9, 3), (0, 0),
        (9, 4), (0, 1),
        (9, 5), (0, 2),
        (9, 6), (0, 3),
    ])
    assert g.current == BLACK
    assert ai.choose_move(g) in ((9, 2), (9, 7))


def test_ai_blocks_opponent_open_four():
    g = Game()
    _play_sequence(g, [
        (0, 0),   (9, 3),
        (0, 18),  (9, 4),
        (18, 0),  (9, 5),
        (18, 18), (9, 6),
    ])
    assert g.current == BLACK
    assert ai.choose_move(g) in ((9, 2), (9, 7))


def _random_legal(game, rng):
    from rules import is_legal
    b = game.board
    cells = [(r, c) for r in range(b.size) for c in range(b.size)
             if b.is_empty(r, c)]
    rng.shuffle(cells)
    for r, c in cells:
        if is_legal(b, r, c, game.current)[0]:
            return (r, c)
    return None


@pytest.mark.parametrize("ai_color", [BLACK, WHITE])
def test_ai_beats_random(ai_color):
    import random
    rng = random.Random(0 if ai_color == BLACK else 1)
    g = Game()
    for _ in range(200):
        if g.current == ai_color:
            m = ai.choose_move(g)
        else:
            m = _random_legal(g, rng)
        if m is None:
            break
        g.play(*m)
        if g.is_over():
            break
    assert g.winner == ai_color, (
        f"AI ({ai_color}) failed to beat random after {g.move_count()} moves"
    )
