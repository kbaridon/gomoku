"""Build a position by hand and watch the engine think about it.

The measured panels in `viz.show` explain what the engine does in general.
This does the opposite: it takes whatever position you put in front of it and
shows what the engine makes of *that* one -- which windows it confined itself
to, which cells it shortlisted and in what order, what it settled on and how
deep it got there.

Click an empty intersection to place a stone; click a stone to take it off.
Everything else is on the right.

Stones are placed straight onto the board rather than played through `Game`,
so any shape can be set up, legal to arrive at or not. The side to move is
therefore explicit rather than inferred, and the engine is asked about the
position exactly as it stands.
"""

import contextlib
import io
import re
import time

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
from matplotlib.widgets import Button, RadioButtons, Slider

import ai.engine as engine
from ai.config import TIME_BUDGET
from ai.search_space import _shortlist_size, search_space, shortlist
from ai.state import SearchState
from board import BLACK, BOARD_SIZE, EMPTY, STONE_NAME, opponent
from game import Game
from ui import (ACCENT, BG, BLACK_STONE, CARD_BORDER, GOBAN, GRID, SUCCESS,
                TEXT_MAIN, TEXT_MUTE, WHITE_STONE)

CARD = "#FFFFFF"
SOFT = "#EFE6D0"

LAYERS = ("stones only", "search windows", "crowding", "shortlist", "ranking")

OPENING = [(9, 9), (9, 10), (10, 10), (8, 8), (10, 9), (8, 10)]


