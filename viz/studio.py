"""The engine explaining itself, one chapter at a time.

`viz.explore` shows what the engine *sees*. This shows what it *does*: the
same position taken through five views, each of them a live measurement of
the real engine rather than a drawing of one.

    1 Candidates     361 intersections narrowed to one move, stage by stage
    2 Alpha-beta     the recorded search tree, walked one node at a time
    3 Deepening      depth 2, 4, 6... filling in against the clock
    4 Optimisations  each one switched off, on this position, on demand
    5 Evaluation     where a leaf's score comes from, line by line

The position is shared by all five and it is yours: click an intersection to
place a stone, click it again to take it off, and every chapter re-answers
about the board in front of you. Nothing here is precomputed and nothing is
quoted from a previous run -- the numbers move when the position does, which
is the only reason to trust them.

Everything is drawn on two axes: the goban on the left, and one panel on the
right that each chapter paints itself. Clicks on the panel are resolved
against rectangles the chapter registered while drawing, so there are no
widgets to create and destroy as the chapters change, and none left invisible
behind a panel to swallow a click.
"""

import math
import textwrap

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
from matplotlib.widgets import Button

from ai.config import DEFENCE_WEIGHT, TIME_BUDGET
from ai.engine import MATE_FLOOR, WIN_VALUE
from ai.lines import CELL_LINES, LINES
from ai.patterns import score_line
from ai.state import SearchState
from board import BLACK, BOARD_SIZE, EMPTY, STONE_NAME, opponent
from game import Game
from ui import (ACCENT, BG, BLACK_STONE, CARD_BORDER, DANGER, GOBAN, GRID,
                LAST_MOVE, STAR_POINTS, SUCCESS, TEXT_MAIN, TEXT_MUTE,
                WHITE_STONE)

from . import measure
from .naive import matched_shapes

CARD = "#FFFFFF"
SOFT = "#F3EBD9"
RULE = "#DCCFB4"
GREY = "#9E927E"
WARM = "#C8791F"
PALE = "#9FBBD1"

# The panel is drawn in units of its own: 100 across, 75 down, y increasing
# downwards so that laying text out reads top to bottom. The pair is chosen so
# that one unit is the same size in both directions -- a circle drawn in panel
# units comes out round.
PANEL_W, PANEL_H = 100.0, 75.0
NOTE_W, NOTE_H = 100.0, 34.0

OPENING = [(9, 9), (9, 10), (10, 10), (8, 8), (10, 9), (8, 10)]


# ---------- small drawing helpers ----------


def _spaced(value):
    """A big number with its thousands parted, and no comma to misread."""
    return f"{int(value):,}".replace(",", " ")


def _signed(value):
    return ("+" if value > 0 else "") + _spaced(value)


def _bound(value):
    """An alpha-beta bound, infinities included."""
    if value == float("inf"):
        return "+∞"
    if value == -float("inf"):
        return "-∞"
    return _spaced(value)


def _outcome(value):
    """A search value in plain language: a raw score, or a proven mate.

    A won or lost line is encoded as WIN_VALUE offset by how many plies away
    the mate is, so the number itself (in the billions) is meaningless to
    read -- what matters is who wins and how soon.
    """
    if abs(value) >= MATE_FLOOR:
        plies = WIN_VALUE - abs(value)
        return f"wins in {plies}" if value > 0 else f"loses in {plies}"
    return _signed(value)


def _plural(count, word, many=None):
    return f"{count} {word if count == 1 else (many or word + 's')}"


def _ms(seconds):
    if seconds is None:
        return "--"
    if seconds < 0.001:
        return f"{seconds * 1e6:.0f} µs"
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms"
    return f"{seconds:.2f} s"


def _card(ax, x, y, w, h, face=CARD, edge=CARD_BORDER, lw=0.9, z=2,
          alpha=1.0):
    patch = Rectangle((x, y), w, h, facecolor=face, edgecolor=edge,
                      lw=lw, zorder=z, alpha=alpha)
    ax.add_patch(patch)
    return patch


def _text(ax, x, y, body, size=9, color=TEXT_MAIN, weight="normal",
          ha="left", va="center", z=5, style="normal"):
    return ax.text(x, y, body, fontsize=size, color=color, fontweight=weight,
                   ha=ha, va=va, zorder=z, fontstyle=style)


def _paragraph(ax, x, y, body, width, size=8, color=TEXT_MUTE, step=2.4,
               limit=None, z=5):
    """Wrapped body text; returns the y just past the last line drawn."""
    lines = textwrap.wrap(body, width)
    if limit:
        lines = lines[:limit]
    for index, line in enumerate(lines):
        _text(ax, x, y + index * step, line, size=size, color=color, z=z)
    return y + len(lines) * step


