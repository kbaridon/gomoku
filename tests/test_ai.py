import time

from ai import choose_move
from ai.config import TIME_BUDGET
from ai.evaluation import Evaluator
from ai.search_space import (Window, ranked_moves, search_windows,
                             window_cells)
from ai.state import SearchState
from board import BLACK, BOARD_SIZE, EMPTY, WHITE
from game import Game
from rules import is_legal


def play_all(game, moves):
    for r, c in moves:
        ok, msg = game.play(r, c)
        assert ok, msg
    return game


# ---------- search space ----------

def test_empty_board_window_is_the_centre():
    game = Game()
    windows = search_windows(game.board)
    centre = BOARD_SIZE // 2
    assert len(windows) == 1
    assert (centre, centre) in window_cells(windows)


def test_distant_groups_get_their_own_window():
    game = play_all(Game(), [(1, 1), (17, 17), (1, 2), (17, 16)])
    windows = search_windows(game.board)
    assert len(windows) == 2
    # Far cheaper than the single bounding box over the whole board.
    assert len(window_cells(windows)) < BOARD_SIZE * BOARD_SIZE / 4


def test_close_groups_are_merged_into_one_window():
    game = play_all(Game(), [(9, 9), (9, 11), (10, 10), (10, 12)])
    assert len(search_windows(game.board)) == 1


def test_windows_cover_every_stone():
    game = play_all(Game(), [(3, 3), (15, 15), (3, 4), (15, 14), (9, 9)])
    cells = window_cells(search_windows(game.board))
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if game.board.get(r, c) != EMPTY:
                assert (r, c) in cells


def test_windows_stay_inside_the_board():
    game = play_all(Game(), [(0, 0), (18, 18)])
    for window in search_windows(game.board):
        assert 0 <= window.r0 <= window.r1 < BOARD_SIZE
        assert 0 <= window.c0 <= window.c1 < BOARD_SIZE


def test_merging_two_far_windows_wastes_most_of_the_union():
    left = Window(0, 0, 1, 1)
    right = Window(17, 17, 18, 18)
    union = left.union(right)
    waste = union.area - (left.area + right.area)
    assert waste > 0.9 * union.area


def test_ranked_moves_are_legal_and_limited():
    game = play_all(Game(), [(9, 9), (9, 10), (8, 9), (10, 10)])
    state = SearchState(game)
    moves = ranked_moves(state, search_windows(state.board), limit=5)
    assert 0 < len(moves) <= 5
    for _, _, _, (r, c) in moves:
        assert is_legal(state.board, r, c, state.current)[0]


# ---------- state ----------

def test_play_then_undo_restores_everything():
    game = play_all(Game(), [(9, 9), (9, 10), (8, 8), (9, 11)])
    state = SearchState(game)
    before_grid = [row[:] for row in state.board.grid]
    before_score = state.evaluate(BLACK)

    move = state.play(7, 7)
    state.undo(move)

    assert state.board.grid == before_grid
    assert state.evaluate(BLACK) == before_score
    assert state.current == game.current


def test_captures_are_undone():
    # Black plays between two white stones and takes the pair back.
    game = play_all(Game(), [(9, 9), (9, 10), (0, 0), (9, 11), (9, 12)])
    state = SearchState(game)
    assert state.captures[BLACK] == 2

    move = state.play(5, 5)
    state.undo(move)
    assert state.captures[BLACK] == 2


def test_incremental_score_matches_a_fresh_evaluation():
    game = play_all(Game(), [(9, 9), (3, 3), (9, 10), (3, 4), (8, 8)])
    state = SearchState(game)
    state.play(7, 7)
    fresh = Evaluator(state.board)
    for color in (BLACK, WHITE):
        assert state.evaluator.pattern_score(color) == fresh.pattern_score(color)


def test_five_in_a_row_is_a_win():
    game = play_all(Game(), [(9, 9), (0, 0), (9, 10), (0, 1),
                             (9, 11), (0, 2), (9, 12), (0, 3)])
    state = SearchState(game)
    state.play(9, 13)
    assert state.winner == BLACK


# ---------- engine ----------

def test_first_move_is_the_centre():
    assert choose_move(Game()) == (BOARD_SIZE // 2, BOARD_SIZE // 2)


def test_engine_completes_the_win():
    game = play_all(Game(), [(9, 9), (0, 0), (9, 10), (0, 1),
                             (9, 11), (0, 2), (9, 12), (0, 3)])
    assert choose_move(game) in {(9, 8), (9, 13)}


def test_engine_blocks_an_open_four():
    game = play_all(Game(), [(0, 0), (3, 3), (0, 1), (3, 4),
                             (18, 18), (3, 5), (18, 17), (3, 6)])
    assert choose_move(game) in {(3, 2), (3, 7)}


def test_engine_returns_a_legal_move():
    game = play_all(Game(), [(9, 9), (9, 10), (8, 9), (10, 10)])
    r, c = choose_move(game)
    assert is_legal(game.board, r, c, game.current)[0]


def test_engine_respects_the_time_budget():
    game = play_all(Game(), [(9, 9), (9, 10), (8, 8), (10, 10), (7, 7)])
    start = time.perf_counter()
    choose_move(game)
    # The deadline is only tested between nodes, so allow the last one to run.
    assert time.perf_counter() - start < TIME_BUDGET + 0.4


def test_engine_returns_none_on_a_finished_game():
    game = play_all(Game(), [(9, 9), (0, 0), (9, 10), (0, 1),
                             (9, 11), (0, 2), (9, 12), (0, 3), (9, 13)])
    game.play(1, 1)  # white cannot break the line: black wins
    assert game.is_over()
    assert choose_move(game) is None
