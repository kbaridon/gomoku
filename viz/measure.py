"""Run the real engine and write down what it did.

Everything the visualiser shows is measured here, on the engine the game
actually plays with -- no reimplementation, no remembered numbers. Two kinds
of measurement:

- a *trace*: one position searched normally, recording the search space it
  was confined to, the candidates it ranked and the depths it completed;
- an *ablation*: the same search with one optimisation switched off, so the
  difference between the two is that optimisation's contribution.

Ablations switch things off from the outside, by swapping a function or a
constant on the module that uses it. The engine has no idea it is being
measured and carries no flags for it.
"""

import inspect
import random
import time
from contextlib import contextmanager

import ai.engine as engine
import ai.search_space as search_space
import ai.state as state_module
from ai.config import CLUSTER_RADIUS, CRITICAL_RUN, WINDOW_MARGIN
from ai.search_space import ranked_moves, search_space as make_space, shortlist
from ai.shapes import free_three_count
from ai.state import SearchState
from board import BOARD_SIZE, EMPTY, STONE_NAME
from game import Game
from rules import is_legal

from . import naive

# The position the trace is taken on: a middlegame with both sides committed.
TRACE_MOVES = [(9, 9), (9, 10), (10, 10), (8, 8), (10, 9), (11, 11),
               (8, 10), (10, 11), (7, 9), (12, 12)]

# Depth the ablations are compared at. Fixed, so that the comparison is
# between equal amounts of work rather than between whatever fitted in a
# time budget.
ABLATION_DEPTH = 8


def build_game(moves):
    game = Game()
    for r, c in moves:
        ok, why = game.play(r, c)
        if not ok:
            raise ValueError(f"illegal setup move {(r, c)}: {why}")
    return game


# ---------- instrumentation ----------


@contextmanager
def counting_nodes():
    """Count the interior nodes the search visits while inside the block."""
    tally = {"nodes": 0}
    original = engine._negamax

    def counted(*args, **kwargs):
        tally["nodes"] += 1
        return original(*args, **kwargs)

    engine._negamax = counted
    try:
        yield tally
    finally:
        engine._negamax = original


def _timed_search(game, depth):
    """One fixed-depth search; returns (seconds, nodes)."""
    engine.reset_tables()
    state = SearchState(game)
    space = make_space(state.board)
    with counting_nodes() as tally:
        started = time.perf_counter()
        best = None
        for step in range(2, depth + 1, 2):
            best, _ = engine._search_root(state, space, step,
                                          time.perf_counter() + 600, best)
        elapsed = time.perf_counter() - started
    return elapsed, tally["nodes"]


# ---------- the trace ----------


def trace(game):
    """What the engine looks at, and in what order, for one position."""
    state = SearchState(game)
    space = make_space(state.board)
    width = engine._branching(0)
    cells = shortlist(state, space, search_space._shortlist_size(width))
    ranked = ranked_moves(state, space, width)

    stones = [(r, c, game.board.get(r, c))
              for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
              if game.board.get(r, c) != EMPTY]

    return {
        "stones": stones,
        "to_play": STONE_NAME[state.current],
        "board_size": BOARD_SIZE,
        "windows": [(w.r0, w.c0, w.r1, w.c1) for w in space.windows],
        "space_cells": len(space.cells),
        "nearby_cells": len(state.nearby),
        "candidates": len(state.nearby & space.cells),
        "proximity": [row[:] for row in state.proximity],
        "shortlist": [(weight, r, c) for weight, r, c in cells],
        "ranked": [(score, r, c, wins, loses)
                   for score, wins, loses, (r, c), _ in ranked],
        "forced": sorted(search_space.forced_replies(state, cells)),
    }


def deepening(game, budget):
    """The iterative deepening trace: what each completed depth cost."""
    engine.reset_tables()
    state = SearchState(game)
    space = make_space(state.board)
    rows = []
    best = None
    deadline = time.perf_counter() + budget
    with counting_nodes() as tally:
        for depth in range(2, engine.MAX_DEPTH + 1, 2):
            before_nodes = tally["nodes"]
            started = time.perf_counter()
            try:
                move, value = engine._search_root(state, space, depth,
                                                  deadline, best)
            except engine.SearchTimeout:
                rows.append({"depth": depth, "seconds": None, "nodes": None,
                             "move": None, "value": None, "cut": True})
                break
            elapsed = time.perf_counter() - started
            best = move
            rows.append({
                "depth": depth,
                "seconds": elapsed,
                "nodes": tally["nodes"] - before_nodes,
                "move": move,
                "value": value,
                "proven": abs(value) >= engine.MATE_FLOOR,
                "cut": False,
            })
            if move is None or abs(value) >= engine.MATE_FLOOR:
                break
    return {
        "rows": rows,
        "table_entries": len(engine.TABLE),
        "table_hits": engine.TABLE.hits,
        "table_stores": engine.TABLE.stores,
    }