class Studio:
    """One window, one position, five ways of looking at what the engine did."""

    def __init__(self, budget=TIME_BUDGET):
        self.budget = budget
        self.game = Game()
        self.to_play = BLACK
        self.history = []
        for r, c in OPENING:
            self.game.board.set(r, c, self.to_play)
            self.to_play = opponent(self.to_play)
            self.history.append((r, c))

        self.stamp = 0
        self.result = None
        self.hotspots = []

        self.chapters = [Candidates(self), AlphaBeta(self), Deepening(self),
                         Optimisations(self), Evaluation(self)]
        self.active = 0

        self.fig = plt.figure(figsize=(15.0, 8.6), facecolor=BG)
        self.fig.canvas.manager.set_window_title(
            "Gomoku - how the engine chooses a move")
        self.board_ax = self.fig.add_axes([0.012, 0.375, 0.313, 0.515])
        self.note_ax = self.fig.add_axes([0.012, 0.175, 0.313, 0.185])
        self.panel_ax = self.fig.add_axes([0.345, 0.045, 0.645, 0.845])
        for ax in (self.note_ax, self.panel_ax):
            ax.set_xticks([])
            ax.set_yticks([])
        self._build_widgets()
        self.fig.canvas.mpl_connect("button_press_event", self._on_click)
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self.refresh()

    # ---------- widgets ----------

    def _build_widgets(self):
        self.tabs = []
        for index, chapter in enumerate(self.chapters):
            ax = self.fig.add_axes([0.012 + index * 0.114, 0.925, 0.108,
                                    0.052])
            button = Button(ax, chapter.label, color=SOFT,
                            hovercolor="#E4D6B6")
            button.label.set_fontsize(9)
            button.on_clicked(lambda _event, i=index: self._on_tab(i))
            self.tabs.append(button)

        self.buttons = []
        actions = [("Think", self._think), ("Play best", self._play_best),
                   ("Undo", self._undo), ("Clear", self._clear),
                   ("Swap turn", self._swap)]
        for index, (name, action) in enumerate(actions):
            ax = self.fig.add_axes([0.012 + index * 0.0641, 0.093, 0.0571,
                                    0.044])
            button = Button(ax, name, color="#EAD8B0", hovercolor="#D6C098")
            button.label.set_fontsize(8)
            button.label.set_color(TEXT_MAIN)
            button.on_clicked(action)
            self.buttons.append(button)

        self.fig.text(0.0125, 0.055,
                      "click an intersection to place a stone, click it again "
                      "to remove it", fontsize=8, color=TEXT_MUTE)
        self.fig.text(0.0125, 0.026,
                      "1-5 or left / right change chapter   ·   T thinks   "
                      "·   space steps   ·   Q quits",
                      fontsize=8, color=TEXT_MUTE)
        self.fig.text(0.99, 0.951,
                      "every number on the right is measured on the position "
                      "on the left", fontsize=8.5, color=TEXT_MUTE,
                      ha="right", va="center")

    # ---------- state ----------

    @property
    def chapter(self):
        return self.chapters[self.active]

    def changed(self):
        """The position moved: everything measured about it is now stale."""
        self.stamp += 1
        self.result = None

    def think(self):
        """The engine's answer for this position, measured once and kept."""
        if self.result is None and self.stones():
            self.result = measure.search_result(self.position(), self.budget)
        return self.result

    def stones(self):
        return sum(1 for row in self.game.board.grid for value in row if value)

    def position(self):
        """The game as the engine should be asked about it."""
        self.game.current = self.to_play
        return self.game

    def working(self, message, function):
        """Run something slow, with the panel saying so first.

        The banner is painted straight onto the panel as it stands rather than
        by redrawing it, because redrawing a panel is what asks a chapter to
        measure, and that is the very thing being waited for. It is removed
        again once the work is done, so it never lingers as a stray artist
        once the chapter draws its real result on top of the same axes.
        """
        ax = self.panel_ax
        patch = _card(ax, 62, 0.0, 38, 5.6, face=WARM, edge=WARM, z=20)
        label = _text(ax, 81, 2.8, message, size=9.5, color=CARD,
                      weight="bold", ha="center", z=21)
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        try:
            return function()
        finally:
            patch.remove()
            label.remove()

    # ---------- events ----------

    def _on_tab(self, index):
        self.active = index
        self.refresh()

    def _on_click(self, event):
        if event.inaxes is self.board_ax and event.xdata is not None:
            r, c = round(event.ydata), round(event.xdata)
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
                if self.chapter.board_click((r, c), event):
                    self.refresh()
                else:
                    self._toggle_stone(r, c)
            return
        if event.inaxes is self.panel_ax and event.xdata is not None:
            for x0, x1, y0, y1, key in self.hotspots:
                if x0 <= event.xdata <= x1 and y0 <= event.ydata <= y1:
                    if self.chapter.click(key):
                        self.refresh()
                    return

    def _toggle_stone(self, r, c):
        if self.game.board.get(r, c) == EMPTY:
            self.game.board.set(r, c, self.to_play)
            self.to_play = opponent(self.to_play)
            self.history.append((r, c))
        else:
            self.game.board.set(r, c, EMPTY)
            if (r, c) in self.history:
                self.history.remove((r, c))
        self.changed()
        self.refresh()

    def _on_key(self, event):
        if event.key in ("q", "escape"):
            plt.close(self.fig)
        elif event.key == "right":
            self._on_tab((self.active + 1) % len(self.chapters))
        elif event.key == "left":
            self._on_tab((self.active - 1) % len(self.chapters))
        elif event.key in ("1", "2", "3", "4", "5"):
            self._on_tab(int(event.key) - 1)
        elif event.key == "t":
            self._think(None)
        elif event.key == "u":
            self._undo(None)
        elif self.chapter.key(event.key):
            self.refresh()

    def _think(self, _event):
        self.result = None
        self.working("thinking...", self.think)
        self.refresh()

    def _play_best(self, _event):
        result = self.working("thinking...", self.think)
        if result and result["move"]:
            r, c = result["move"]
            self.game.board.set(r, c, self.to_play)
            self.to_play = opponent(self.to_play)
            self.history.append((r, c))
            self.changed()
        self.refresh()

    def _undo(self, _event):
        if self.history:
            r, c = self.history.pop()
            self.game.board.set(r, c, EMPTY)
            self.to_play = opponent(self.to_play)
            self.changed()
            self.refresh()

    def _clear(self, _event):
        self.game = Game()
        self.to_play = BLACK
        self.history = []
        self.changed()
        self.refresh()

    def _swap(self, _event):
        self.to_play = opponent(self.to_play)
        self.changed()
        self.refresh()

    # ---------- drawing ----------

    def refresh(self):
        for index, button in enumerate(self.tabs):
            colour = ACCENT if index == self.active else SOFT
            button.color = colour
            button.ax.set_facecolor(colour)
            button.label.set_color(CARD if index == self.active else TEXT_MAIN)
            button.label.set_fontweight(
                "bold" if index == self.active else "normal")
        self._draw_panel()
        self._draw_board()
        self._draw_note()
        self.fig.canvas.draw_idle()

    def _draw_board(self):
        ax = self.board_ax
        ax.clear()
        ax.set_facecolor(GOBAN)
        grid, last = self.chapter.board_state()
        for i in range(BOARD_SIZE):
            ax.plot([0, BOARD_SIZE - 1], [i, i], color=GRID, lw=0.4, zorder=1)
            ax.plot([i, i], [0, BOARD_SIZE - 1], color=GRID, lw=0.4, zorder=1)
        for r in STAR_POINTS:
            for c in STAR_POINTS:
                ax.add_patch(Circle((c, r), 0.09, color=GRID, zorder=1))

        self.chapter.overlay(ax, grid)

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                value = grid[r][c]
                if value != EMPTY:
                    ax.add_patch(Circle(
                        (c, r), 0.42, zorder=6, lw=0.6,
                        facecolor=BLACK_STONE if value == BLACK
                        else WHITE_STONE, edgecolor="#00000055"))
        if last is not None:
            ax.add_patch(Circle((last[1], last[0]), 0.30, facecolor="none",
                                edgecolor=LAST_MOVE, lw=1.8, zorder=8))

        ax.set_xlim(-1, BOARD_SIZE)
        ax.set_ylim(BOARD_SIZE, -1)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        for spine in ax.spines.values():
            spine.set_color(CARD_BORDER)

    def _draw_note(self):
        ax = self.note_ax
        ax.clear()
        ax.set_facecolor(CARD)
        ax.set_xlim(0, NOTE_W)
        ax.set_ylim(NOTE_H, 0)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color(CARD_BORDER)

        _text(ax, 3, 3.6, f"{STONE_NAME[self.to_play]} to play", size=10,
              weight="bold", color=ACCENT)
        result = self.result
        if result and result["move"]:
            _text(ax, 97, 3.6,
                  f"it plays {result['move']}  ·  depth {result['depth']}  ·  "
                  f"{_ms(result['seconds'])}", size=8, color=TEXT_MUTE,
                  ha="right")
        elif self.stones():
            _text(ax, 97, 3.6, "press T to make it think", size=8,
                  color=TEXT_MUTE, ha="right")
        ax.plot([3, 97], [5.8, 5.8], color=RULE, lw=0.8)

        y = 8.6
        for entry in self.chapter.note():
            if isinstance(entry, tuple):
                swatch, body = entry
                ax.add_patch(Rectangle((3, y - 1.1), 2.2, 2.2,
                                       facecolor=swatch, edgecolor="none"))
                y = _paragraph(ax, 7.5, y, body, 68, size=7.4,
                               color=TEXT_MAIN, step=3.0, limit=2) + 1.2
            else:
                y = _paragraph(ax, 3, y, entry, 72, size=7.4, color=TEXT_MUTE,
                               step=3.0, limit=3) + 1.2

    def _draw_panel(self):
        ax = self.panel_ax
        ax.clear()
        ax.set_facecolor(BG)
        ax.set_xlim(0, PANEL_W)
        ax.set_ylim(PANEL_H, 0)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        self.hotspots = []

        chapter = self.chapter
        _text(ax, 0, 2.6, chapter.heading, size=15, weight="bold")
        _paragraph(ax, 0, 6.6, chapter.subtitle, 132, size=8.2, step=2.5,
                   limit=2)
        ax.plot([0, PANEL_W], [9.8, 9.8], color=RULE, lw=1.0, zorder=1)
        chapter.ensure()
        chapter.draw(ax)

    def hot(self, x, y, w, h, key):
        """Register a clickable rectangle of the panel, in panel units."""
        self.hotspots.append((x, x + w, y, y + h, key))


