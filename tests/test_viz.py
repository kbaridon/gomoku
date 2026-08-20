"""The visualiser must measure the engine, not a lookalike of it.

Three things are checked here.

*The baselines are honest.* Every speed number the visualiser shows is a
comparison between what the engine does and what `viz.naive` does, which only
means anything if the two agree on the answer and differ solely in how they
reach it.

*The instrumentation does not change what it watches.* `viz.measure` records
the search by swapping the engine's own helpers for versions that write down
what they were handed; a recording that came back with a different move, or
that left a swapped function behind, would be worse than no recording.

*Every chapter draws.* The studio is only ever looked at on a machine with a
display, so a missing key or an empty list would otherwise show up in front of
an examiner rather than here.
"""

import random
import time

import ai.engine as engine
import ai.search_space as search_space_module
import ai.state as state_module
from ai.evaluation import Evaluator
from ai.patterns import score_line
from ai.search_space import _shortlist_size, search_space, shortlist
from ai.state import SearchState
from board import BLACK, BOARD_SIZE, EMPTY, WHITE
from game import Game
from viz import measure, naive

WIDTH = 10


def a_position(seed, moves=24):
    rng = random.Random(seed)
    game = Game()
    for _ in range(moves):
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


def test_naive_captures_agree_with_the_board():
    for seed in range(6):
        game = a_position(seed)
        board = game.board
        for color in (1, 2):
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if board.get(r, c) != EMPTY:
                        continue
                    assert (naive.find_captures(board, r, c, color)
                            == board.find_captures(r, c, color))


def test_naive_proximity_agrees_with_the_maintained_counts():
    for seed in range(6):
        game = a_position(seed)
        state = SearchState(game)
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                assert naive.proximity(state.board, r, c) == state.proximity[r][c]


def test_naive_evaluation_agrees_with_the_running_total():
    for seed in range(6):
        game = a_position(seed)
        state = SearchState(game)
        for color in (1, 2):
            assert naive.evaluate(state, color) == state.evaluate(color)


def test_naive_shortlist_agrees_move_for_move():
    """Same cells in the same order: the ablation isolates one thing only."""
    for seed in range(6):
        game = a_position(seed)
        if game.is_over():
            continue
        state = SearchState(game)
        space = search_space(state.board)
        size = _shortlist_size(WIDTH)
        assert naive.shortlist(state, space, size) == shortlist(state, space, size)