# ---------- micro-benchmarks ----------


def _repeat(fn, rounds):
    started = time.perf_counter()
    for _ in range(rounds):
        fn()
    return (time.perf_counter() - started) / rounds


def micro_benchmarks(game):
    """Per-operation costs, engine version against the obvious version."""
    st = SearchState(game)
    board = st.board
    space = make_space(st.board)
    empties = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
               if board.get(r, c) == EMPTY][:120]
    color = st.current

    results = []

    results.append({
        "key": "legality",
        "name": "Legality of one move",
        "detail": "the double-three ban, over 120 cells",
        "slow_name": "rules.is_legal (reference)",
        "fast_name": "ai.shapes, off the line text",
        "slow": _repeat(lambda: [is_legal(board, r, c, color)
                                 for r, c in empties], 20),
        "fast": _repeat(lambda: [free_three_count(st.evaluator, r, c, color)
                                 for r, c in empties], 20),
    })

    results.append({
        "key": "evaluation",
        "name": "Scoring the position",
        "detail": "one evaluation",
        "slow_name": "re-score the whole goban",
        "fast_name": "read the running total",
        "slow": _repeat(lambda: naive.evaluate(st, color), 40),
        "fast": _repeat(lambda: st.evaluate(color), 40),
    })

    results.append({
        "key": "shortlist",
        "name": "Candidate shortlist",
        "detail": "one node's worth of candidates",
        "slow_name": "count neighbours per cell",
        "fast_name": "read the maintained counts",
        "slow": _repeat(lambda: naive.shortlist(st, space, 20), 40),
        "fast": _repeat(lambda: shortlist(st, space, 20), 40),
    })

    results.append({
        "key": "captures",
        "name": "Captures of one move",
        "detail": "over 120 cells",
        "slow_name": "walk 8 directions, check bounds",
        "fast_name": "pre-resolved ray table",
        "slow": _repeat(lambda: [naive.find_captures(board, r, c, color)
                                 for r, c in empties], 20),
        "fast": _repeat(lambda: [board.find_captures(r, c, color)
                                 for r, c in empties], 20),
    })

    for row in results:
        row["speedup"] = row["slow"] / row["fast"] if row["fast"] else 0.0
    return results


# ---------- ablations ----------


@contextmanager
def _swapped(owner, name, value):
    original = getattr(owner, name)
    setattr(owner, name, value)
    try:
        yield
    finally:
        setattr(owner, name, original)


class _TableView:
    """The real table with some of what it offers withheld."""

    def __init__(self, inner, enabled=True, with_move=True):
        self.inner, self.enabled, self.with_move = inner, enabled, with_move

    def get(self, key):
        if not self.enabled:
            return None
        entry = self.inner.get(key)
        if entry is None or self.with_move:
            return entry
        return (entry[0], entry[1], entry[2], None)

    def store(self, *args):
        if self.enabled:
            self.inner.store(*args)

    def clear(self):
        self.inner.clear()

    def __len__(self):
        return len(self.inner)

    @property
    def hits(self):
        return self.inner.hits

    @property
    def stores(self):
        return self.inner.stores


def _all_depths(state, time_budget, max_depth):
    """`_best_move` stepping through every depth instead of the even ones."""
    if not state.nearby:
        centre = state.board.size // 2
        return (centre, centre)
    space = make_space(state.board)
    best = None
    deadline = time.perf_counter() + time_budget
    for depth in range(1, max_depth + 1):
        try:
            move, value = engine._search_root(state, space, depth, deadline,
                                              best)
        except engine.SearchTimeout:
            break
        if move is None:
            break
        best = move
        engine.REPORT.depth_completed(depth)
        if abs(value) >= engine.MATE_FLOOR:
            break
    return best if best is not None else engine._any_legal_move(state)