# ---------- chapters ----------


class Chapter:
    """One view of the shared position."""

    label = ""
    heading = ""
    subtitle = ""

    def __init__(self, studio):
        self.studio = studio
        self.stamp = None

    def ensure(self):
        if self.stamp != self.studio.stamp:
            self.stamp = self.studio.stamp
            self.reset()

    def reset(self):
        """Forget everything measured about the previous position."""

    def board_state(self):
        """(grid, last move) the goban should show for this chapter."""
        return self.studio.game.board.grid, None

    def overlay(self, ax, grid):
        """Anything this chapter draws on the goban, under the stones."""

    def note(self):
        """Lines for the card under the goban: strings, or (colour, string)."""
        return []

    def draw(self, ax):
        """Paint the panel."""

    def click(self, key):
        """A registered hotspot was clicked; return True to redraw."""
        return False

    def board_click(self, cell, event):
        """A goban cell was clicked. True means handled, so no stone moves."""
        return False

    def key(self, name):
        return False

    # -- shared bits --

    def _mark(self, ax, r, c, body, edge, fill="none", size=6.0, alpha=1.0,
              z=4, lw=1.5):
        ax.add_patch(Circle((c, r), 0.40, facecolor=fill, edgecolor=edge,
                            lw=lw, alpha=alpha, zorder=z))
        if body:
            ax.text(c, r, body, ha="center", va="center", fontsize=size,
                    color=TEXT_MAIN, fontweight="bold", zorder=z + 1)

    def _empty(self, ax, message):
        _text(ax, PANEL_W / 2, PANEL_H / 2, message, size=11, color=TEXT_MUTE,
              ha="center")


class Candidates(Chapter):
    """361 intersections down to one move, and what each stage costs."""

    label = "1 Candidates"
    heading = "From 361 intersections to one move"
    subtitle = ("the highlighted stage is shown on the goban  ·  click any "
                "stage, or use up and down, to move to it")

    STAGES = 6

    def __init__(self, studio):
        super().__init__(studio)
        self.stage = 1
        self.data = None
        self.chosen = None

    def reset(self):
        self.data = None

    def ensure(self):
        super().ensure()
        result = self.studio.result
        chosen = result["move"] if result else None
        # The last stage is the move the search came back with, so the funnel
        # is stale as soon as the engine has thought about this position.
        if self.data is None or chosen != self.chosen:
            if not self.studio.stones():
                return
            self.chosen = chosen
            self.data = measure.funnel(self.studio.position(), chosen)

    # -- goban --

    def overlay(self, ax, grid):
        if not self.data:
            return
        stage = self.data["stages"][self.stage]
        key = stage["key"]
        if key == "board":
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    if grid[r][c] == EMPTY:
                        ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1,
                                               facecolor=ACCENT, alpha=0.10,
                                               edgecolor="none", zorder=2))
        elif key == "windows":
            for r0, c0, r1, c1 in self.data["windows"]:
                ax.add_patch(Rectangle(
                    (c0 - 0.5, r0 - 0.5), c1 - c0 + 1, r1 - r0 + 1,
                    facecolor=ACCENT, alpha=0.14, edgecolor=ACCENT, lw=1.6,
                    linestyle=(0, (5, 3)), zorder=2))
        elif key == "reach":
            crowding = self.data["crowding"]
            peak = max((max(row) for row in crowding), default=1) or 1
            for r, c in stage["cells"]:
                ax.add_patch(Rectangle(
                    (c - 0.5, r - 0.5), 1, 1, zorder=2, edgecolor="none",
                    facecolor=ACCENT,
                    alpha=0.10 + 0.55 * crowding[r][c] / peak))
        elif key == "shortlist":
            promoted = set(self.data["promoted"])
            for rank, (r, c) in enumerate(stage["cells"], start=1):
                lifted = (r, c) in promoted
                self._mark(ax, r, c, str(rank), WARM if lifted else ACCENT,
                           lw=2.4 if lifted else 1.5)
        elif key == "ranked":
            for rank, (r, c) in enumerate(stage["cells"], start=1):
                self._mark(ax, r, c, str(rank), ACCENT,
                           fill=ACCENT if rank == 1 else "none",
                           alpha=0.5 if rank == 1 else 1.0)
        elif key == "chosen":
            for rank, (r, c) in enumerate(self.data["stages"][4]["cells"], 1):
                self._mark(ax, r, c, str(rank), GREY, alpha=0.45, lw=1.0)
            for r, c in stage["cells"]:
                self._mark(ax, r, c, "", SUCCESS, lw=2.8, z=7)

    def note(self):
        if not self.data:
            return ["Put some stones on the board."]
        stage = self.data["stages"][self.stage]
        lines = [f"Stage {self.stage + 1} of {self.STAGES} on the goban: "
                 f"{stage['title']}, {_plural(stage['count'], 'cell')}."]
        if any(wins for _, _, _, wins, _ in self.data["ranked"]):
            lines.append((SUCCESS, "one candidate wins outright, so the "
                                   "ranking stopped there: nothing else was "
                                   "worth scoring"))
        elif self.data["forced"]:
            lines.append((DANGER, "the opponent has a move that ends the "
                                  "game, so every candidate that does not "
                                  "answer it was dropped"))
        if stage["key"] == "shortlist":
            promoted = self.data["promoted"]
            lines.append((WARM,
                          f"pulled back in by the tactical promotion: "
                          f"{', '.join(str(cell) for cell in promoted)}"
                          if promoted else
                          "nothing needed the tactical promotion here -- "
                          "crowding already had every dangerous cell"))
        elif stage["key"] == "ranked":
            lines.append((ACCENT, "numbered by the score read back after "
                                  "really playing each one"))
        elif stage["key"] == "chosen":
            lines.append((SUCCESS, "green is the move the search settled on, "
                                   "grey is what it chose between"))
        elif stage["key"] == "reach":
            lines.append((ACCENT, "the darker the cell, the more stones are "
                                  "within two steps of it"))
        return lines

    # -- panel --

    def draw(self, ax):
        if not self.data:
            self._empty(ax, "Put some stones on the board.")
            return
        stages = self.data["stages"]
        y = 11.0
        for index in range(self.STAGES):
            if index == self.stage:
                y = self._focus(ax, y, index, stages)
            else:
                y = self._collapsed(ax, y, index, stages[index])
            y += 1.4

        _text(
            ax, 0, min(y + 1.2, 71.0),
            f"stage 5 is the expensive one -- {_ms(self.data['per_candidate'])} "
            f"a candidate -- so stages 1-4 exist only to shrink what it sees",
            size=8.4, weight="bold", color=TEXT_MUTE)

    def _collapsed(self, ax, y, index, stage):
        height = 5.4
        _card(ax, 0, y, PANEL_W, height, face=BG, edge=RULE, lw=0.8)
        self.studio.hot(0, y, PANEL_W, height, index)
        middle = y + height / 2
        _text(ax, 1.5, middle, f"stage {index + 1}", size=7.2,
              color=TEXT_MUTE)
        _text(ax, 15.0, middle, stage["title"], size=9.0, color=TEXT_MAIN)
        _text(ax, PANEL_W - 1.5, middle, str(stage["count"]), size=10,
              weight="bold", color=TEXT_MUTE, ha="right")
        return y + height

    def _focus(self, ax, y, index, stages):
        stage = stages[index]
        height = 18.4
        _card(ax, 0, y, PANEL_W, height, face=CARD, edge=ACCENT, lw=2.0)
        self.studio.hot(0, y, PANEL_W, height, index)

        _text(ax, 1.5, y + 3.0, f"stage {index + 1} of {self.STAGES}",
              size=7.6, weight="bold", color=ACCENT)
        _text(ax, 1.5, y + 7.2, stage["title"], size=13.5, weight="bold")
        _paragraph(ax, 1.5, y + 11.0, stage["rule"], 80, size=8.2, step=2.6,
                   limit=2)

        _text(ax, PANEL_W - 1.5, y + 5.6, str(stage["count"]), size=21,
              weight="bold", color=ACCENT, ha="right")
        if index > 0:
            _text(ax, PANEL_W - 1.5, y + 10.0, f"of {stages[index - 1]['count']}",
                  size=8.0, color=TEXT_MUTE, ha="right")
        if stage["seconds"] is not None:
            _text(ax, PANEL_W - 1.5, y + 14.4, _ms(stage["seconds"]),
                  size=8.6, weight="bold", color=WARM, ha="right")
        return y + height

    def click(self, key):
        if isinstance(key, int) and 0 <= key < self.STAGES:
            self.stage = key
            return True
        return False

    def key(self, name):
        if name in ("up", "down"):
            step = -1 if name == "up" else 1
            self.stage = (self.stage + step) % self.STAGES
            return True
        return False