class Explorer:
    """A clickable goban with the engine's reasoning beside it."""

    def __init__(self):
        self.game = Game()
        self.to_play = BLACK
        self.history = []
        self.layer = LAYERS[1]
        self.depth_cap = 0          # 0 = use the time budget
        self.result = None
        self.trace = None
        for r, c in OPENING:
            self.game.board.set(r, c, self.to_play)
            self.to_play = opponent(self.to_play)
            self.history.append((r, c))

        self.fig = plt.figure(figsize=(14, 8.5), facecolor=BG)
        self.fig.canvas.manager.set_window_title(
            "Gomoku - explore what the engine sees")
        # The board and the things that change it live on the left; what the
        # engine reports back lives on the right.
        self.board_ax = self.fig.add_axes([0.035, 0.20, 0.45, 0.75])
        self.side_ax = self.fig.add_axes([0.53, 0.44, 0.45, 0.51])
        self.bars_ax = self.fig.add_axes([0.60, 0.10, 0.375, 0.26])
        self._build_controls()
        self.fig.canvas.mpl_connect("button_press_event", self._on_click)
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self.refresh(think=True)

    # ---------- controls ----------

    def _build_controls(self):
        # Widgets have to stay referenced or matplotlib stops delivering
        # their callbacks.
        radio_ax = self.fig.add_axes([0.035, 0.015, 0.115, 0.16])
        radio_ax.set_facecolor(CARD)
        for spine in radio_ax.spines.values():
            spine.set_color(CARD_BORDER)
        self.radio = RadioButtons(radio_ax, LAYERS, active=1,
                                  activecolor=ACCENT)
        for label in self.radio.labels:
            label.set_fontsize(8.5)
            label.set_color(TEXT_MAIN)
        self.radio.on_clicked(self._on_layer)

        slider_ax = self.fig.add_axes([0.215, 0.115, 0.265, 0.022])
        slider_ax.set_facecolor(SOFT)
        self.slider = Slider(slider_ax, "depth ", 0, 14, valinit=0, valstep=2,
                             color=ACCENT, initcolor="none")
        self.slider.label.set_fontsize(9)
        self.slider.label.set_color(TEXT_MUTE)
        self.slider.valtext.set_fontsize(9)
        self.slider.valtext.set_color(TEXT_MAIN)
        self.slider.on_changed(self._on_depth)

        self.buttons = []
        labels = [("Think", self._think), ("Play best", self._play_best),
                  ("Undo", self._undo), ("Clear", self._clear),
                  ("Swap turn", self._swap)]
        for i, (text, action) in enumerate(labels):
            ax = self.fig.add_axes([0.215 + i * 0.055, 0.028, 0.050, 0.040])
            button = Button(ax, text, color="#EAD8B0", hovercolor="#D6C098")
            button.label.set_fontsize(8)
            button.label.set_color(TEXT_MAIN)
            button.on_clicked(action)
            self.buttons.append(button)

    # ---------- events ----------

    def _cell(self, event):
        if event.inaxes is not self.board_ax or event.xdata is None:
            return None
        r, c = round(event.ydata), round(event.xdata)
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            return r, c
        return None

    def _on_click(self, event):
        cell = self._cell(event)
        if cell is None:
            return
        r, c = cell
        if self.game.board.get(r, c) == EMPTY:
            self.game.board.set(r, c, self.to_play)
            self.to_play = opponent(self.to_play)
            self.history.append(cell)
        else:
            self.game.board.set(r, c, EMPTY)
            if cell in self.history:
                self.history.remove(cell)
        self.refresh(think=True)

    def _on_key(self, event):
        if event.key in ("q", "escape"):
            plt.close(self.fig)
        elif event.key == "t":
            self._think(None)
        elif event.key == "u":
            self._undo(None)
        elif event.key == "enter":
            self._play_best(None)

    def _on_layer(self, label):
        self.layer = label
        self.refresh(think=False)

    def _on_depth(self, value):
        self.depth_cap = int(value)
        self.refresh(think=True)

    def _think(self, _event):
        self.refresh(think=True)

    def _play_best(self, _event):
        if self.result and self.result["move"]:
            r, c = self.result["move"]
            self.game.board.set(r, c, self.to_play)
            self.to_play = opponent(self.to_play)
            self.history.append((r, c))
            self.refresh(think=True)

    def _undo(self, _event):
        if self.history:
            r, c = self.history.pop()
            self.game.board.set(r, c, EMPTY)
            self.to_play = opponent(self.to_play)
            self.refresh(think=True)

    def _clear(self, _event):
        self.game = Game()
        self.to_play = BLACK
        self.history = []
        self.refresh(think=True)

    def _swap(self, _event):
        self.to_play = opponent(self.to_play)
        self.refresh(think=True)

    # ---------- the engine ----------

    def _run(self):
        """Ask the engine about the position as it stands."""
        self.game.current = self.to_play
        stones = sum(1 for row in self.game.board.grid for v in row if v)
        if stones == 0:
            self.result = self.trace = None
            return

        state = SearchState(self.game)
        space = search_space(state.board)
        width = engine._branching(0)
        cells = shortlist(state, space, _shortlist_size(width))
        from ai.search_space import ranked_moves
        ranked = ranked_moves(state, space, width)
        self.trace = {"space": space, "shortlist": cells, "ranked": ranked,
                      "proximity": state.proximity, "state": state}

        engine.reset_tables()
        nodes = {"n": 0}
        original = engine._negamax

        def counted(*args, **kwargs):
            nodes["n"] += 1
            return original(*args, **kwargs)

        engine._negamax = counted
        buffer = io.StringIO()
        try:
            started = time.perf_counter()
            with contextlib.redirect_stdout(buffer):
                move = engine.choose_move(
                    self.game, time_budget=TIME_BUDGET,
                    max_depth=self.depth_cap or engine.MAX_DEPTH)
            elapsed = time.perf_counter() - started
        finally:
            engine._negamax = original

        reached = re.findall(r"\((?:depth (\d+)|opening)\)", buffer.getvalue())
        self.result = {
            "move": move,
            "seconds": elapsed,
            "nodes": nodes["n"],
            "depth": int(reached[0]) if reached and reached[0] else 0,
            "table": len(engine.TABLE),
        }

    # ---------- drawing ----------

    def refresh(self, think):
        if think:
            self._run()
        self._draw_board()
        self._draw_side()
        self._draw_bars()
        self.fig.canvas.draw_idle()

    def _draw_board(self):
        ax = self.board_ax
        ax.clear()
        ax.set_facecolor(GOBAN)
        for i in range(BOARD_SIZE):
            ax.plot([0, BOARD_SIZE - 1], [i, i], color=GRID, lw=0.5, zorder=1)
            ax.plot([i, i], [0, BOARD_SIZE - 1], color=GRID, lw=0.5, zorder=1)

        trace = self.trace
        if trace and self.layer == "search windows":
            for window in trace["space"].windows:
                ax.add_patch(Rectangle(
                    (window.c0 - 0.5, window.r0 - 0.5),
                    window.c1 - window.c0 + 1, window.r1 - window.r0 + 1,
                    facecolor=ACCENT, alpha=0.15, edgecolor=ACCENT, lw=1.6,
                    linestyle=(0, (5, 3)), zorder=2))
        elif trace and self.layer == "crowding":
            proximity = trace["proximity"]
            peak = max((max(row) for row in proximity), default=1) or 1
            for r, row in enumerate(proximity):
                for c, weight in enumerate(row):
                    if weight and self.game.board.get(r, c) == EMPTY:
                        ax.add_patch(Rectangle(
                            (c - 0.5, r - 0.5), 1, 1, zorder=2,
                            facecolor=ACCENT, edgecolor="none",
                            alpha=0.10 + 0.60 * weight / peak))
        elif trace and self.layer == "shortlist":
            for rank, (_, r, c) in enumerate(trace["shortlist"], start=1):
                self._marker(ax, r, c, rank, filled=False)
        elif trace and self.layer == "ranking":
            for rank, (_, _, _, (r, c), _) in enumerate(trace["ranked"], 1):
                self._marker(ax, r, c, rank, filled=(rank == 1))

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                value = self.game.board.get(r, c)
                if value != EMPTY:
                    ax.add_patch(Circle(
                        (c, r), 0.42, zorder=5, lw=0.6,
                        facecolor=BLACK_STONE if value == BLACK else WHITE_STONE,
                        edgecolor="#00000066"))

        if self.result and self.result["move"]:
            r, c = self.result["move"]
            ax.add_patch(Circle((c, r), 0.46, facecolor="none", lw=2.6,
                                edgecolor=SUCCESS, zorder=8))

        ax.set_xlim(-1, BOARD_SIZE)
        ax.set_ylim(BOARD_SIZE, -1)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        for spine in ax.spines.values():
            spine.set_color(CARD_BORDER)

    def _marker(self, ax, r, c, rank, filled):
        ax.add_patch(Circle((c, r), 0.40, zorder=4, edgecolor=ACCENT, lw=1.8,
                            facecolor=ACCENT if filled else "none",
                            alpha=0.45 if filled else 1))
        ax.text(c, r, str(rank), ha="center", va="center", fontsize=6.5,
                color=TEXT_MAIN, fontweight="bold", zorder=6)

    def _draw_side(self):
        ax = self.side_ax
        ax.clear()
        ax.set_facecolor(CARD)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color(CARD_BORDER)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        ax.text(0.04, 0.955, "What the engine sees", fontsize=14,
                color=TEXT_MAIN, fontweight="bold", va="top")
        ax.text(0.04, 0.895,
                "click to place a stone, click one again to remove it",
                fontsize=9, color=TEXT_MUTE, va="top")

        ax.text(0.545, 0.955, f"{STONE_NAME[self.to_play]} to play",
                fontsize=11, color=ACCENT, fontweight="bold", va="top")

        if not self.trace or not self.result:
            ax.text(0.04, 0.55, "Put some stones on the board.", fontsize=11,
                    color=TEXT_MUTE)
            return

        trace, result = self.trace, self.result
        space_cells = len(trace["space"].cells)
        rows = [
            ("Search windows", f"{len(trace['space'].windows)}"),
            ("Cells in the space", f"{space_cells} of 361"),
            ("Shortlisted", f"{len(trace['shortlist'])}"),
            ("Searched", f"{len(trace['ranked'])}"),
        ]
        for i, (key, value) in enumerate(rows):
            y = 0.80 - i * 0.058
            ax.text(0.06, y, key, fontsize=10, color=TEXT_MUTE, va="center")
            ax.text(0.44, y, value, fontsize=10.5, color=TEXT_MAIN,
                    va="center", ha="right", fontweight="bold")

        chosen = result["move"]
        ax.text(0.56, 0.80, "It plays", fontsize=10, color=TEXT_MUTE,
                va="center")
        ax.text(0.56, 0.725, f"{chosen}" if chosen else "nothing",
                fontsize=17, color=SUCCESS, fontweight="bold", va="center")

        cap = ("time budget" if not self.depth_cap
               else f"capped at {self.depth_cap}")
        more = [
            ("Depth reached", f"{result['depth']}"),
            ("Nodes", f"{result['nodes']:,}".replace(",", " ")),
            ("Time", f"{result['seconds'] * 1000:.0f} ms"),
            ("Table entries", f"{result['table']:,}".replace(",", " ")),
        ]
        for i, (key, value) in enumerate(more):
            y = 0.62 - i * 0.058
            ax.text(0.56, y, key, fontsize=10, color=TEXT_MUTE, va="center")
            ax.text(0.96, y, value, fontsize=10.5, color=TEXT_MAIN,
                    va="center", ha="right", fontweight="bold")
        ax.text(0.56, 0.355, cap, fontsize=8.5, color=TEXT_MUTE)

        ax.text(0.04, 0.30, self._commentary(), fontsize=9.2,
                color=TEXT_MAIN, va="top", linespacing=1.5)

    def _commentary(self):
        """A sentence about this position, not about the algorithm."""
        trace, result = self.trace, self.result
        ranked = trace["ranked"]
        if not ranked:
            return "No candidate move: the search space came up empty."
        if len(ranked) == 1:
            return ("Only one move survived generation: either it wins on the\n"
                    "spot, or the opponent threatens to and everything that\n"
                    "does not answer that was dropped.")
        top, second = ranked[0][0], ranked[1][0]
        gap = top - second
        if result["depth"] == 0:
            return "Opening move: played from the centre without searching."
        if gap > 50_000:
            return (f"The best move scores {gap:,} more than the next one\n"
                    f"before any search: a threat this size settles the\n"
                    f"ranking on its own.".replace(",", " "))
        if gap < 500:
            return ("The top candidates are within a few hundred points of\n"
                    "each other, so the static ranking barely separates them\n"
                    "and the depth is doing the deciding.")
        return (f"The static ranking separates the top two by {gap:,} points;\n"
                f"the search then confirms or overturns that."
                .replace(",", " "))

    def _draw_bars(self):
        ax = self.bars_ax
        ax.clear()
        ax.set_facecolor(BG)
        trace = self.trace
        if not trace or not trace["ranked"]:
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            return

        top = trace["ranked"][:7]
        labels = [f"{i}. {mv}" for i, (_, _, _, mv, _) in enumerate(top, 1)]
        scores = [entry[0] for entry in top]
        floor = min(scores)
        offsets = [s - floor + 1 for s in scores]
        chosen = self.result["move"] if self.result else None
        colors = [SUCCESS if mv == chosen else ACCENT
                  for _, _, _, mv, _ in top]

        spots = range(len(labels))
        ax.barh(list(spots), offsets, color=colors, height=0.6, zorder=3)
        ax.set_yticks(list(spots))
        ax.set_yticklabels(labels, fontsize=8.5, color=TEXT_MAIN)
        ax.invert_yaxis()
        ax.set_xticks([])
        ax.set_xlabel("static score of each candidate -- green is the move "
                      "the search settled on", fontsize=8.5, color=TEXT_MUTE)
        for spine in ax.spines.values():
            spine.set_visible(False)
        span = max(offsets) or 1
        for i, score in enumerate(scores):
            ax.text(offsets[i] + span * 0.02, i, f"{score:,}".replace(",", " "),
                    va="center", fontsize=8.5, color=TEXT_MAIN)
        ax.set_xlim(0, span * 1.35)


def explore():
    Explorer()
    plt.show()