# Every optimisation the visualiser can switch off, and how. Each entry is
# (key, name, what switching it off means, a factory for the context manager
# that switches it off). The factory runs at measurement time rather than at
# import, so a case that wraps `engine.TABLE` wraps whatever table is current.
ABLATION_CASES = (
    ("table", "Transposition table", "no memory of searched positions",
     lambda: _swapped(engine, "TABLE",
                      _TableView(engine.TABLE, enabled=False))),
    ("table_move", "Table move first",
     "table used for cutoffs only, not for ordering",
     lambda: _swapped(engine, "TABLE",
                      _TableView(engine.TABLE, with_move=False))),
    ("killers", "Killer moves", "no cutoff move remembered per ply",
     lambda: _swapped(engine, "_remember_killer", lambda ply, move: None)),
    ("beam", "Narrowing beam", "every node ten moves wide instead",
     lambda: _swapped(engine, "BRANCHING_BY_PLY", (16,) + (10,) * 15)),
    ("tactical", "Tactical promotion",
     "a four- or five-making cell may be cut by proximity",
     lambda: _swapped(search_space, "longest_run",
                      lambda evaluator, r, c: 0)),
    ("forced", "Forced replies",
     "no narrowing when the opponent threatens to win",
     lambda: _swapped(search_space, "forced_replies", lambda st, cells: ())),
    ("evaluation", "Incremental evaluation",
     "the goban re-scored at every node",
     lambda: _swapped(state_module.SearchState, "evaluate", naive.evaluate)),
    ("proximity", "Incremental proximity",
     "neighbours counted at every node",
     lambda: _swapped(search_space, "shortlist", naive.shortlist)),
)


def ablations(game):
    """Each optimisation's contribution: the same search without it."""
    baseline_seconds, baseline_nodes = _timed_search(game, ABLATION_DEPTH)

    cases = []
    for key, name, detail, factory in ABLATION_CASES:
        with factory():
            seconds, nodes = _timed_search(game, ABLATION_DEPTH)
        cases.append({
            "key": key,
            "name": name,
            "detail": detail,
            "seconds": seconds,
            "nodes": nodes,
            "cost": seconds / baseline_seconds if baseline_seconds else 0.0,
        })

    cases.sort(key=lambda case: -case["cost"])
    return {
        "depth": ABLATION_DEPTH,
        "baseline_seconds": baseline_seconds,
        "baseline_nodes": baseline_nodes,
        "cases": cases,
    }


def _plain_minimax(state, space, depth, ply, tally):
    """The same tree with no pruning at all: every move of every node."""
    tally["nodes"] += 1
    moves = ranked_moves(state, space, engine._branching(ply))
    if not moves:
        return 0
    best = -float("inf")
    for score, wins, loses, move, captured in moves:
        if wins:
            value = engine.WIN_VALUE - ply
        elif loses:
            value = -engine.WIN_VALUE + ply
        elif depth <= 1:
            value = score
        else:
            played = state.play(move[0], move[1], captured)
            try:
                value = -_plain_minimax(state, space, depth - 1, ply + 1, tally)
            finally:
                state.undo(played)
        if value > best:
            best = value
    return best


def pruning_comparison(game, depth=6):
    """What alpha-beta is worth: the same tree searched with and without it.

    Both sides see exactly the same moves in the same order -- the only
    difference is that one stops looking at a branch once it cannot change
    the answer. The table is switched off for both, so the number is
    alpha-beta's alone.
    """
    real = engine.TABLE
    off = _TableView(real, enabled=False)

    with _swapped(engine, "TABLE", off):
        state = SearchState(game)
        space = make_space(state.board)
        with counting_nodes() as tally:
            started = time.perf_counter()
            engine._search_root(state, space, depth,
                                time.perf_counter() + 600, None)
            pruned_seconds = time.perf_counter() - started
        pruned = tally["nodes"]

        state = SearchState(game)
        tally = {"nodes": 0}
        started = time.perf_counter()
        for score, wins, loses, move, captured in ranked_moves(
                state, space, engine._branching(0)):
            if wins or loses or depth <= 1:
                continue
            played = state.play(move[0], move[1], captured)
            try:
                _plain_minimax(state, space, depth - 1, 1, tally)
            finally:
                state.undo(played)
        full_seconds = time.perf_counter() - started
        full = tally["nodes"]

    return {
        "depth": depth,
        "pruned": pruned, "pruned_seconds": pruned_seconds,
        "full": full, "full_seconds": full_seconds,
        "saved": 1 - pruned / full if full else 0.0,
    }


