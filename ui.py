import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
from matplotlib.widgets import Button

from ai import choose_move
from board import BLACK, BOARD_SIZE, EMPTY, STONE_NAME, WHITE


# --- Palette ---
BG = "#F0E7D2"
GOBAN = "#DEB887"
GRID = "#3A2A18"
BLACK_STONE = "#111111"
WHITE_STONE = "#F8F8F8"
LAST_MOVE = "#D64545"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#B8A88A"
TEXT_MAIN = "#2A2018"
TEXT_MUTE = "#7A6E5C"
ACCENT = "#4A7A9E"
DANGER = "#C0392B"
SUCCESS = "#2E7D5E"
WARNING_BG = "#FFEACC"
WARNING_BORDER = "#E09040"
STATUS_BG = "#FFF8E8"

STAR_POINTS = (3, 9, 15)
CAPTURE_LIMIT = 10
CAPTURE_DANGER = 8


def stone_color(color):
    return BLACK_STONE if color == BLACK else WHITE_STONE


def fmt_time(t):
    if t is None:
        return "  --  "
    return f"{t:5.2f}s"


class GomokuUI:
    def __init__(self, game, players=None):
        self.game = game
        self.players = players or {BLACK: "human", WHITE: "human"}
        # Hint is available whenever at least one player is human.
        self.hint_enabled = "human" in self.players.values()
        self._hint = None
        self._status_msg = ""
        self._status_kind = "info"

        self.fig = plt.figure(figsize=(14, 8.5), facecolor=BG)
        self._set_window_title("Gomoku")

        self.board_ax = self.fig.add_axes([0.03, 0.06, 0.55, 0.90])
        self.info_ax = self.fig.add_axes([0.60, 0.14, 0.37, 0.82])
        if self.hint_enabled:
            self.reset_ax = self.fig.add_axes([0.60, 0.03, 0.12, 0.07])
            self.hint_ax = self.fig.add_axes([0.735, 0.03, 0.12, 0.07])
            self.quit_ax = self.fig.add_axes([0.87, 0.03, 0.10, 0.07])
        else:
            self.reset_ax = self.fig.add_axes([0.60, 0.03, 0.17, 0.07])
            self.hint_ax = None
            self.quit_ax = self.fig.add_axes([0.80, 0.03, 0.17, 0.07])

        self._setup_buttons()
        self._setup_board_ax()
        self._setup_info_ax()
        self._connect_events()
        self._start_timer()

        self._draw_all()

    def run(self):
        plt.show()

    # ---------- setup ----------

    def _set_window_title(self, title):
        try:
            self.fig.canvas.manager.set_window_title(title)
        except Exception:
            pass

    def _setup_buttons(self):
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

        if self.hint_ax is not None:
            self.hint_btn = Button(
                self.hint_ax, "Hint (H)",
                color="#D4E4EA", hovercolor="#B8D0DA",
            )
            self.hint_btn.on_clicked(lambda _e: self._show_hint())

    def _setup_board_ax(self):
        ax = self.board_ax
        ax.set_facecolor(GOBAN)
        ax.set_xlim(-0.7, BOARD_SIZE - 0.3)
        ax.set_ylim(BOARD_SIZE - 0.3, -0.7)
        ax.set_aspect("equal")
        self._draw_grid_lines()
        self._draw_star_points()
        self._set_board_labels()

    def _draw_grid_lines(self):
        ax = self.board_ax
        end = BOARD_SIZE - 1
        for i in range(BOARD_SIZE):
            ax.plot([0, end], [i, i], color=GRID, lw=0.7, zorder=1)
            ax.plot([i, i], [0, end], color=GRID, lw=0.7, zorder=1)

    def _draw_star_points(self):
        ax = self.board_ax
        for r in STAR_POINTS:
            for c in STAR_POINTS:
                ax.plot(c, r, "o", color=GRID, markersize=5, zorder=2)

    def _set_board_labels(self):
        ax = self.board_ax
        letters = [chr(ord("A") + i) for i in range(BOARD_SIZE)]
        ax.set_xticks(range(BOARD_SIZE))
        ax.set_xticklabels(letters, color=TEXT_MAIN, fontsize=9)
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

    def _connect_events(self):
        self.fig.canvas.mpl_connect("button_press_event", self._on_click)
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)

    def _start_timer(self):
        self._timer = self.fig.canvas.new_timer(interval=100)
        self._timer.add_callback(self._tick)
        self._timer.start()

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

    def _board_text(self, x, y, s, **kw):
        kw.setdefault("va", "center")
        kw.setdefault("ha", "left")
        kw.setdefault("zorder", 12)
        return self.board_ax.text(x, y, s, **kw)

    # ---------- clearing ----------

    def _clear_info(self):
        for patch in list(self.info_ax.patches):
            patch.remove()
        for text in list(self.info_ax.texts):
            text.remove()
        for line in list(self.info_ax.lines):
            line.remove()

    def _clear_board_dynamic(self):
        for patch in list(self.board_ax.patches):
            patch.remove()
        for text in list(self.board_ax.texts):
            text.remove()
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
                if v != EMPTY:
                    self._draw_stone(r, c, stone_color(v))
        if self.game.last_move is not None:
            r, c = self.game.last_move
            self._draw_last_move_marker(r, c)
        if self._hint is not None and not self.game.is_over():
            self._draw_hint_marker(*self._hint)

    def _draw_hint_marker(self, r, c):
        self.board_ax.add_patch(Circle(
            (c, r), 0.42,
            facecolor="none", edgecolor=ACCENT,
            linewidth=2.4, linestyle="--", zorder=5,
        ))

    def _draw_stone(self, r, c, color):
        self.board_ax.add_patch(Circle(
            (c, r), 0.42,
            facecolor=color, edgecolor="black",
            linewidth=0.6, zorder=3,
        ))

    def _draw_last_move_marker(self, r, c):
        self.board_ax.add_patch(Circle(
            (c, r), 0.14,
            facecolor=LAST_MOVE, edgecolor="none", zorder=4,
        ))

    # ---------- info panel ----------

    def _draw_info(self):
        self._clear_info()
        self._draw_title()
        self._draw_status_card()
        self._draw_player_card(BLACK, y=0.610)
        self._draw_player_card(WHITE, y=0.415)
        self._draw_timing_card()
        self._draw_status_message()
        self._draw_hint()

    def _draw_title(self):
        self._text(0.5, 0.965, "GOMOKU",
                   ha="center", fontsize=24, fontweight="bold")

    def _draw_status_card(self):
        g = self.game
        pending = g.is_pending_defense() and not g.is_over()
        self._card(
            0.02, 0.815, 0.96, 0.115,
            face=WARNING_BG if pending else STATUS_BG,
            edge=WARNING_BORDER if pending else CARD_BORDER,
            lw=1.6,
        )
        if g.is_over():
            self._draw_winner_status()
        else:
            self._draw_turn_status(pending)

    def _draw_winner_status(self):
        g = self.game
        self._stone_icon(0.09, 0.885, stone_color(g.winner), size=22)
        self._text(0.17, 0.895, f"{g.winner_name()} wins",
                   fontsize=16, fontweight="bold")
        self._text(0.17, 0.855, f"by {g.win_reason}",
                   color=TEXT_MUTE, fontsize=10)

    def _draw_turn_status(self, pending):
        g = self.game
        self._stone_icon(0.09, 0.895, stone_color(g.current), size=22)
        self._text(0.17, 0.905, f"{STONE_NAME[g.current]}'s turn",
                   fontsize=15, fontweight="bold")
        self._text(0.17, 0.867,
                   f"thinking  {g.elapsed_current_turn():5.2f}s",
                   color=TEXT_MUTE, fontsize=10, family="monospace")
        if pending:
            self._text(0.5, 0.832,
                       "! break the line or you lose !",
                       ha="center", color=DANGER,
                       fontsize=10, fontweight="bold")

    def _draw_player_card(self, color, y):
        active = not self.game.is_over() and self.game.current == color
        edge = ACCENT if active else CARD_BORDER
        lw = 2.2 if active else 1.2
        self._card(0.02, y, 0.96, 0.180, edge=edge, lw=lw)
        self._draw_player_header(color, y, active)
        self._draw_player_captures(color, y)

    def _draw_player_header(self, color, y, active):
        n = self.game.move_count(color)
        avg = fmt_time(self.game.average_time(color))
        summary = f"n={n}   avg {avg}"
        self._stone_icon(0.09, y + 0.132, stone_color(color), size=18)
        self._text(0.16, y + 0.135, STONE_NAME[color],
                   fontsize=13, fontweight="bold")
        if active:
            self._text(0.28, y + 0.135, "  to play",
                       fontsize=10, color=ACCENT, fontweight="bold")
        self._text(0.94, y + 0.135, summary,
                   ha="right", color=TEXT_MUTE,
                   fontsize=10, family="monospace")

    def _draw_player_captures(self, color, y):
        caps = self.game.captures[color]
        cap_color = DANGER if caps >= CAPTURE_DANGER else SUCCESS
        self._text(0.06, y + 0.085, "captures",
                   color=TEXT_MUTE, fontsize=10)
        self._text(0.94, y + 0.085, f"{caps} / {CAPTURE_LIMIT}",
                   ha="right", color=cap_color,
                   fontsize=12, fontweight="bold", family="monospace")
        self._progress(0.06, y + 0.028, 0.88, 0.030,
                       caps / CAPTURE_LIMIT, color=cap_color)

    def _draw_timing_card(self):
        g = self.game
        self._card(0.02, 0.185, 0.96, 0.20)
        self._text(0.06, 0.355, "Timing",
                   fontsize=13, fontweight="bold")

        rows = [
            ("last move (Black)", fmt_time(g.last_move_time(BLACK))),
            ("last move (White)", fmt_time(g.last_move_time(WHITE))),
            ("total moves", f"{g.move_count()}"),
        ]
        for (label, value), y in zip(rows, (0.316, 0.278, 0.240)):
            self._text(0.06, y, label, color=TEXT_MUTE, fontsize=10)
            self._text(0.94, y, value,
                       ha="right", fontsize=11, family="monospace")

        self._text(0.06, 0.205, "overall average",
                   fontsize=11, fontweight="bold")
        self._text(0.94, 0.205, fmt_time(g.average_time()),
                   ha="right", fontsize=13, fontweight="bold",
                   family="monospace", color=ACCENT)

    def _draw_status_message(self):
        if not self._status_msg:
            return
        color = DANGER if self._status_kind == "error" else TEXT_MUTE
        self._text(0.5, 0.135, self._status_msg,
                   ha="center", color=color,
                   fontsize=10, fontstyle="italic")

    def _draw_hint(self):
        hint = ("game over — press R to restart"
                if self.game.is_over()
                else "click an intersection to place a stone")
        self._text(0.5, 0.07, hint,
                   ha="center", color=TEXT_MUTE, fontsize=9)

    # ---------- game over overlay ----------

    def _draw_gameover_overlay(self):
        self._draw_gameover_dim()
        bx, by, bw, bh = 1.5, 6.0, 16.0, 7.0
        self._draw_gameover_banner(bx, by, bw, bh)
        self._draw_gameover_content(bx, by, bw, bh)

    def _draw_gameover_dim(self):
        self.board_ax.add_patch(Rectangle(
            (-1, -1), BOARD_SIZE + 2, BOARD_SIZE + 2,
            facecolor="white", alpha=0.60, zorder=10,
        ))

    def _draw_gameover_banner(self, bx, by, bw, bh):
        self.board_ax.add_patch(FancyBboxPatch(
            (bx, by), bw, bh,
            boxstyle="round,pad=0.4,rounding_size=0.8",
            facecolor="#FFF8E8", edgecolor="#8A6A32", linewidth=2.5,
            zorder=11,
        ))

    def _draw_gameover_content(self, bx, by, bw, bh):
        g = self.game
        title_y = by + 0.28 * bh
        reason_y = by + 0.46 * bh
        stats_y = by + 0.70 * bh
        hint_y = by + 0.87 * bh
        center_x = bx + bw / 2

        self._draw_gameover_stone(bx + 2.8, title_y, stone_color(g.winner))
        self._board_text(bx + 5.0, title_y,
                         f"{g.winner_name().upper()} WINS",
                         fontsize=28, fontweight="bold", color=TEXT_MAIN)
        self._board_text(bx + 5.0, reason_y,
                         f"by {g.win_reason}",
                         fontsize=15, color=TEXT_MUTE)
        self._board_text(center_x, stats_y,
                         f"final average  {fmt_time(g.average_time())}"
                         f"    •    total moves  {g.move_count()}",
                         ha="center", fontsize=12, color=TEXT_MAIN)
        self._board_text(center_x, hint_y,
                         "press  R  to restart    •    Q  to quit",
                         ha="center", fontsize=12, color=TEXT_MUTE,
                         fontstyle="italic")

    def _draw_gameover_stone(self, x, y, color):
        line, = self.board_ax.plot(
            x, y, "o",
            markerfacecolor=color, markeredgecolor="black",
            markeredgewidth=1.5, markersize=52, zorder=12,
        )
        line._gomoku_overlay = True

    # ---------- interaction ----------

    def _tick(self):
        if self.game.is_over():
            return
        if self._is_ai_turn():
            self._ai_play()
            return
        self._draw_info()
        self.fig.canvas.draw_idle()

    def _is_ai_turn(self):
        return self.players.get(self.game.current) == "ai"

    def _ai_play(self):
        move = choose_move(self.game)
        if move is None:
            self._set_status("AI has no legal move.", "error")
            self._draw_all()
            return
        r, c = move
        ok, msg = self.game.play(r, c)
        if not ok:
            self._set_status(f"AI produced illegal move: {msg}", "error")
        else:
            self._hint = None
        self._draw_all()

    def _show_hint(self):
        if self.game.is_over() or self._is_ai_turn():
            return
        self._hint = choose_move(self.game)
        self._draw_all()

    def _reset(self):
        self.game.__init__()
        self._hint = None
        self._set_status("New game started.", "info")
        self._draw_all()

    def _on_key(self, event):
        if event.key == "q":
            plt.close(self.fig)
        elif event.key == "r":
            self._reset()
        elif event.key == "h" and self.hint_enabled:
            self._show_hint()

    def _on_click(self, event):
        button_axes = [self.reset_ax, self.quit_ax]
        if self.hint_ax is not None:
            button_axes.append(self.hint_ax)
        if event.inaxes in button_axes:
            return
        if event.inaxes != self.board_ax:
            return
        if self.game.is_over():
            self._set_status(
                "Game over — press R (or Restart) to play again.",
                "error",
            )
            self._draw_all()
            return
        if self._is_ai_turn():
            self._set_status("Wait — it's the AI's turn.", "info")
            self._draw_all()
            return
        cell = self._click_to_cell(event)
        if cell is None:
            return
        self._try_play(*cell)

    def _click_to_cell(self, event):
        if event.xdata is None or event.ydata is None:
            return None
        c = int(round(event.xdata))
        r = int(round(event.ydata))
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            return None
        return r, c

    def _try_play(self, r, c):
        ok, msg = self.game.play(r, c)
        if ok:
            self._hint = None
            self._set_status("", "info")
        else:
            self._set_status(f"Illegal move: {msg}", "error")
        self._draw_all()

    def _set_status(self, msg, kind):
        self._status_msg = msg
        self._status_kind = kind