class AlphaBeta(Chapter):
    """One node of the recorded tree: its replies, ranked, searched or cut."""

    label = "2 Alpha-beta"
    heading = "Why it plays what it plays"
    subtitle = ("click a numbered reply -- on the goban or in the list -- to "
                "see what happens after it  ·  shift-click to place a stone "
                "instead")

    TOP, BOTTOM = 30.0, 63.0
    BAR_LEFT, BAR_RIGHT = 44.0, 87.0

    def __init__(self, studio):
        super().__init__(studio)
        self.depth = 6
        self.root = None
        self.path = []

    def reset(self):
        self.root = None
        self.path = []

    def ensure(self):
        super().ensure()
        if self.root is None and self.studio.stones():
            self.root = self.studio.working(
                f"recording the tree at depth {self.depth}...",
                lambda: measure.record_tree(self.studio.position(),
                                            self.depth))
            self.path = []

    def _chain(self):
        return [self.root] + [item["node"] for item in self.path]

    def _node(self):
        return self._chain()[-1]

    def _mover(self):
        """Whoever is to move at the node currently on screen."""
        if not self.path:
            return self.studio.to_play
        nodes = [item["node"] for item in self.path]
        return measure.replay(self.studio.position(), nodes).current

    def _ranked(self, node):
        """This node's replies, strongest first for the player moving here.

        A cut move was never scored, so it has no place of its own in that
        order; the cut moves keep the tail exactly as the search generated
        them, after every reply that was actually searched.
        """
        searched = [item for item in node["moves"] if item["searched"]]
        cut = [item for item in node["moves"] if not item["searched"]]
        searched.sort(key=lambda item: item["node"]["value"], reverse=True)
        return searched + cut

    def _colour(self, item, rank):
        if not item["searched"]:
            return GREY
        child = item["node"]
        if child["wins"]:
            return SUCCESS
        if child["loses"]:
            return DANGER
        return SUCCESS if rank == 1 else ACCENT

    # -- goban --

    def board_state(self):
        if not self.root or not self.path:
            return self.studio.game.board.grid, None
        nodes = [item["node"] for item in self.path]
        state = measure.replay(self.studio.position(), nodes)
        return state.board.grid, nodes[-1]["move"]

    def overlay(self, ax, grid):
        if not self.root:
            return
        node = self._node()
        for rank, item in enumerate(self._ranked(node), start=1):
            r, c = item["move"]
            if grid[r][c] != EMPTY:
                continue
            self._mark(ax, r, c, str(rank), self._colour(item, rank),
                       alpha=1.0 if item["searched"] else 0.5,
                       lw=2.2 if rank == 1 else 1.4)

    def board_click(self, cell, event):
        if not self.root or event.key == "shift":
            return False
        for item in self._node()["moves"]:
            if (item["move"] == cell and item["searched"]
                    and item["node"]["children"]):
                self.path = self.path + [item]
                return True
        return True  # swallow the click instead of moving a stone

    def note(self):
        if not self.root:
            return ["Put some stones on the board."]
        node = self._node()
        first = ("The goban is the position as it stands." if not self.path
                 else "The goban is the position after the replies chosen "
                      "so far; the red ring marks the last one played.")
        lines = [first,
                 (ACCENT, _plural(len(node["moves"]) - node["pruned"], "move")
                          + " searched here")]
        if node["pruned"]:
            lines.append((GREY, _plural(node["pruned"], "move")
                                + " generated and skipped"))
        return lines

    # -- panel --

    def draw(self, ax):
        if not self.root:
            self._empty(ax, "Put some stones on the board.")
            return
        node = self._node()
        self._header(ax, node)
        self._controls(ax)
        self._moves(ax, node)
        self._verdict(ax, node)

    def _header(self, ax, node):
        mover = STONE_NAME[self._mover()]
        title = ("root -- the position as it stands" if not self.path else
                 "after " + " → ".join(str(item["move"])
                                       for item in self.path))
        _card(ax, 0, 11.0, PANEL_W, 9.4, face=CARD, edge=CARD_BORDER)
        _text(ax, 1.5, 14.0, title, size=9.8, weight="bold")
        _text(ax, 1.5, 17.8, f"{mover} to move here  ·  searched {self.depth} "
                            f"plies deep", size=7.8, color=TEXT_MUTE)

        ranked = self._ranked(node)
        best = next((item for item in ranked if item["searched"]), None)
        if best is not None:
            value = best["node"]["value"]
            _text(ax, PANEL_W - 1.5, 14.0, _outcome(value), size=15,
                  weight="bold", ha="right",
                  color=SUCCESS if value >= 0 else DANGER)
            _text(ax, PANEL_W - 1.5, 17.8, f"best reply: {best['move']}",
                  size=7.8, color=TEXT_MUTE, ha="right")
        else:
            _text(ax, PANEL_W - 1.5, 15.4, "a leaf -- scored, not searched",
                  size=8.4, color=TEXT_MUTE, ha="right")

    def _controls(self, ax):
        y = 21.6
        for body, key, x in (("–", "shallower", 0.0), ("+", "deeper", 7.0)):
            _card(ax, x, y, 4.6, 4.8, face=SOFT, edge=CARD_BORDER)
            _text(ax, x + 2.3, y + 2.4, body, size=11, weight="bold",
                  ha="center")
            self.studio.hot(x, y, 4.6, 4.8, key)
        _text(ax, 15.0, y + 2.4, f"search depth {self.depth}", size=7.8,
              color=TEXT_MUTE)
        if self.path:
            _card(ax, 86, y, 14, 4.8, face=SOFT, edge=ACCENT, lw=1.1)
            _text(ax, 93, y + 2.4, "◂ back", size=8.2, ha="center",
                  color=ACCENT)
            self.studio.hot(86, y, 14, 4.8, "back")

    def _moves(self, ax, node):
        ranked = self._ranked(node)
        if not ranked:
            return
        room = self.BOTTOM - self.TOP
        height = max(min(4.6, room / len(ranked)), 2.8)
        fits = max(1, int(room / height))

        values = [item["node"]["value"] for item in ranked
                 if item["searched"]]
        lo, hi = (min(values), max(values)) if values else (0, 1)
        span = (hi - lo) or 1

        _text(ax, 0, self.TOP - 2.4,
              f"longer bar = stronger for {STONE_NAME[self._mover()]}  ·  "
              "green is the reply it plays",
              size=7.4, color=TEXT_MUTE)

        for order, item in enumerate(ranked[:fits]):
            y = self.TOP + order * height
            rank = order + 1
            searched = item["searched"]
            colour = self._colour(item, rank)
            _card(ax, 0, y, PANEL_W, height - 0.6,
                  face=CARD if searched else BG,
                  edge=CARD_BORDER if searched else RULE, lw=0.8)
            middle = y + (height - 0.6) / 2
            _text(ax, 1.5, middle, str(rank), size=7.2, color=TEXT_MUTE)
            _text(ax, 6.0, middle, f"{item['move']}", size=8.6,
                  weight="bold" if rank == 1 else "normal",
                  color=TEXT_MAIN if searched else GREY)

            if searched:
                value = item["node"]["value"]
                frac = max(0.05, (value - lo) / span)
                width = (self.BAR_RIGHT - self.BAR_LEFT) * frac
                ax.add_patch(Rectangle((self.BAR_LEFT, y + 0.5), width,
                                       height - 1.6, facecolor=colour,
                                       edgecolor="none", zorder=3))
                _text(ax, self.BAR_RIGHT + 1.5, middle, _outcome(value),
                      size=7.6, ha="left", color=TEXT_MAIN)
                tag = self._tag(item)
                if tag:
                    _text(ax, self.BAR_LEFT - 1.0, middle, tag, size=7.0,
                          color=colour, ha="right", weight="bold")
                if item["node"]["children"]:
                    self.studio.hot(0, y, PANEL_W, height - 0.6,
                                    ("open", item["move"]))
            else:
                _text(ax, self.BAR_LEFT, middle, "generated, never searched",
                      size=7.4, color=GREY, style="italic")

        if len(ranked) > fits:
            _text(ax, 0, self.TOP + fits * height + 1.6,
                  f"...and {len(ranked) - fits} more, all cut", size=7.2,
                  color=TEXT_MUTE)

    def _tag(self, item):
        child = item["node"]
        if child["wins"]:
            return "wins"
        if child["loses"]:
            return "loses"
        return ""

    def _verdict(self, ax, node):
        y = 65.6
        _card(ax, 0, y, PANEL_W, 9.2, face=CARD, edge=CARD_BORDER)
        window = node["window"]
        if node["pruned"] and node["children"]:
            last = node["children"][-1]
            tail = (f"so the {_plural(node['pruned'], 'move left')} could "
                    f"not change what happens one ply up, and were never "
                    f"searched.")
            if abs(last["value"]) >= MATE_FLOOR:
                body = (f"Stopped early: {last['move']} already "
                        f"{_outcome(last['value'])} -- {tail}")
            else:
                body = (f"Stopped early: {last['move']} already scores "
                        f"{_spaced(last['value'])}, past β "
                        f"({_bound(window[1])}) -- {tail}")
        elif window is None:
            body = ("A leaf: the last ply, so this position is scored as it "
                    "stands instead of being searched further.")
        else:
            body = ("Nothing to cut: every move here either beat the one "
                    "before it or stayed under β, so all of them had to be "
                    "searched.")
        _paragraph(ax, 2, y + 3.4, body, 128, size=8.6, step=2.9, limit=3,
                   color=TEXT_MAIN)

    def click(self, key):
        if key == "back":
            if self.path:
                self.path.pop()
            return True
        if key in ("deeper", "shallower"):
            self.depth = max(2, min(10, self.depth
                                    + (2 if key == "deeper" else -2)))
            self.root = None
            self.ensure()
            return True
        if isinstance(key, tuple) and key[0] == "open":
            move = key[1]
            for item in self._node()["moves"]:
                if item["move"] == move and item["searched"]:
                    self.path = self.path + [item]
                    return True
        return False

    def key(self, name):
        if name in ("backspace", "up") and self.path:
            self.path.pop()
            return True
        return False