def table_under_budget(budget, positions=8):
    """What the table is worth when the clock, not the depth, is the limit.

    The fixed-depth ablation understates it, and for a reason worth showing:
    at a shallow fixed depth there are few transpositions to find and the
    lookup is pure overhead. Under a time budget the search goes as deep as
    it can, which is exactly where positions start repeating.
    """
    sample = sampled_positions(seeds=range(4))[:positions]
    real = engine.TABLE
    out = {}
    for label, view in (("with", _TableView(real)),
                        ("without", _TableView(real, enabled=False))):
        depths = []
        with _swapped(engine, "TABLE", view):
            for game in sample:
                engine.reset_tables()
                deepest = {"depth": 0}

                def note(depth, _seen=deepest):
                    _seen["depth"] = max(_seen["depth"], depth)

                with _swapped(engine.REPORT, "depth_completed", note),                         _swapped(engine.REPORT, "start_move", lambda c: None),                         _swapped(engine.REPORT, "finish_move", lambda m, s: None):
                    engine.choose_move(game, time_budget=budget)
                depths.append(deepest["depth"])
        out[label] = sum(depths) / len(depths)
    out["positions"] = len(sample)
    return out


def parity_comparison(budget, positions=8):
    """Even-depth deepening against every-depth deepening, same budget.

    Averaged over several positions: on any single one the two are a ply
    apart either way, and quoting whichever way one position happened to
    fall would be quoting noise.
    """
    sample = sampled_positions(seeds=range(4))[:positions]
    out = {}
    for label, best_move in (("even", None), ("every", _all_depths)):
        depths = []
        context = (_swapped(engine, "_best_move", best_move) if best_move
                   else _swapped(engine, "MAX_DEPTH", engine.MAX_DEPTH))
        with context:
            for game in sample:
                engine.reset_tables()
                deepest = {"depth": 0}

                def note(depth, _seen=deepest):
                    _seen["depth"] = max(_seen["depth"], depth)

                with _swapped(engine.REPORT, "depth_completed", note),                         _swapped(engine.REPORT, "start_move", lambda c: None),                         _swapped(engine.REPORT, "finish_move", lambda m, s: None):
                    engine.choose_move(game, time_budget=budget)
                depths.append(deepest["depth"])
        out[label] = {"depth": sum(depths) / len(depths)}
    out["positions"] = len(sample)
    return out


# ---------- depth over many positions ----------


def sampled_positions(seeds=range(8), every=4, per_game=4):
    """Positions from games played at random near the centre."""
    out = []
    for seed in seeds:
        rng = random.Random(seed)
        game = Game()
        taken = 0
        for turn in range(40):
            if game.is_over():
                break
            cells = [(r, c) for r in range(5, 14) for c in range(5, 14)
                     if game.board.get(r, c) == EMPTY]
            rng.shuffle(cells)
            for r, c in cells:
                if game.play(r, c)[0]:
                    break
            else:
                break
            if turn >= 6 and turn % every == 0 and not game.is_over():
                out.append(_snapshot(game))
                taken += 1
                if taken >= per_game:
                    break
    return out


def _snapshot(game):
    copy = Game()
    copy.board.grid = [row[:] for row in game.board.grid]
    copy.captures = dict(game.captures)
    copy.current = game.current
    copy.pending_alignment_owner = game.pending_alignment_owner
    copy.pending_alignment = game.pending_alignment
    return copy


def depth_survey(budget):
    """How deep the engine gets, position by position, at the real budget."""
    rows = []
    for game in sampled_positions():
        engine.reset_tables()
        deepest = {"depth": 0}

        def note(depth, _seen=deepest):
            _seen["depth"] = max(_seen["depth"], depth)

        with _swapped(engine.REPORT, "depth_completed", note), \
                _swapped(engine.REPORT, "start_move", lambda color: None), \
                _swapped(engine.REPORT, "finish_move", lambda m, s: None):
            started = time.perf_counter()
            engine.choose_move(game, time_budget=budget)
            elapsed = time.perf_counter() - started
        rows.append({
            "depth": deepest["depth"],
            "seconds": elapsed,
            # A search that stopped well inside the budget did so because it
            # proved the result, not because it ran out of room.
            "solved": elapsed < budget * 0.7,
            "stones": sum(1 for row in game.board.grid for v in row if v),
        })
    return rows