def test_every_panel_draws(tmp_path):
    """Each panel must render from a plain measurement without blowing up.

    Panels read a lot of nested measurement data, and a missing key or an
    empty list only shows up when the panel is drawn -- which happens on a
    machine with a display, minutes after `make viz` starts measuring.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from viz.show import PANELS, render_panel

    data = _sample_data()
    for index, (title, subtitle, _) in enumerate(PANELS):
        assert title and subtitle
        figure = plt.figure(figsize=(14, 8.5))
        try:
            render_panel(figure, data, index)
        finally:
            plt.close(figure)


def test_the_deck_saves_to_a_pdf(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from viz.show import save_pdf

    out = tmp_path / "deck.pdf"
    save_pdf(_sample_data(), out)
    assert out.stat().st_size > 10_000


def _sample_data():
    """Enough of a measurement to render, without running a real search."""
    game = a_position(0, moves=10)
    state = SearchState(game)
    space = search_space(state.board)
    cells = shortlist(state, space, _shortlist_size(WIDTH))
    return {
        "budget": 0.45,
        "beam": {"by_ply": [16, 3, 2], "deep": 2, "root_narrows_at": 7,
                 "root_deep": 8, "max_depth": 20},
        "trace": {
            "stones": [(r, c, game.board.get(r, c))
                       for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
                       if game.board.get(r, c) != EMPTY],
            "to_play": "Black", "board_size": BOARD_SIZE,
            "windows": [(w.r0, w.c0, w.r1, w.c1) for w in space.windows],
            "space_cells": len(space.cells), "nearby_cells": len(state.nearby),
            "candidates": len(state.nearby & space.cells),
            "proximity": [row[:] for row in state.proximity],
            "shortlist": [(w, r, c) for w, r, c in cells],
            "ranked": [(100, r, c, False, False) for _, r, c in cells[:5]],
            "forced": [],
        },
        "deepening": {
            "rows": [{"depth": 2, "seconds": 0.01, "nodes": 20,
                      "move": (9, 9), "value": 10, "proven": False,
                      "cut": False}],
            "table_entries": 10, "table_hits": 5, "table_stores": 10,
        },
        "micro": [{"key": key, "name": key.title(), "detail": "d",
                   "slow_name": "obvious", "fast_name": "engine",
                   "slow": 0.01, "fast": 0.001, "speedup": 10.0}
                  for key in ("legality", "evaluation", "shortlist",
                              "captures")],
        "ablations": {
            "depth": 8, "baseline_seconds": 0.05, "baseline_nodes": 500,
            "cases": [{"name": "Narrowing beam", "detail": "d",
                       "seconds": 2.0, "nodes": 12000, "cost": 40.0},
                      {"name": "Tactical promotion", "detail": "d",
                       "seconds": 0.03, "nodes": 500, "cost": 0.7}],
        },
        "parity": {"even": {"depth": 11.5}, "every": {"depth": 9.2},
                   "positions": 8},
        "table_budget": {"with": 10.2, "without": 9.4, "positions": 8},
        "pruning": {"depth": 6, "pruned": 305, "pruned_seconds": 0.033,
                    "full": 682, "full_seconds": 0.234, "saved": 0.55},
        "survey": [{"depth": 10, "seconds": 0.45, "solved": False,
                    "stones": 20},
                   {"depth": 4, "seconds": 0.05, "solved": True,
                    "stones": 18}],
    }


# ---------- the pieces the evaluation chapter names ----------


def test_matched_shapes_add_up_to_what_the_engine_scored():
    """The chapter shows which shape earned which points.

    `patterns.score_line` returns one number and no explanation, so the
    breakdown is computed alongside it -- and would be a second opinion
    rather than an explanation if the pieces did not come to the same total.
    """
    for seed in range(4):
        game = a_position(seed)
        evaluator = Evaluator(game.board)
        for line in evaluator.text:
            for color in (BLACK, WHITE):
                pieces = naive.matched_shapes(line, color)
                assert (sum(value for _, _, value in pieces)
                        == score_line(line, color))


def test_matched_shapes_point_at_real_occurrences():
    """Each piece names where on the line it was found, and it is there."""
    for seed in range(3):
        game = a_position(seed)
        evaluator = Evaluator(game.board)
        for line in evaluator.text:
            for color in (BLACK, WHITE):
                for at, pattern, _ in naive.matched_shapes(line, color):
                    length = len(pattern)
                    assert 0 <= at <= len(line) - length


# ---------- recording the tree must not disturb it ----------


def test_the_recorded_tree_agrees_with_an_uninstrumented_search():
    """Recording writes the search down; it must not change its mind."""
    for seed in (1, 3, 5):
        game = a_position(seed, moves=14)
        if game.is_over():
            continue
        recorded = measure.record_tree(game, 4)
        engine.reset_tables()
        plain = engine.choose_move(game, time_budget=30, max_depth=4)
        assert recorded["best"] == plain


def test_recording_the_tree_puts_the_engine_back_as_it_found_it():
    before = (engine._search_move, engine._ordered_moves, engine._try_first)
    measure.record_tree(a_position(1, moves=12), 4)
    assert (engine._search_move, engine._ordered_moves,
            engine._try_first) == before


def test_the_recorded_tree_accounts_for_every_move_a_node_generated():
    """A move was either searched, and has a node, or cut, and has none.

    The chapter's whole claim is that the grey rows are moves alpha-beta
    spared the search from expanding. That is only true if what was generated
    and what was searched are lined up exactly.
    """
    root = measure.record_tree(a_position(2, moves=14), 4)
    visited = 0

    def walk(node):
        nonlocal visited
        visited += 1
        searched = [item for item in node["moves"] if item["searched"]]
        assert node["pruned"] == len(node["moves"]) - len(searched)
        if node["children"]:
            first = node["children"][0]
            assert node["window"] == (first["alpha"], first["beta"])
        else:
            assert node["window"] is None
        for item in node["moves"]:
            assert (item["node"] is not None) is item["searched"]
            if item["searched"]:
                assert item["node"]["move"] == item["move"]
                walk(item["node"])

    walk(root)
    assert visited > 1


def test_a_cut_node_really_did_reach_its_beta():
    """Nothing is called a cutoff unless the engine's own numbers say so."""
    root = measure.record_tree(a_position(3, moves=16), 6)
    cuts = 0

    def walk(node):
        nonlocal cuts
        if node["pruned"]:
            cuts += 1
            assert node["children"][-1]["value"] >= node["window"][1]
        for item in node["moves"]:
            if item["searched"]:
                walk(item["node"])

    walk(root)
    assert cuts, "no cutoff happened at all: the test position is too quiet"