# ---------- start-screen mode picker ----------


def _pick_from_menu(title, options):
    """Show a small window of stacked buttons and return the picked key.

    `options` is a list of (key, label) pairs. Returns None if the user
    closes the window without clicking any button.
    """
    fig = plt.figure(figsize=(6.5, 5.5), facecolor=BG)
    try:
        fig.canvas.manager.set_window_title("Gomoku")
    except Exception:
        pass

    fig.text(0.5, 0.92, "GOMOKU", ha="center",
             fontsize=26, fontweight="bold", color=TEXT_MAIN)
    fig.text(0.5, 0.85, title, ha="center",
             fontsize=13, color=TEXT_MUTE)

    choice = {"key": None}
    buttons = []
    top, height, gap = 0.70, 0.12, 0.03

    def make_callback(key):
        def _clicked(_event):
            choice["key"] = key
            plt.close(fig)
        return _clicked

    for i, (key, label) in enumerate(options):
        y = top - i * (height + gap)
        ax = fig.add_axes([0.10, y - height, 0.80, height])
        btn = Button(ax, label, color=CARD_BG, hovercolor="#EAD8B0")
        btn.on_clicked(make_callback(key))
        buttons.append(btn)

    plt.show()
    return choice["key"]


def select_mode():
    """Run the start-screen wizard.

    Returns one of "pvp", "pvai-black", "pvai-white", "aivai", or None
    if the user closes the window without finishing the choice.
    """
    top = _pick_from_menu(
        "Choose a game mode",
        [
            ("pvp",   "Human   vs   Human"),
            ("pvai",  "Human   vs   AI"),
            ("aivai", "AI   vs   AI"),
        ],
    )
    if top != "pvai":
        return top

    return _pick_from_menu(
        "Which color do you want to play?",
        [
            ("pvai-black", "Black   (you play first)"),
            ("pvai-white", "White"),
        ],
    )