# ---------- the tree, recorded node by node ----------


def _reader(function):
    """Read a call's arguments by name, whatever the signature happens to be.

    The recorder wraps private helpers of the engine, and those gain
    parameters as the engine is worked on. Binding by name means a new
    parameter makes the recorder read the same things it read before, instead
    of silently recording the wrong column.
    """
    signature = inspect.signature(function)

    def read(args, kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        return bound.arguments

    return read


def record_tree(game, depth):
    """One real search at `depth`, written down node by node.

    The engine is not asked to cooperate. `_search_move`, `_ordered_moves`
    and `_try_first` are swapped for versions that note what they were handed
    and pass the work straight through, so what comes back is the tree the
    search actually walked: every node with the alpha-beta window it was
    searched under, every move that was generated for it, and every move that
    was generated and never looked at because a cutoff came first.

    One thing is not left alone. `_ordered_moves` is a generator and the
    search stops pulling from it the moment a cutoff happens, so the moves it
    would have offered next are never created. The recorder drains it: same
    moves, same order, same result -- but a recorded node pays for a ranking
    a real one skips, which is why this measures shape and never time.

    Iterative deepening is run for real and the last iteration's tree kept:
    the table, the killers and the previous best move are all as warm as they
    would be in a game.
    """
    engine.reset_tables()
    state = SearchState(game)
    space = make_space(state.board)

    original_move = engine._search_move
    original_moves = engine._ordered_moves
    original_first = engine._try_first
    read_move = _reader(original_move)
    read_moves = _reader(original_moves)
    stack = []

    def traced_move(*args, **kwargs):
        field = read_move(args, kwargs)
        node = {
            "move": field["move"], "captured": field["captured"],
            "ply": field["ply"], "depth": field["depth"],
            "alpha": field["alpha"], "beta": field["beta"],
            "score": field["score"], "wins": field["wins"],
            "loses": field["loses"], "value": None,
            "children": [], "offered": None, "table_move": None,
        }
        stack[-1]["children"].append(node)
        stack.append(node)
        try:
            node["value"] = original_move(*args, **kwargs)
        finally:
            stack.pop()
        return node["value"]

    def traced_moves(*args, **kwargs):
        field = read_moves(args, kwargs)
        node = stack[-1]
        generated = list(original_moves(*args, **kwargs))
        node["offered"] = [{"move": move, "score": score, "wins": wins,
                            "loses": loses}
                           for move, _captured, score, wins, loses in generated]
        node["table_move"] = field["table_move"]
        return iter(generated)

    def traced_first(moves, preferred):
        ordered = original_first(moves, preferred)
        root = stack[0]
        root["offered"] = [{"move": move, "score": score, "wins": wins,
                            "loses": loses}
                           for score, wins, loses, move, _captured in ordered]
        root["previous_best"] = preferred
        return ordered

    engine._search_move = traced_move
    engine._ordered_moves = traced_moves
    engine._try_first = traced_first
    root = None
    try:
        best = None
        for step in range(2, max(depth, 2) + 1, 2):
            root = {"move": None, "captured": (), "ply": -1, "depth": step,
                    "alpha": -engine.INFINITY, "beta": engine.INFINITY,
                    "score": 0, "wins": False, "loses": False, "value": None,
                    "children": [], "offered": None, "table_move": None,
                    "previous_best": best, "is_root": True}
            stack[:] = [root]
            best, value = engine._search_root(state, space, step,
                                              time.perf_counter() + 600, best)
            root["value"] = value
            root["best"] = best
    finally:
        engine._search_move = original_move
        engine._ordered_moves = original_moves
        engine._try_first = original_first

    _annotate(root)
    return root


def _annotate(node):
    """Match what a node generated against what it actually searched.

    Every move the engine looked at arrives here as a child, and every move it
    generated as an entry of `offered`. Lining the two up is what turns the
    recording into the thing worth showing: the candidates the cutoff spared
    the search from ever expanding.
    """
    searched = {}
    previous = None
    for child in node["children"]:
        # The same move twice running is a principal variation re-search: the
        # null window said "better than alpha", so it is measured for real.
        child["research"] = child["move"] == previous
        previous = child["move"]
        child["null_window"] = child["beta"] == child["alpha"] + 1
        # A leaf that still has children was extended past the horizon.
        child["extended"] = child["depth"] <= 1 and bool(child["children"])
        found = searched.setdefault(child["move"],
                                    {"probe": None, "full": None})
        if child["null_window"] and found["full"] is None:
            found["probe"] = child
        else:
            found["full"] = child
        _annotate(child)

    for item in node["offered"] or ():
        found = searched.get(item["move"])
        item["searched"] = found is not None
        item["probe"] = found["probe"] if found else None
        item["node"] = (found["full"] or found["probe"]) if found else None
    node["moves"] = list(node["offered"] or ())
    node["pruned"] = sum(1 for item in node["moves"] if not item["searched"])
    # A node's own window is the one its *first* move was searched under; the
    # ones after it carry the null window instead.
    node["window"] = ((node["children"][0]["alpha"],
                       node["children"][0]["beta"])
                      if node["children"] else None)


def replay(game, path):
    """The position reached by playing `path`, a list of recorded nodes.

    Each node carries the captures the engine resolved when it played that
    move, so the position is rebuilt by the engine's own `play` rather than by
    dropping stones onto a grid.
    """
    state = SearchState(game)
    for node in path:
        r, c = node["move"]
        state.play(r, c, node["captured"])
    return state


# ---------- the funnel ----------


def funnel(game, chosen=None):
    """The candidate set narrowing, stage by stage, on one position.

    Each stage is a set of cells and the time the engine spent producing it.
    The point is the shape of the sequence: two cheap stages throw most of the
    goban away, and only what survives them reaches the stage that puts a
    stone down and scores the position.
    """
    state = SearchState(game)
    size = state.board.size
    grid = state.board.grid

    started = time.perf_counter()
    space = make_space(state.board)
    space_seconds = time.perf_counter() - started

    width = engine._branching(0)
    keep = search_space._shortlist_size(width)
    reachable = sorted(cell for cell in state.nearby & space.cells
                       if grid[cell[0]][cell[1]] == EMPTY)

    started = time.perf_counter()
    cells = shortlist(state, space, keep)
    shortlist_seconds = time.perf_counter() - started

    # The same shortlist with the tactical promotion blinded, so that the
    # cells it rescued from the cut can be named rather than asserted.
    with _swapped(search_space, "longest_run", lambda evaluator, r, c: 0):
        by_crowding = shortlist(state, space, keep)
    crowded_only = {(r, c) for _, r, c in by_crowding}
    promoted = [(r, c) for _, r, c in cells if (r, c) not in crowded_only]

    started = time.perf_counter()
    ranked = ranked_moves(state, space, width)
    ranked_seconds = time.perf_counter() - started

    forced = sorted(search_space.forced_replies(state, cells))
    per_candidate = ranked_seconds / len(cells) if cells else 0.0

    stages = [
        {
            "key": "board", "title": "Every intersection",
            "rule": "the goban as the rules see it",
            "cells": [(r, c) for r in range(size) for c in range(size)],
            "seconds": None,
        },
        {
            "key": "windows", "title": "Inside the search windows",
            "rule": f"stones within {CLUSTER_RADIUS} clustered, each cluster "
                    f"boxed, cheap boxes merged, grown by {WINDOW_MARGIN}",
            "cells": sorted(space.cells), "seconds": space_seconds,
        },
        {
            "key": "reach", "title": "Empty, with a stone in reach",
            "rule": "a crowding count kept up to date as stones appear and "
                    "disappear -- the board is never swept",
            "cells": reachable, "seconds": None,
        },
        {
            "key": "shortlist", "title": f"The {keep} most crowded",
            "rule": f"twice the beam of {width}, plus any cell that would "
                    f"make a line of {CRITICAL_RUN} for either colour",
            "cells": [(r, c) for _, r, c in cells],
            "seconds": shortlist_seconds,
        },
        {
            "key": "ranked", "title": "Played, scored, taken back",
            "rule": "the only stage that touches the board, and the bill the "
                    "whole funnel exists to keep down",
            "cells": [entry[3] for entry in ranked], "seconds": ranked_seconds,
        },
        {
            "key": "chosen", "title": "Searched, and one is played",
            "rule": "alpha-beta over the beam, as deep as the clock allows",
            "cells": [chosen] if chosen else [], "seconds": None,
        },
    ]
    for stage in stages:
        stage["count"] = len(stage["cells"])

    return {
        "stages": stages,
        "beam": width,
        "keep": keep,
        "promoted": promoted,
        "forced": forced,
        "ranked": [(score, r, c, wins, loses)
                   for score, wins, loses, (r, c), _ in ranked],
        "crowding": [row[:] for row in state.proximity],
        "windows": [(w.r0, w.c0, w.r1, w.c1) for w in space.windows],
        "per_candidate": per_candidate,
        "whole_board_estimate": per_candidate * size * size,
        "to_play": STONE_NAME[state.current],
    }


# ---------- one optimisation at a time ----------


def baseline_search(game, depth=ABLATION_DEPTH):
    """The engine as it stands, at a fixed depth: what an ablation compares to."""
    seconds, nodes = _timed_search(game, depth)
    return {"seconds": seconds, "nodes": nodes}


def ablate(game, key, depth=ABLATION_DEPTH):
    """The same search with one optimisation switched off from the outside."""
    for case in ABLATION_CASES:
        if case[0] == key:
            break
    else:
        raise KeyError(key)
    _, name, detail, factory = case
    with factory():
        seconds, nodes = _timed_search(game, depth)
    return {"key": key, "name": name, "detail": detail,
            "seconds": seconds, "nodes": nodes}


# ---------- iterative deepening, one depth at a time ----------


def deepening_steps(game, budget):
    """`deepening` as a generator, so a caller can watch it fill in.

    The clock only runs while a depth is being searched: what is left of the
    budget is recomputed at the top of each iteration rather than fixed once
    at the start. Run straight through, that is the same deadline; for a
    caller that stops to draw between depths it is the difference between
    measuring the engine and measuring how fast the user clicks.
    """
    engine.reset_tables()
    state = SearchState(game)
    space = make_space(state.board)
    best = None
    spent = 0.0
    with counting_nodes() as tally:
        for depth in range(2, engine.MAX_DEPTH + 1, 2):
            before = tally["nodes"]
            started = time.perf_counter()
            try:
                move, value = engine._search_root(
                    state, space, depth, started + max(budget - spent, 0.0),
                    best)
            except engine.SearchTimeout:
                spent += time.perf_counter() - started
                yield {"depth": depth, "seconds": None, "nodes": None,
                       "move": None, "value": None, "cut": True,
                       "spent": spent}
                return
            elapsed = time.perf_counter() - started
            spent += elapsed
            best = move
            yield {
                "depth": depth, "seconds": elapsed,
                "nodes": tally["nodes"] - before, "move": move,
                "value": value, "cut": False, "spent": spent,
                "proven": abs(value) >= engine.MATE_FLOOR,
            }
            if move is None or abs(value) >= engine.MATE_FLOOR:
                return


def search_result(game, budget, max_depth=None):
    """Ask the engine for its move, and note what the search cost.

    The same call the game itself makes. The reporting hooks are borrowed for
    the duration, so the depth reached is read off the engine rather than
    parsed out of what it printed.
    """
    engine.reset_tables()
    deepest = {"depth": 0}

    def note(depth):
        deepest["depth"] = max(deepest["depth"], depth)

    with counting_nodes() as tally,             _swapped(engine.REPORT, "depth_completed", note),             _swapped(engine.REPORT, "start_move", lambda color: None),             _swapped(engine.REPORT, "finish_move", lambda move, seconds: None):
        started = time.perf_counter()
        move = engine.choose_move(game, time_budget=budget,
                                  max_depth=max_depth or engine.MAX_DEPTH)
        elapsed = time.perf_counter() - started
    return {"move": move, "depth": deepest["depth"], "nodes": tally["nodes"],
            "seconds": elapsed, "table": len(engine.TABLE)}


# ---------- everything ----------


def collect(budget):
    game = build_game(TRACE_MOVES)
    return {
        "budget": budget,
        "beam": {
            "by_ply": list(engine.BRANCHING_BY_PLY),
            "deep": engine.DEEP_BRANCHING,
            "root_narrows_at": engine.ROOT_NARROWS_AT,
            "root_deep": engine.ROOT_BRANCHING_DEEP,
            "max_depth": engine.MAX_DEPTH,
        },
        "trace": trace(game),
        "deepening": deepening(game, budget),
        "micro": micro_benchmarks(game),
        "ablations": ablations(game),
        "parity": parity_comparison(budget),
        "table_budget": table_under_budget(budget),
        "pruning": pruning_comparison(game),
        "survey": depth_survey(budget),
    }