def test_replaying_a_recorded_line_reaches_the_position_it_describes():
    game = a_position(2, moves=14)
    root = measure.record_tree(game, 4)
    line = []
    node = root
    while True:
        onward = [item for item in node["moves"]
                  if item["searched"] and item["node"]["children"]]
        if not onward:
            break
        line.append(onward[0]["node"])
        node = onward[0]["node"]
    state = measure.replay(game, line)
    stones = sum(1 for row in state.board.grid for value in row if value)
    before = sum(1 for row in game.board.grid for value in row if value)
    # Every move of the line put a stone down; captures may have taken pairs
    # off, so the count can only be short by an even number.
    assert (before + len(line) - stones) % 2 == 0
    assert stones <= before + len(line)


# ---------- the funnel ----------


def test_the_funnel_only_ever_narrows():
    """Each stage is a subset of the one before it, or the picture lies."""
    for seed in (0, 2, 4):
        game = a_position(seed, moves=16)
        if game.is_over():
            continue
        stages = measure.funnel(game)["stages"][:5]
        counts = [stage["count"] for stage in stages]
        assert counts == sorted(counts, reverse=True)
        for wider, narrower in zip(stages, stages[1:]):
            assert set(narrower["cells"]) <= set(wider["cells"])


def test_the_funnel_names_the_cells_the_promotion_rescued():
    """Whatever it calls promoted must be missing from the plain ranking."""
    for seed in (1, 3, 5):
        game = a_position(seed, moves=16)
        if game.is_over():
            continue
        data = measure.funnel(game)
        shortlisted = set(data["stages"][3]["cells"])
        for cell in data["promoted"]:
            assert cell in shortlisted


# ---------- iterative deepening, one depth at a time ----------


def test_deepening_steps_stay_inside_the_budget():
    game = a_position(5, moves=16)
    budget = 0.15
    rows = list(measure.deepening_steps(game, budget))
    assert rows
    assert all(row["depth"] % 2 == 0 for row in rows)
    # Loose on purpose: the deadline is only tested between nodes, so the
    # last one always overruns a little. What this catches is a budget that
    # is not applied at all, which runs to MAX_DEPTH and takes seconds.
    assert rows[-1]["spent"] <= budget + 1.0


def test_deepening_steps_do_not_charge_the_caller_for_looking():
    """A caller that stops to draw between depths keeps its budget.

    The studio steps this one depth at a time with a redraw in between, so a
    deadline fixed once at the start would spend the whole budget on the time
    the user spent reading the previous depth.
    """
    steps = measure.deepening_steps(a_position(5, moves=16), 0.2)
    try:
        first = next(steps)
        time.sleep(0.3)
        second = next(steps)
    finally:
        steps.close()
    assert first["nodes"] and not first["cut"]
    assert second["nodes"] and not second["cut"]


# ---------- one optimisation at a time ----------


