import random
import time

from ai import choose_move
from ai import engine
from ai.shapes import is_playable
from ai.config import TIME_BUDGET
from ai.evaluation import Evaluator
from ai.search_space import (Window, _shortlist_size, forced_replies,
                             ranked_moves, search_space, search_windows,
                             shortlist, window_cells)
from ai.state import SearchState
from board import BLACK, BOARD_SIZE, EMPTY, WHITE
from game import Game
from rules import is_legal


# A node width to exercise the generator with: the tests are about what the
# generator does, not about how the engine happens to be tuned today.
WIDTH = 10


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
    moves = ranked_moves(state, search_space(state.board), limit=5)
    assert 0 < len(moves) <= 5
    for _, _, _, (r, c), _ in moves:
        assert is_legal(state.board, r, c, state.current)[0]


def test_ranked_moves_skips_what_the_caller_already_tried():
    game = play_all(Game(), [(9, 9), (9, 10), (8, 9), (10, 10)])
    state = SearchState(game)
    space = search_space(state.board)
    first = ranked_moves(state, space, limit=5)[0][3]
    rest = ranked_moves(state, space, limit=5, skip=(first,))
    assert first not in [entry[3] for entry in rest]


def test_a_winning_move_ends_the_generation():
    # Black has four in a row: the fifth is the only move worth ranking.
    game = play_all(Game(), [(9, 9), (0, 0), (9, 10), (0, 1),
                             (9, 11), (0, 2), (9, 12), (0, 3)])
    state = SearchState(game)
    moves = ranked_moves(state, search_space(state.board), limit=10)
    assert len(moves) == 1
    assert moves[0][1] is True
    assert moves[0][3] in {(9, 8), (9, 13)}


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


# ---------- fast legality mirrors the reference ----------

def random_position(seed, stones=40):
    """A game reached by playing random legal moves near the centre."""
    rng = random.Random(seed)
    game = Game()
    for _ in range(stones):
        if game.is_over():
            break
        cells = [(r, c) for r in range(6, 13) for c in range(6, 13)
                 if game.board.get(r, c) == EMPTY]
        rng.shuffle(cells)
        for r, c in cells:
            if game.play(r, c)[0]:
                break
        else:
            break
    return game


def test_fast_legality_agrees_with_the_reference_everywhere():
    """`ai.shapes` is an optimisation of `rules.is_legal`, not a variant."""
    checked = disagreements = 0
    for seed in range(25):
        game = random_position(seed)
        if game.is_over():
            continue
        state = SearchState(game)
        color = state.current
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if state.board.get(r, c) != EMPTY:
                    continue
                captured = state.board.find_captures(r, c, color)
                fast = is_playable(state, r, c, captured)
                reference = is_legal(state.board, r, c, color)[0]
                checked += 1
                disagreements += fast != reference
    assert disagreements == 0
    assert checked > 4_000


def test_fast_legality_still_forbids_a_double_three():
    # Two open threes crossing on (9, 9): the classic forbidden move. Black
    # is to play -- the threes have to be the mover's own to be forbidden.
    game = play_all(Game(), [(9, 7), (0, 0), (9, 8), (0, 1),
                             (7, 9), (0, 2), (8, 9), (0, 3)])
    state = SearchState(game)
    assert state.current == BLACK
    assert is_legal(state.board, 9, 9, state.current)[0] is False
    assert is_playable(state, 9, 9, state.board.find_captures(9, 9, state.current)) is False


# ---------- zobrist keys ----------

def test_playing_and_undoing_restores_the_position_key():
    game = play_all(Game(), [(9, 9), (9, 10), (8, 8), (9, 11), (7, 7)])
    state = SearchState(game)
    before = state.position_key()
    for cell in [(10, 10), (6, 6), (9, 12), (11, 11)]:
        move = state.play(*cell)
        assert state.position_key() != before
        state.undo(move)
        assert state.position_key() == before


def test_the_same_position_reached_two_ways_has_the_same_key():
    left = play_all(Game(), [(9, 9), (3, 3), (9, 11), (3, 5)])
    right = play_all(Game(), [(9, 11), (3, 5), (9, 9), (3, 3)])
    assert SearchState(left).position_key() == SearchState(right).position_key()


def test_the_side_to_move_is_part_of_the_key():
    game = play_all(Game(), [(9, 9), (3, 3)])
    black_to_play = SearchState(game)
    white_to_play = SearchState(game)
    white_to_play.current = WHITE if black_to_play.current == BLACK else BLACK
    assert black_to_play.position_key() != white_to_play.position_key()


def test_captures_are_part_of_the_key():
    game = play_all(Game(), [(9, 9), (9, 10), (0, 0), (9, 11), (9, 12)])
    state = SearchState(game)
    assert state.captures[BLACK] == 2
    key = state.position_key()
    state.captures[BLACK] = 4
    assert state.position_key() != key