class Deepening(Chapter):
    """Depth 2, then 4, then 6... against half a second of clock."""

    label = "3 Deepening"
    heading = "Deeper until the clock says stop"
    subtitle = ("press space, or click below, to complete one more depth  ·  "
                "the answer played is the last one that finished")

    TOP, HEIGHT = 32.8, 4.6

    def __init__(self, studio):
        super().__init__(studio)
        self.rows = []
        self.steps = None
        self.done = False

    def reset(self):
        self._close()
        self.rows = []
        self.done = False

    def _close(self):
        if self.steps is not None:
            self.steps.close()
            self.steps = None

    def _step(self):
        if self.done or not self.studio.stones():
            return
        if self.steps is None:
            self.steps = measure.deepening_steps(self.studio.position(),
                                                 self.studio.budget)
        try:
            self.rows.append(next(self.steps))
        except StopIteration:
            self.done = True
            self._close()
            return
        if self.rows[-1]["cut"]:
            self.done = True
            self._close()

    def _run(self):
        while not self.done and len(self.rows) < 8:
            self._step()

    # -- goban --

    def overlay(self, ax, grid):
        best = None
        chosen = {}
        for row in self.rows:
            if row["move"]:
                best = row["move"]
                chosen.setdefault(row["move"], []).append(row["depth"])
        for move, depths in chosen.items():
            r, c = move
            latest = move == best
            self._mark(ax, r, c, ",".join(str(d) for d in depths),
                       SUCCESS if latest else GREY,
                       fill=SUCCESS if latest else "none",
                       alpha=0.35 if latest else 0.8,
                       lw=2.4 if latest else 1.2, size=5.2)

    def note(self):
        if not self.rows:
            return ["Press space, or click “Step one depth”, to complete the "
                    "first iteration."]
        changes = sum(1 for a, b in zip(self.rows, self.rows[1:])
                      if a["move"] and b["move"] and a["move"] != b["move"])
        return [
            "Each ring is a depth's answer; the number inside says which "
            "depth chose it.",
            (SUCCESS, "green is the answer as it stands"),
            f"It changed its mind {_plural(changes, 'time')} on the way "
            f"down, which is the entire reason for searching deeper.",
        ]

    # -- panel --

    def draw(self, ax):
        if not self.studio.stones():
            self._empty(ax, "Put some stones on the board.")
            return
        self._buttons(ax)
        self._clock(ax)
        self._table(ax)

    def _buttons(self, ax):
        kept = [row for row in self.rows if not row["cut"]]
        if kept:
            last = kept[-1]
            _text(ax, 0, 13.2, f"plays {last['move']}", size=13,
                  weight="bold", color=SUCCESS)
            _text(ax, 0, 17.2,
                  f"depth {last['depth']}  ·  {_outcome(last['value'])}",
                  size=8.0, color=TEXT_MUTE)
        else:
            _text(ax, 0, 14.6, "not searched yet", size=9.5, color=TEXT_MUTE)

        for body, key, x in (("Step one depth", "step", 58.0),
                             ("Run to the end", "run", 79.0)):
            _card(ax, x, 11.0, 19.0, 5.2, face=CARD, edge=ACCENT, lw=1.3)
            _text(ax, x + 9.5, 13.6, body, size=8.5, weight="bold",
                  ha="center", color=ACCENT)
            self.studio.hot(x, 11.0, 19.0, 5.2, key)

    def _clock(self, ax):
        budget = self.studio.budget
        top, height = 21.5, 5.4
        label = (f"the {budget:.2f} s budget, filled in by the depths that "
                f"finished")
        if self.done:
            label += "  --  fully spent"
        _text(ax, 0, 19.4, label, size=8.6, weight="bold")
        _card(ax, 0, top, PANEL_W, height, face=SOFT, edge=CARD_BORDER)

        spent = 0.0
        for index, row in enumerate(self.rows):
            if row["seconds"] is None:
                continue
            x0 = PANEL_W * min(spent / budget, 1.0)
            spent += row["seconds"]
            x1 = PANEL_W * min(spent / budget, 1.0)
            ax.add_patch(Rectangle((x0, top), max(x1 - x0, 0.25), height,
                                   facecolor=ACCENT if index % 2 else "#6F9CBD",
                                   edgecolor=CARD, lw=0.6, zorder=3))
            if x1 - x0 > 4:
                _text(ax, (x0 + x1) / 2, top + height / 2, str(row["depth"]),
                      size=8, color=CARD, weight="bold", ha="center")
        if self.rows and self.rows[-1]["cut"]:
            left = PANEL_W * min(spent / budget, 1.0)
            ax.add_patch(Rectangle((left, top), max(PANEL_W - left, 0.5),
                                   height, facecolor=DANGER, alpha=0.28,
                                   edgecolor=DANGER, hatch="//", zorder=3))
            if PANEL_W - left > 20:
                _text(ax, (left + PANEL_W) / 2, top + height / 2,
                      f"depth {self.rows[-1]['depth']} started here and was "
                      f"abandoned", size=7.6, color=DANGER, weight="bold",
                      ha="center", z=6)
        _text(ax, 0, top + height + 1.6, "0 s", size=7, color=TEXT_MUTE)
        _text(ax, PANEL_W, top + height + 1.6, f"{budget:.2f} s", size=7,
              color=TEXT_MUTE, ha="right")

    def _table(self, ax):
        top, height = self.TOP, self.HEIGHT
        for x, name, right in ((1, "depth", False), (13, "time", False),
                               (29, "nodes", False), (52, "best move", False),
                               (PANEL_W - 1, "value", True)):
            _text(ax, x, top - 1.9, name, size=7.4, color=TEXT_MUTE,
                  ha="right" if right else "left")
        ax.plot([0, PANEL_W], [top - 0.6, top - 0.6], color=RULE, lw=0.8)

        if not self.rows:
            _text(ax, 0, top + 3.6,
                  "Nothing searched yet.", size=9, color=TEXT_MUTE)
            return

        peak = max((row["nodes"] or 0) for row in self.rows) or 1
        previous = None
        for index, row in enumerate(self.rows):
            y = top + index * height
            if row["cut"]:
                _card(ax, 0, y, PANEL_W, height - 0.6, face="#FBEAE7",
                      edge=DANGER, lw=0.9)
                _text(ax, 1, y + 2.1, str(row["depth"]), size=9,
                      color=DANGER, weight="bold")
                _paragraph(ax, 13, y + 2.1,
                           "the clock ran out inside this depth -- the partial "
                           "answer is thrown away and the previous one played",
                           120, size=7.6, color=DANGER, limit=1)
                continue
            changed = previous is not None and row["move"] != previous
            _card(ax, 0, y, PANEL_W, height - 0.6, face=CARD,
                  edge=ACCENT if changed else CARD_BORDER,
                  lw=1.4 if changed else 0.8)
            _text(ax, 1, y + 2.1, str(row["depth"]), size=9.4, weight="bold")
            _text(ax, 13, y + 2.1, _ms(row["seconds"]), size=8.0)
            ax.add_patch(Rectangle((29, y + 1.2), max(17.0 * row["nodes"]
                                                      / peak, 0.3), 1.8,
                                   facecolor=PALE, edgecolor="none", zorder=3))
            _text(ax, 50, y + 2.1, _spaced(row["nodes"]), size=7.8, ha="right")
            _text(ax, 52, y + 2.1, f"{row['move']}", size=8.4,
                  weight="bold" if changed else "normal")
            if changed:
                _text(ax, 66, y + 2.1, "changed its mind", size=7.2,
                      color=ACCENT)
            _text(ax, PANEL_W - 1, y + 2.1, _outcome(row["value"]), size=7.8,
                  ha="right")
            previous = row["move"]

        kept = [row for row in self.rows if not row["cut"]]
        if kept:
            _paragraph(
                ax, 0, min(top + len(self.rows) * height + 2.4, 64.0),
                f"It plays {kept[-1]['move']}, the answer of depth "
                f"{kept[-1]['depth']} -- the last iteration that finished. "
                f"Every iteration re-searches the whole tree, which sounds "
                f"wasteful and is not: the shallow pass leaves the good moves "
                f"first in the transposition table, and alpha-beta on a well "
                f"ordered tree saves far more than the pass cost.",
                134, size=8.0, step=2.5, limit=4, color=TEXT_MAIN)

    def click(self, key):
        if key == "step":
            self.studio.working("searching one more depth...", self._step)
            return True
        if key == "run":
            self.studio.working("searching to the end of the budget...",
                                self._run)
            return True
        return False

    def key(self, name):
        if name == " ":
            self.studio.working("searching one more depth...", self._step)
            return True
        if name == "enter":
            self.studio.working("searching to the end of the budget...",
                                self._run)
            return True
        return False


