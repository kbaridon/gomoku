"""Positions whose right answer is known, played by the whole engine.

These are the tests that catch the failures that matter. A search can be
fast, deep and well pruned and still lose every game, because none of those
things check that the move it settles on is the right one.

They are written as *positions*, not as move sequences: the stones are placed
directly so that a case says what it is about and nothing else. Everything
else in the suite goes through `Game.play`; here the point is the shape on
the board, not how it got there.

Each case allows a set of moves rather than one, because several are often
equally correct -- either end of an open three stops it just as well.
"""

import contextlib
import io

import pytest

from ai import choose_move, reset_tables
from board import BLACK, WHITE
from game import Game
from rules import is_legal


def position(black, white, to_play=BLACK):
    game = Game()
    for r, c in black:
        game.board.set(r, c, BLACK)
    for r, c in white:
        game.board.set(r, c, WHITE)
    game.current = to_play
    return game


def best_move(game):
    reset_tables()
    with contextlib.redirect_stdout(io.StringIO()):
        return choose_move(game)


# Black to play in every case. The far-away black stones give Black something
# of its own to do, so that a case measures whether the engine prefers the
# right move rather than whether it has any other move at all.
DISTRACTION = [(3, 3), (3, 4)]

CASES = [
    pytest.param(
        [(9, 5), (9, 6), (9, 7), (9, 8)], [(15, 15), (15, 16)],
        {(9, 4), (9, 9)}, id="complete-own-four"),
    pytest.param(
        DISTRACTION, [(9, 5), (9, 6), (9, 7), (9, 8)],
        {(9, 4), (9, 9)}, id="block-open-four"),
    pytest.param(
        [(9, 4)] + DISTRACTION, [(9, 5), (9, 6), (9, 7), (9, 8)],
        {(9, 9)}, id="block-closed-four"),
    pytest.param(
        DISTRACTION, [(9, 6), (9, 7), (9, 8)],
        {(9, 5), (9, 9)}, id="block-open-three"),
    pytest.param(
        DISTRACTION, [(6, 6), (7, 7), (8, 8)],
        {(5, 5), (9, 9)}, id="block-open-three-diagonal"),
    pytest.param(
        DISTRACTION, [(6, 12), (7, 11), (8, 10)],
        {(5, 13), (9, 9)}, id="block-open-three-antidiagonal"),
    pytest.param(
        DISTRACTION, [(9, 6), (9, 7), (9, 9)],
        {(9, 5), (9, 8), (9, 10)}, id="block-broken-three"),
    pytest.param(
        [(9, 5), (9, 6), (9, 7), (9, 8)], [(5, 5), (5, 6), (5, 7), (5, 8)],
        {(9, 4), (9, 9)}, id="win-rather-than-block"),
    pytest.param(
        DISTRACTION, [(9, 6), (9, 7), (9, 8), (12, 6), (12, 7), (12, 8)],
        {(9, 5), (9, 9), (12, 5), (12, 9)}, id="block-one-of-two-threes"),
]


@pytest.mark.parametrize("black,white,acceptable", CASES)
def test_the_engine_finds_the_move(black, white, acceptable):
    move = best_move(position(black, white))
    assert move in acceptable


def test_extending_a_three_is_generated_at_all():
    """The move that turns a three into an open four must be a candidate.

    It has one neighbour, while the cells alongside the three have three
    each, so a ranking that counts neighbours puts it last and the shortlist
    cuts it. Nobody then sees the winning extension until it is a five, and
    games run to a quick alignment. This is that regression.
    """
    from ai.config import CRITICAL_RUN
    from ai.search_space import _shortlist_size, search_space, shortlist
    from ai.shapes import longest_run
    from ai.state import SearchState

    game = position(DISTRACTION, [(9, 6), (9, 7), (9, 8)], to_play=WHITE)
    state = SearchState(game)
    space = search_space(state.board)
    cells = shortlist(state, space, _shortlist_size(4))
    listed = {(r, c) for _, r, c in cells}

    for extension in ((9, 5), (9, 9)):
        assert longest_run(state.evaluator, *extension) >= CRITICAL_RUN
        assert extension in listed, f"{extension} was cut from the shortlist"
        # And it is there on merit it does not have: by proximity alone it
        # ranks below cells that decide nothing.
        alongside = state.proximity[10][7]
        assert state.proximity[extension[0]][extension[1]] < alongside


# Game length was tried here as a proxy for "the engine is still defending",
# and it does not work. Measured over four openings at a fixed depth, an
# engine with the tactical promotion switched off -- which fails five of the
# positions above -- produced games of 23, 10, 31 and 36 moves, against 41,
# 43, 25 and 13 with it on. The distributions overlap, so no threshold
# separates them and the test only ever produced false alarms. What a game
# between two engines can honestly assert is that it stays legal and ends,
# which is what is left below.


def test_two_engines_play_a_legal_game_to_the_end():
    """An integration check: every move legal, the game terminates, and the
    result is one the rules can produce."""
    reset_tables()
    game = Game()
    for r, c in [(9, 9), (9, 10), (10, 10)]:
        assert game.play(r, c)[0]

    played = 0
    with contextlib.redirect_stdout(io.StringIO()):
        while not game.is_over() and played < 80:
            move = choose_move(game, time_budget=60.0, max_depth=4)
            assert move is not None, "engine had no move in an unfinished game"
            assert is_legal(game.board, move[0], move[1], game.current)[0]
            assert game.play(*move)[0]
            played += 1

    assert game.is_over(), f"still running after {played} moves"
    assert game.win_reason in {"alignment", "capture"}


# ---------- the other way to lose ----------

def capture_threat(white_captures):
    """White to capture the black pair at (9, 6)-(9, 7) by playing (9, 8)."""
    game = position([(9, 6), (9, 7)] + DISTRACTION,
                    [(9, 5), (14, 14), (14, 15)])
    game.captures[WHITE] = white_captures
    return game


def test_the_engine_stops_a_capture_that_would_end_the_game():
    """Five in a row is not the only way to lose, and the cheap ranking
    cannot see this one either.

    The cell that completes a capture has a single stone beside it, so
    proximity ranks it near the bottom, and it makes a run of three, so the
    four-maker rescue does not reach it. With White one pair from ten the
    engine used to answer at the far end of the board and lose on the spot.
    """
    assert best_move(capture_threat(8)) == (9, 8)


def test_a_capture_that_wins_is_played():
    game = capture_threat(8)
    game.current = WHITE
    assert best_move(game) == (9, 8)


def test_a_harmless_capture_is_not_treated_as_urgent():
    """The same shape with the counter low decides nothing, and the engine
    should be free to play elsewhere -- otherwise the rescue would be
    dragging a pointless cell into every shortlist for the whole game."""
    assert best_move(capture_threat(0)) != (9, 8)
