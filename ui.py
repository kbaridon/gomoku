"""Interactive Gomoku UI — pure matplotlib.

Layout (figure coords):

    +-----------------------------+-----------------+
    |                             |   GOMOKU        |
    |                             |  ┌───────────┐  |
    |                             |  │ status    │  |
    |                             |  └───────────┘  |
    |          BOARD              |  ┌───────────┐  |
    |                             |  │ Black     │  |
    |                             |  └───────────┘  |
    |                             |  ┌───────────┐  |
    |                             |  │ White     │  |
    |                             |  └───────────┘  |
    |                             |  ┌───────────┐  |
    |                             |  │ Timing    │  |
    |                             |  └───────────┘  |
    |                             | [Restart][Quit] |
    +-----------------------------+-----------------+
"""

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
from matplotlib.widgets import Button

from board import BLACK, BOARD_SIZE, EMPTY, STONE_NAME, WHITE


# --- Palette ---
BG             = "#F0E7D2"
GOBAN          = "#DEB887"
GRID           = "#3A2A18"
BLACK_STONE    = "#111111"
WHITE_STONE    = "#F8F8F8"
LAST_MOVE      = "#D64545"
CARD_BG        = "#FFFFFF"
CARD_BORDER    = "#B8A88A"
TEXT_MAIN      = "#2A2018"
TEXT_MUTE      = "#7A6E5C"
ACCENT         = "#4A7A9E"
DANGER         = "#C0392B"
SUCCESS        = "#2E7D5E"
WARNING_BG     = "#FFEACC"
WARNING_BORDER = "#E09040"
STATUS_BG      = "#FFF8E8"