class Optimisations(Chapter):
    """The same search on this position, with one thing switched off."""

    label = "4 Optimisations"
    heading = "What each optimisation is worth"
    subtitle = ("click a row to re-run this position with that one switched "
                "off  ·  the engine is never told it is being measured")

    DEPTH = 8
    PRUNING_DEPTH = 6
    # The ratio axis is logarithmic and labelled, because these numbers span
    # two orders of magnitude: drawn linearly, every bar under 2x would be a
    # smear against the edge and a 0.5x would look much like a 1x.
    LOW, HIGH, LEFT, RIGHT = 0.5, 32.0, 52.0, 97.0
    TOP, HEIGHT = 28.5, 4.6

    def __init__(self, studio):
        super().__init__(studio)
        self.baseline = None
        self.measured = {}

    def reset(self):
        self.baseline = None
        self.measured = {}

    def _rows(self):
        return [("pruning", "Alpha-beta pruning itself",
                 "every move of every node searched to the end")] + [
            (key, name, detail)
            for key, name, detail, _ in measure.ABLATION_CASES]

    def _measure(self, key):
        game = self.studio.position()
        if self.baseline is None:
            self.baseline = self.studio.working(
                "measuring the engine as it stands...",
                lambda: measure.baseline_search(game, self.DEPTH))
        if key == "pruning":
            data = self.studio.working(
                "searching the same tree with no pruning at all...",
                lambda: measure.pruning_comparison(game, self.PRUNING_DEPTH))
            self.measured[key] = {
                "seconds": data["full_seconds"], "nodes": data["full"],
                "cost": (data["full_seconds"] / data["pruned_seconds"]
                         if data["pruned_seconds"] else 0.0),
                "against": data["pruned_seconds"], "depth": data["depth"],
            }
            return
        data = self.studio.working(
            "re-running the same search without it...",
            lambda: measure.ablate(game, key, self.DEPTH))
        base = self.baseline["seconds"]
        self.measured[key] = {
            "seconds": data["seconds"], "nodes": data["nodes"],
            "cost": data["seconds"] / base if base else 0.0,
            "against": base, "depth": self.DEPTH,
        }

    def overlay(self, ax, grid):
        windows = measure.search_space.search_windows(
            self.studio.game.board)
        for window in windows:
            ax.add_patch(Rectangle(
                (window.c0 - 0.5, window.r0 - 0.5),
                window.c1 - window.c0 + 1, window.r1 - window.r0 + 1,
                facecolor=ACCENT, alpha=0.10, edgecolor=ACCENT, lw=1.2,
                linestyle=(0, (5, 3)), zorder=2))

    def note(self):
        if not self.studio.stones():
            return ["Put some stones on the board."]
        return [
            (ACCENT, "the dashed windows are what every one of these searches "
                     "is confined to"),
            f"Every row re-runs a fixed {self.DEPTH}-ply search from the "
            f"position on the left, so both sides do the same amount of "
            f"thinking and only the machinery differs.",
            "Change the position and the numbers change with it: a quiet "
            "board and a sharp one do not stress the same parts.",
        ]

    # -- panel --

    def _at(self, ratio):
        ratio = max(self.LOW, min(self.HIGH, ratio))
        span = math.log2(self.HIGH) - math.log2(self.LOW)
        return self.LEFT + (self.RIGHT - self.LEFT) * (
            math.log2(ratio) - math.log2(self.LOW)) / span

    def draw(self, ax):
        if not self.studio.stones():
            self._empty(ax, "Put some stones on the board.")
            return
        rows = self._rows()
        bottom = self.TOP + len(rows) * self.HEIGHT

        _card(ax, 0, 11.0, 60, 9.0, face=CARD, edge=CARD_BORDER)
        if self.baseline:
            _text(ax, 1.5, 15.2, _ms(self.baseline["seconds"]), size=17,
                  weight="bold", color=ACCENT)
            _text(ax, 1.5, 19.0,
                  f"as it stands, depth {self.DEPTH}  ·  "
                  f"{_spaced(self.baseline['nodes'])} nodes", size=7.8,
                  color=TEXT_MUTE)
        else:
            _text(ax, 1.5, 15.5, "nothing measured yet", size=9.5,
                  color=TEXT_MUTE)
        _card(ax, 62, 11.0, 36, 9.0, face=CARD, edge=ACCENT, lw=1.3)
        _text(ax, 80, 15.5, "measure every row", size=8.8, weight="bold",
              ha="center", color=ACCENT)
        self.studio.hot(62, 11.0, 36, 9.0, "all")

        self._scale(ax, bottom)
        for index, (key, name, detail) in enumerate(rows):
            y = self.TOP + index * self.HEIGHT
            done = self.measured.get(key)
            _card(ax, 0, y, PANEL_W, self.HEIGHT - 0.7,
                  face=CARD if done else BG,
                  edge=CARD_BORDER if done else RULE, z=4)
            self.studio.hot(0, y, PANEL_W, self.HEIGHT - 0.7, key)
            _text(ax, 1.5, y + 1.4, name, size=8.6, weight="bold",
                  color=TEXT_MAIN if done else TEXT_MUTE, z=6)
            _paragraph(ax, 1.5, y + 3.1, f"off: {detail}", 74, size=7.0,
                       limit=1, z=6)
            if done:
                self._bar(ax, y, done)
            else:
                _text(ax, self.LEFT, y + 2.0, "click to measure", size=7.4,
                      color=ACCENT, style="italic", z=6)

        _paragraph(
            ax, 0, bottom + 2.4,
            "A bar under 1x is real, not a mistake: some of these rows pay "
            "for correctness, not speed, and only show their worth in games "
            "won -- not in the time this one search takes.",
            134, size=8.4, step=2.7, limit=2)

    def _scale(self, ax, bottom):
        _text(ax, self.LEFT, 23.0,
              "how long the same search takes without it", size=7.4,
              color=TEXT_MUTE)
        for tick in (0.5, 1, 2, 4, 8, 16, 32):
            x = self._at(tick)
            ax.plot([x, x], [26.4, bottom], color=RULE, lw=0.7, zorder=1,
                    linestyle=(0, (2, 3)))
            _text(ax, x, 25.2, f"{tick:g}x", size=6.6, color=TEXT_MUTE,
                  ha="center")
        one = self._at(1.0)
        ax.plot([one, one], [26.4, bottom], color=TEXT_MUTE, lw=1.1, zorder=3)

    def _bar(self, ax, y, done):
        one, end = self._at(1.0), self._at(done["cost"])
        slower = done["cost"] >= 1.0
        ax.add_patch(Rectangle((min(one, end), y + 0.9),
                               max(abs(end - one), 0.3), 1.9, zorder=6,
                               facecolor=DANGER if slower else SUCCESS,
                               edgecolor="none"))
        if done["cost"] > self.HIGH:
            # Off the end of the scale: the label goes inside the bar rather
            # than past the edge of the panel.
            _text(ax, self.RIGHT - 1.0, y + 1.85, f"{done['cost']:.0f}x  ▸",
                  size=8, weight="bold", z=7, ha="right", color=CARD)
        else:
            _text(ax, end + (1.0 if slower else -1.0), y + 1.85,
                  f"{done['cost']:.2f}x", size=8, weight="bold", z=6,
                  ha="left" if slower else "right",
                  color=DANGER if slower else SUCCESS)
        _text(ax, self.RIGHT, y + 3.3,
              f"{_ms(done['seconds'])}, {_spaced(done['nodes'])} nodes, "
              f"against {_ms(done['against'])} at depth {done['depth']}",
              size=6.6, color=TEXT_MUTE, ha="right", z=6)

    def click(self, key):
        if key == "all":
            for row_key, _, _ in self._rows():
                self._measure(row_key)
            return True
        if any(key == row[0] for row in self._rows()):
            self._measure(key)
            return True
        return False