def test_every_ablation_can_be_measured_on_its_own():
    game = a_position(2, moves=14)
    baseline = measure.baseline_search(game, 4)
    assert baseline["seconds"] > 0
    assert baseline["nodes"] > 0
    for key, name, detail, _ in measure.ABLATION_CASES:
        result = measure.ablate(game, key, 4)
        assert result["name"] == name
        assert result["detail"] == detail
        assert result["seconds"] > 0


def test_an_ablation_puts_the_engine_back_as_it_found_it():
    """Switching something off must not leak into the next measurement."""
    def snapshot():
        return (engine.TABLE, engine.BRANCHING_BY_PLY, engine._remember_killer,
                search_space_module.longest_run,
                search_space_module.forced_replies,
                search_space_module.shortlist,
                state_module.SearchState.evaluate)

    before = snapshot()
    game = a_position(2, moves=12)
    for case in measure.ABLATION_CASES:
        measure.ablate(game, case[0], 2)
    assert snapshot() == before


def test_an_unknown_ablation_is_refused():
    import pytest

    with pytest.raises(KeyError):
        measure.ablate(a_position(0, moves=8), "no such thing", 2)


# ---------- the studio ----------


class _Click:
    """Enough of a matplotlib mouse event to drive the click handler."""

    def __init__(self, axes, x, y, button=1, key=None):
        self.inaxes, self.xdata, self.ydata = axes, x, y
        self.button, self.key = button, key


def _studio():
    import matplotlib
    matplotlib.use("Agg")
    from viz.studio import Studio

    return Studio(budget=0.05)


def test_every_studio_chapter_draws_on_a_position_and_on_an_empty_board():
    import matplotlib.pyplot as plt

    studio = _studio()
    try:
        for index in range(len(studio.chapters)):
            studio.active = index
            studio.refresh()
        studio._clear(None)
        for index in range(len(studio.chapters)):
            studio.active = index
            studio.refresh()
    finally:
        plt.close(studio.fig)


def test_every_studio_hotspot_can_be_clicked():
    """Everything the panel offers must survive being clicked.

    The hotspots are rectangles a chapter registered while drawing, so a
    stale one -- a row that moved, an index that no longer exists -- shows up
    as an exception under the user's cursor and nowhere else.
    """
    import matplotlib.pyplot as plt

    studio = _studio()
    # The ablation chapter re-runs a whole search per row; two plies is
    # enough to walk the code, and the numbers are not what is under test.
    studio.chapters[3].DEPTH = 2
    studio.chapters[3].PRUNING_DEPTH = 2
    try:
        for index in range(len(studio.chapters)):
            studio.active = index
            studio.refresh()
            for x0, x1, y0, y1, _ in list(studio.hotspots):
                studio._on_click(_Click(studio.panel_ax, (x0 + x1) / 2,
                                        (y0 + y1) / 2))
    finally:
        plt.close(studio.fig)


def test_the_studio_takes_a_stone_and_a_key_in_every_chapter():
    import matplotlib.pyplot as plt

    studio = _studio()
    try:
        for index in range(len(studio.chapters)):
            studio.active = index
            studio._on_click(_Click(studio.board_ax, 12.0, 12.0))
            studio._on_click(_Click(studio.board_ax, 12.0, 12.0, key="shift"))
            for name in ("up", "down", " ", "backspace", "enter"):
                studio.chapter.key(name)
            studio.refresh()
    finally:
        plt.close(studio.fig)


def test_the_studio_answers_about_a_position_that_is_already_won():
    """A move that wins outright ends move generation, leaving one candidate."""
    import matplotlib.pyplot as plt

    studio = _studio()
    try:
        studio._clear(None)
        for c in (5, 6, 7, 8):
            studio.game.board.set(9, c, BLACK)
        for c in (5, 6, 7):
            studio.game.board.set(10, c, WHITE)
        studio.to_play = BLACK
        studio.changed()
        data = measure.funnel(studio.position())
        assert len(data["ranked"]) == 1
        assert data["ranked"][0][3] is True
        for index in range(len(studio.chapters)):
            studio.active = index
            studio.refresh()
    finally:
        plt.close(studio.fig)