class GomokuUI:
    def __init__(self, game):
        self.game = game

        self.fig = plt.figure(figsize=(14, 8.5), facecolor=BG)
        try:
            self.fig.canvas.manager.set_window_title("Gomoku")
        except Exception:
            pass

        self.board_ax = self.fig.add_axes([0.03, 0.06, 0.55, 0.90])
        self.info_ax = self.fig.add_axes([0.60, 0.14, 0.37, 0.82])
        self.reset_ax = self.fig.add_axes([0.60, 0.03, 0.17, 0.07])
        self.quit_ax = self.fig.add_axes([0.80, 0.03, 0.17, 0.07])

        self.reset_btn = Button(
            self.reset_ax, "Restart (R)",
            color="#EAD8B0", hovercolor="#D6C098",
        )
        self.quit_btn = Button(
            self.quit_ax, "Quit (Q)",
            color="#EABEB8", hovercolor="#D69C98",
        )
        self.reset_btn.on_clicked(lambda _e: self._reset())
        self.quit_btn.on_clicked(lambda _e: plt.close(self.fig))

        self._setup_board_ax()
        self._setup_info_ax()

        self._status_msg = ""
        self._status_kind = "info"

        self.fig.canvas.mpl_connect("button_press_event", self._on_click)
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)

        self._timer = self.fig.canvas.new_timer(interval=100)
        self._timer.add_callback(self._tick)
        self._timer.start()

        self._draw_all()

    # ---------- axes ----------

    def _setup_board_ax(self):
        ax = self.board_ax
        ax.set_facecolor(GOBAN)
        ax.set_xlim(-0.7, BOARD_SIZE - 0.3)
        ax.set_ylim(BOARD_SIZE - 0.3, -0.7)
        ax.set_aspect("equal")
        for i in range(BOARD_SIZE):
            ax.plot([0, BOARD_SIZE - 1], [i, i],
                    color=GRID, lw=0.7, zorder=1)
            ax.plot([i, i], [0, BOARD_SIZE - 1],
                    color=GRID, lw=0.7, zorder=1)
        for r in (3, 9, 15):
            for c in (3, 9, 15):
                ax.plot(c, r, "o", color=GRID, markersize=5, zorder=2)
        ax.set_xticks(range(BOARD_SIZE))
        ax.set_xticklabels([chr(ord("A") + i) for i in range(BOARD_SIZE)],
                           color=TEXT_MAIN, fontsize=9)
        ax.set_yticks(range(BOARD_SIZE))
        ax.set_yticklabels(range(1, BOARD_SIZE + 1),
                           color=TEXT_MAIN, fontsize=9)
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)

    def _setup_info_ax(self):
        ax = self.info_ax
        ax.set_facecolor(BG)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

    # ---------- primitives ----------

    def _card(self, x, y, w, h, face=CARD_BG, edge=CARD_BORDER, lw=1.2):
        box = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.005,rounding_size=0.015",
            facecolor=face, edgecolor=edge, linewidth=lw, zorder=1,
        )
        self.info_ax.add_patch(box)

    def _progress(self, x, y, w, h, frac, color=ACCENT):
        self.info_ax.add_patch(Rectangle(
            (x, y), w, h,
            facecolor="#EFE6D0", edgecolor=CARD_BORDER, lw=0.6, zorder=2,
        ))
        frac = max(0.0, min(1.0, frac))
        if frac > 0:
            self.info_ax.add_patch(Rectangle(
                (x, y), w * frac, h,
                facecolor=color, edgecolor="none", zorder=3,
            ))

    def _stone_icon(self, x, y, color, size=18, zorder=4):
        self.info_ax.plot(
            x, y, "o",
            markerfacecolor=color, markeredgecolor="black",
            markeredgewidth=0.8, markersize=size, zorder=zorder,
        )

    def _text(self, x, y, s, **kw):
        kw.setdefault("color", TEXT_MAIN)
        kw.setdefault("va", "center")
        kw.setdefault("ha", "left")
        kw.setdefault("fontsize", 11)
        return self.info_ax.text(x, y, s, **kw)

    # ---------- clearing ----------

    def _clear_info(self):
        for a in list(self.info_ax.patches):
            a.remove()
        for t in list(self.info_ax.texts):
            t.remove()
        for l in list(self.info_ax.lines):
            l.remove()

    def _clear_board_dynamic(self):
        for a in list(self.board_ax.patches):
            a.remove()
        for t in list(self.board_ax.texts):
            t.remove()
        # Remove overlay stone marker (added via ax.plot on board_ax)
        # only if it was ours; keep grid lines. Grid lines were added at
        # setup and use ax.plot too, so we distinguish by zorder>=10.
        for line in list(self.board_ax.lines):
            if getattr(line, "_gomoku_overlay", False):
                line.remove()

    # ---------- rendering ----------

    def _draw_all(self):
        self._clear_board_dynamic()
        self._draw_stones()
        self._draw_info()
        if self.game.is_over():
            self._draw_gameover_overlay()
        self.fig.canvas.draw_idle()

    def _draw_stones(self):
        board = self.game.board
        for r in range(board.size):
            for c in range(board.size):
                v = board.get(r, c)
                if v == EMPTY:
                    continue
                color = BLACK_STONE if v == BLACK else WHITE_STONE
                self.board_ax.add_patch(Circle(
                    (c, r), 0.42,
                    facecolor=color, edgecolor="black",
                    linewidth=0.6, zorder=3,
                ))
        if self.game.last_move is not None:
            r, c = self.game.last_move
            self.board_ax.add_patch(Circle(
                (c, r), 0.14,
                facecolor=LAST_MOVE, edgecolor="none", zorder=4,
            ))

    def _draw_info(self):
        self._clear_info()
        g = self.game

        # -- Title
        self._text(0.5, 0.965, "GOMOKU",
                   ha="center", fontsize=24, fontweight="bold")

        # -- Status card
        pending = g.is_pending_defense() and not g.is_over()
        self._card(
            0.02, 0.815, 0.96, 0.115,
            face=WARNING_BG if pending else STATUS_BG,
            edge=WARNING_BORDER if pending else CARD_BORDER,
            lw=1.6,
        )
        if g.is_over():
            stone_color = BLACK_STONE if g.winner == BLACK else WHITE_STONE
            self._stone_icon(0.09, 0.885, stone_color, size=22)
            self._text(0.17, 0.895, f"{g.winner_name()} wins",
                       fontsize=16, fontweight="bold")
            self._text(0.17, 0.855, f"by {g.win_reason}",
                       color=TEXT_MUTE, fontsize=10)
        else:
            cur = g.current
            stone_color = BLACK_STONE if cur == BLACK else WHITE_STONE
            self._stone_icon(0.09, 0.895, stone_color, size=22)
            self._text(0.17, 0.905, f"{STONE_NAME[cur]}'s turn",
                       fontsize=15, fontweight="bold")
            live = g.elapsed_current_turn()
            self._text(0.17, 0.867, f"thinking  {live:5.2f}s",
                       color=TEXT_MUTE, fontsize=10, family="monospace")
            if pending:
                self._text(0.5, 0.832,
                           "! break the line or you lose !",
                           ha="center", color=DANGER,
                           fontsize=10, fontweight="bold")

        # -- Player cards
        self._draw_player_card(BLACK, y=0.610)
        self._draw_player_card(WHITE, y=0.415)

        # -- Timing card
        self._card(0.02, 0.185, 0.96, 0.20)
        self._text(0.06, 0.355, "Timing",
                   fontsize=13, fontweight="bold")

        rows = [
            ("last move (Black)", _fmt_time(g.last_move_time(BLACK))),
            ("last move (White)", _fmt_time(g.last_move_time(WHITE))),
            ("total moves",       f"{g.move_count()}"),
        ]
        ys = [0.316, 0.278, 0.240]
        for (label, value), y in zip(rows, ys):
            self._text(0.06, y, label, color=TEXT_MUTE, fontsize=10)
            self._text(0.94, y, value,
                       ha="right", fontsize=11, family="monospace")

        self._text(0.06, 0.205, "overall average",
                   fontsize=11, fontweight="bold")
        self._text(0.94, 0.205, _fmt_time(g.average_time()),
                   ha="right", fontsize=13, fontweight="bold",
                   family="monospace", color=ACCENT)

        # -- Status / hint area
        if self._status_msg:
            color = DANGER if self._status_kind == "error" else TEXT_MUTE
            self._text(0.5, 0.135, self._status_msg,
                       ha="center", color=color, fontsize=10, fontstyle="italic")

        hint = ("game over — press R to restart"
                if g.is_over()
                else "click an intersection to place a stone")
        self._text(0.5, 0.07, hint,
                   ha="center", color=TEXT_MUTE, fontsize=9)

    def _draw_player_card(self, color, y):
        g = self.game
        name = STONE_NAME[color]
        stone_col = BLACK_STONE if color == BLACK else WHITE_STONE
        caps = g.captures[color]
        n_moves = g.move_count(color)
        avg = g.average_time(color)

        active = not g.is_over() and g.current == color
        edge = ACCENT if active else CARD_BORDER
        lw = 2.2 if active else 1.2

        self._card(0.02, y, 0.96, 0.180, edge=edge, lw=lw)

        # Header: stone + name (left), moves+avg (right)
        self._stone_icon(0.09, y + 0.132, stone_col, size=18)
        self._text(0.16, y + 0.135, name,
                   fontsize=13, fontweight="bold")
        if active:
            self._text(0.28, y + 0.135, "  to play",
                       fontsize=10, color=ACCENT, fontweight="bold")
        self._text(0.94, y + 0.135,
                   f"n={n_moves}   avg {_fmt_time(avg)}",
                   ha="right", color=TEXT_MUTE, fontsize=10, family="monospace")

        # Captures row
        self._text(0.06, y + 0.085, "captures",
                   color=TEXT_MUTE, fontsize=10)
        cap_color = DANGER if caps >= 8 else SUCCESS
        self._text(0.94, y + 0.085, f"{caps} / 10",
                   ha="right", color=cap_color,
                   fontsize=12, fontweight="bold", family="monospace")
        # Progress bar
        self._progress(0.06, y + 0.028, 0.88, 0.030,
                       caps / 10.0, color=cap_color)

    def _draw_gameover_overlay(self):
        g = self.game
        # Dim the board
        dim = Rectangle(
            (-1, -1), BOARD_SIZE + 2, BOARD_SIZE + 2,
            facecolor="white", alpha=0.60, zorder=10,
        )
        self.board_ax.add_patch(dim)

        bx, by, bw, bh = 1.5, 6.0, 16.0, 7.0
        banner = FancyBboxPatch(
            (bx, by), bw, bh,
            boxstyle="round,pad=0.4,rounding_size=0.8",
            facecolor="#FFF8E8", edgecolor="#8A6A32", linewidth=2.5,
            zorder=11,
        )
        self.board_ax.add_patch(banner)

        # The board Y-axis is inverted (top = 0). Offsets ADD to move DOWN.
        title_y  = by + 0.28 * bh
        reason_y = by + 0.46 * bh
        stats_y  = by + 0.70 * bh
        hint_y   = by + 0.87 * bh

        stone_color = BLACK_STONE if g.winner == BLACK else WHITE_STONE
        stone_line, = self.board_ax.plot(
            bx + 2.8, title_y, "o",
            markerfacecolor=stone_color, markeredgecolor="black",
            markeredgewidth=1.5, markersize=52, zorder=12,
        )
        stone_line._gomoku_overlay = True

        self.board_ax.text(
            bx + 5.0, title_y,
            f"{g.winner_name().upper()} WINS",
            fontsize=28, fontweight="bold", color=TEXT_MAIN,
            zorder=12, va="center", ha="left",
        )
        self.board_ax.text(
            bx + 5.0, reason_y,
            f"by {g.win_reason}",
            fontsize=15, color=TEXT_MUTE,
            zorder=12, va="center", ha="left",
        )
        self.board_ax.text(
            bx + bw / 2, stats_y,
            f"final average  {_fmt_time(g.average_time())}"
            f"    •    total moves  {g.move_count()}",
            fontsize=12, color=TEXT_MAIN,
            zorder=12, va="center", ha="center",
        )
        self.board_ax.text(
            bx + bw / 2, hint_y,
            "press  R  to restart    •    Q  to quit",
            fontsize=12, color=TEXT_MUTE, fontstyle="italic",
            zorder=12, va="center", ha="center",
        )

    # ---------- interaction ----------

    def _tick(self):
        if self.game.is_over():
            return
        self._draw_info()
        self.fig.canvas.draw_idle()

    def _reset(self):
        self.game.__init__()
        self._status_msg = "New game started."
        self._status_kind = "info"
        self._draw_all()

    def _on_click(self, event):
        # Ignore clicks on the button axes (they handle themselves).
        if event.inaxes in (self.reset_ax, self.quit_ax):
            return
        if event.inaxes != self.board_ax:
            return
        if self.game.is_over():
            self._status_msg = "Game over — press R (or Restart) to play again."
            self._status_kind = "error"
            self._draw_all()
            return
        if event.xdata is None or event.ydata is None:
            return
        c = int(round(event.xdata))
        r = int(round(event.ydata))
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            return
        ok, msg = self.game.play(r, c)
        if ok:
            self._status_msg = ""
            self._status_kind = "info"
        else:
            self._status_msg = f"Illegal move: {msg}"
            self._status_kind = "error"
        self._draw_all()

    def _on_key(self, event):
        if event.key == "q":
            plt.close(self.fig)
        elif event.key == "r":
            self._reset()

    def run(self):
        plt.show()


def _fmt_time(t):
    if t is None:
        return "  --  "
    return f"{t:5.2f}s"