class Evaluation(Chapter):
    """Where the number at the bottom of the tree comes from."""

    label = "5 Evaluation"
    heading = "What a position is worth"
    subtitle = ("click an empty intersection to score it  ·  shift-click to "
                "place a stone  ·  a move can only change the lines it sits "
                "on")

    AXES = {(0, 1): "row", (1, 0): "column", (1, 1): "↘ diagonal",
            (1, -1): "↗ diagonal"}
    TOP, HEIGHT = 24.0, 11.2

    def __init__(self, studio):
        super().__init__(studio)
        self.cell = None
        self.data = None

    def reset(self):
        self.data = None

    def ensure(self):
        super().ensure()
        if self.data is None and self.studio.stones():
            cell = self.cell
            if cell is None or self.studio.game.board.get(*cell) != EMPTY:
                result = self.studio.result
                cell = result["move"] if result and result["move"] else None
            if cell is None:
                ranked = measure.funnel(self.studio.position())["ranked"]
                cell = (ranked[0][1], ranked[0][2]) if ranked else None
            self.cell = cell
            self.data = self._look(cell) if cell else None

    def _look(self, cell):
        """Play the move on a search state and read the lines it moved."""
        r, c = cell
        state = SearchState(self.studio.position())
        color = state.current
        other = opponent(color)
        places = CELL_LINES[cell]
        before_text = {line_id: state.evaluator.text[line_id]
                       for line_id, _ in places}
        before = state.evaluate(color)

        captured = state.board.find_captures(r, c, color)
        move = state.play(r, c, captured)
        after = state.evaluate(color)
        after_text = {line_id: state.evaluator.text[line_id]
                      for line_id, _ in places}
        state.undo(move)

        rows = []
        for line_id, index in places:
            (r0, c0), (r1, c1) = LINES[line_id][0], LINES[line_id][1]
            old, new = before_text[line_id], after_text[line_id]
            rows.append({
                "name": self.AXES[(r1 - r0, c1 - c0)],
                "text": new, "index": index,
                "mine": (score_line(old, color), score_line(new, color)),
                "theirs": (score_line(old, other), score_line(new, other)),
                "shapes": [shape for shape in matched_shapes(new, color)
                           if shape[0] <= index + 1 < shape[0] + len(shape[1])],
            })
        return {
            "cell": cell, "color": color, "captured": captured,
            "before": before, "after": after, "rows": rows,
            "mine": sum(row["mine"][1] - row["mine"][0] for row in rows),
            "theirs": sum(row["theirs"][1] - row["theirs"][0] for row in rows),
        }

    # -- goban --

    def board_click(self, cell, event):
        if event.key == "shift" or self.studio.game.board.get(*cell) != EMPTY:
            return False
        self.cell = cell
        self.data = self._look(cell)
        return True

    def overlay(self, ax, grid):
        if not self.data:
            return
        for line_id, _ in CELL_LINES[self.data["cell"]]:
            for r, c in LINES[line_id]:
                ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, zorder=2,
                                       facecolor=ACCENT, alpha=0.12,
                                       edgecolor="none"))
        r, c = self.data["cell"]
        self._mark(ax, r, c, "", WARM, lw=2.6, z=7)

    def note(self):
        if not self.data:
            return ["Put some stones on the board."]
        return [
            f"Scoring {self.data['cell']} for "
            f"{STONE_NAME[self.data['color']]}. The shaded cells are the "
            f"lines through it -- the only ones the evaluator has to re-read.",
            (WARM, "click another empty intersection to score that one "
                   "instead"),
        ]

    # -- panel --

    def draw(self, ax):
        if not self.data:
            self._empty(ax, "Put some stones on the board.")
            return
        data = self.data
        name = STONE_NAME[data["color"]]

        _card(ax, 0, 11.0, PANEL_W, 10.0, face=CARD, edge=CARD_BORDER)
        _text(ax, 1.5, 14.2, f"{name} plays {data['cell']}", size=10,
              weight="bold")
        _text(ax, 1.5, 18.0,
              f"the whole position, scored for {name}:   "
              f"{_spaced(data['before'])}  →  {_spaced(data['after'])}",
              size=8.2, color=TEXT_MUTE)
        delta = data["after"] - data["before"]
        _text(ax, PANEL_W - 1.5, 14.2, _signed(delta), size=15, weight="bold",
              ha="right", color=SUCCESS if delta >= 0 else DANGER)
        _text(ax, PANEL_W - 1.5, 18.0,
              f"own shapes {_signed(data['mine'])}   −   theirs "
              f"{_signed(data['theirs'])} × {DEFENCE_WEIGHT}"
              + (f"   +   {len(data['captured'])} stones captured"
                 if data["captured"] else ""),
              size=7.4, color=TEXT_MUTE, ha="right")

        for index, row in enumerate(data["rows"]):
            self._line(ax, self.TOP + index * self.HEIGHT, row, data["color"])

        _paragraph(
            ax, 0, self.TOP + len(data["rows"]) * self.HEIGHT + 1.0,
            "That is the whole evaluation: add up every line the move "
            f"touches, and count the opponent's lines {DEFENCE_WEIGHT} times "
            "over, since losing ground costs more than gaining it pays.",
            134, size=8.4, step=2.7, limit=2)

    def _line(self, ax, y, row, color):
        _card(ax, 0, y, PANEL_W, self.HEIGHT - 1.0, face=CARD,
              edge=CARD_BORDER)
        _text(ax, 1.5, y + 3.2, row["name"], size=8.6, weight="bold")

        text, index = row["text"], row["index"] + 1
        span, size = 5, 3.4
        start = max(1, min(index - span, len(text) - 2 - 2 * span))
        left = 14.0
        for order, at in enumerate(range(start,
                                        min(start + 2 * span + 1,
                                            len(text) - 1))):
            x = left + order * size
            here = at == index
            _card(ax, x, y + 1.4, size - 0.4, size - 0.4, z=3,
                  face="#F6E3C4" if here else GOBAN,
                  edge=WARM if here else RULE, lw=1.8 if here else 0.6)
            glyph = text[at]
            if glyph in "BW":
                ax.add_patch(Circle((x + (size - 0.4) / 2,
                                     y + 1.4 + (size - 0.4) / 2),
                                    (size - 0.4) / 2 - 0.35, zorder=4, lw=0.5,
                                    facecolor=BLACK_STONE if glyph == "B"
                                    else WHITE_STONE, edgecolor="#00000055"))
        _text(ax, left, y + 6.4,
              "the line as the evaluator keeps it, with the move played",
              size=6.8, color=TEXT_MUTE)

        names = (STONE_NAME[color], STONE_NAME[opponent(color)])
        for order, (side, scores) in enumerate(
                zip(names, (row["mine"], row["theirs"]))):
            at = y + 3.2 + order * 3.2
            delta = scores[1] - scores[0]
            mine = order == 0
            _text(ax, 56, at, side, size=7.8,
                  color=TEXT_MAIN if delta else TEXT_MUTE)
            _text(ax, 65, at,
                  f"{_spaced(scores[0])}  →  {_spaced(scores[1])}", size=7.8,
                  color=TEXT_MAIN if delta else TEXT_MUTE)
            _text(ax, PANEL_W - 1.5, at, _signed(delta), size=8.6,
                  weight="bold" if delta else "normal", ha="right",
                  color=(SUCCESS if mine else DANGER) if delta else TEXT_MUTE)

        own, foe = STONE_NAME[color][0], STONE_NAME[opponent(color)][0]
        if row["shapes"]:
            body = "shapes through the new stone:   " + ",   ".join(
                f"{pattern.replace('X', own).replace('O', foe)} "
                f"{_signed(value)}" for _, pattern, value in row["shapes"])
        else:
            body = "no shape of the mover's own runs through the new stone"
        _paragraph(ax, 1.5, y + 9.0, body, 118, size=7.4, limit=1,
                   color=TEXT_MAIN)


def studio(budget=TIME_BUDGET):
    Studio(budget)
    plt.show()