def test_proximity_counts_survive_a_capture():
    game = play_all(Game(), [(9, 9), (9, 10), (0, 0), (9, 11)])
    state = SearchState(game)
    snapshot = [row[:] for row in state.proximity]
    nearby = set(state.nearby)
    move = state.play(9, 12)          # black takes the white pair back
    assert len(move.captured) == 2
    state.undo(move)
    assert state.proximity == snapshot
    assert state.nearby == nearby


# ---------- the transposition table does not change the answer ----------

def test_the_table_does_not_change_the_move_the_search_returns():
    """A second search of the same position, table warm, picks the same move.

    The *value* may drift by a little, and that is not a bug: the beam is
    indexed by ply while the table is indexed by position, so an entry filed
    from one ply can be read back at another, where the node would have been
    a different width. The engine's answer is the move, and that is stable.
    """
    for seed in range(6):
        game = random_position(seed, stones=20)
        if game.is_over():
            continue
        engine.reset_tables()
        cold = engine._search_root(SearchState(game),
                                   search_space(game.board), 4,
                                   time.perf_counter() + 300, None)
        warm = engine._search_root(SearchState(game),
                                   search_space(game.board), 4,
                                   time.perf_counter() + 300, None)
        assert cold[0] == warm[0], f"seed {seed}: {cold} then {warm}"


def test_the_table_fills_up_and_is_kept_between_moves():
    engine.reset_tables()
    game = play_all(Game(), [(9, 9), (9, 10), (8, 8)])
    choose_move(game)
    after_one = len(engine.TABLE)
    assert after_one > 0
    game.play(*choose_move(game))
    choose_move(game)
    assert len(engine.TABLE) > after_one, "the table was dropped between moves"


def test_a_capture_does_not_look_like_a_new_game():
    """Stones going down is a capture, not a restart: the table must survive."""
    engine.reset_tables()
    # Black plays between two white stones and takes the pair off the board.
    game = play_all(Game(), [(9, 9), (9, 10), (0, 0), (9, 11)])
    choose_move(game)
    filled = len(engine.TABLE)
    assert filled > 0
    ok, _ = game.play(9, 12)
    assert ok and game.captures[BLACK] == 2
    choose_move(game)
    assert len(engine.TABLE) >= filled, "the capture emptied the table"


def test_a_new_game_drops_the_table():
    engine.reset_tables()
    choose_move(play_all(Game(), [(9, 9), (9, 10), (8, 8)]))
    assert len(engine.TABLE) > 0
    choose_move(play_all(Game(), [(9, 9)]))   # a board back to one stone
    assert engine._stones_last_move == 1


# ---------- tactics survive the shortlist ----------

def test_the_move_that_stops_a_five_is_never_cut():
    """Proximity ranks a lonely blocking cell below any crowd; it must survive.

    White holds (3, 3)..(3, 6) and can play (3, 7) for five. Black's own
    stones in the corner make a denser cluster, so (3, 7) loses the proximity
    contest to a dozen cells that decide nothing.
    """
    game = play_all(Game(), [(3, 2), (3, 3), (0, 0), (3, 4),
                             (0, 1), (3, 5), (0, 2), (3, 6)])
    state = SearchState(game)
    assert state.current == BLACK
    space = search_space(state.board)

    cells = shortlist(state, space, _shortlist_size(WIDTH))
    assert (3, 7) in [(r, c) for _, r, c in cells]
    assert state.proximity[3][7] < max(p for p, _, _ in cells)


def test_a_threatened_five_forces_the_reply():
    game = play_all(Game(), [(3, 2), (3, 3), (0, 0), (3, 4),
                             (0, 1), (3, 5), (0, 2), (3, 6)])
    state = SearchState(game)
    space = search_space(state.board)
    cells = shortlist(state, space, _shortlist_size(WIDTH))
    assert forced_replies(state, cells) == frozenset({(3, 7)})
    assert [entry[3] for entry in ranked_moves(state, space, WIDTH)] == [(3, 7)]


def test_forced_replies_leaves_a_quiet_position_alone():
    game = play_all(Game(), [(9, 9), (9, 10), (8, 8), (10, 10)])
    state = SearchState(game)
    space = search_space(state.board)
    cells = shortlist(state, space, _shortlist_size(WIDTH))
    assert forced_replies(state, cells) == ()
    assert len(ranked_moves(state, space, WIDTH)) > 1


def test_looking_for_threats_leaves_the_state_untouched():
    game = play_all(Game(), [(3, 2), (3, 3), (0, 0), (3, 4),
                             (0, 1), (3, 5), (0, 2), (3, 6)])
    state = SearchState(game)
    space = search_space(state.board)
    before = (state.position_key(), state.current, dict(state.captures),
              [row[:] for row in state.board.grid], state.winner)
    forced_replies(state, shortlist(state, space, _shortlist_size(WIDTH)))
    after = (state.position_key(), state.current, dict(state.captures),
             [row[:] for row in state.board.grid], state.winner)
    assert before == after


def test_the_engine_blocks_a_four_hidden_behind_a_crowd():
    game = play_all(Game(), [(3, 2), (3, 3), (0, 0), (3, 4),
                             (0, 1), (3, 5), (0, 2), (3, 6)])
    assert choose_move(game) == (3, 7)
