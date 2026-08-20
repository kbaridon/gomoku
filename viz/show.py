"""A slide deck, in matplotlib, explaining what the engine does.

One panel per idea, stepped through with the arrow keys or the buttons.
Every figure on every panel was measured by `viz.measure` on the real engine
moments before the window opened, so the deck describes the code as it is
rather than as it was written up.

Drawn with the same palette as the game's own board, and with nothing but
matplotlib -- the project has no other graphics dependency.
"""

import textwrap

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrow, Rectangle
from matplotlib.widgets import Button

from board import BLACK
from ui import (ACCENT, BG, CARD_BORDER, DANGER, GOBAN, GRID, SUCCESS,
                TEXT_MAIN, TEXT_MUTE, BLACK_STONE, WHITE_STONE)

CARD = "#FFFFFF"
SOFT = "#EFE6D0"

# Where the caption sits, and how wide it wraps. Every panel keeps its
# content above this: a caption that ran off the bottom of the figure would
# be invisible, and the panels whose explanation matters most have the
# longest ones.
CAPTION_Y = 0.225
CAPTION_WIDTH = 116


# ---------- drawing helpers ----------


def _wrap(text, width=96):
    out = []
    for paragraph in text.strip().split("\n\n"):
        out.append(textwrap.fill(" ".join(paragraph.split()), width))
    return "\n\n".join(out)


def _blank_axes(fig, rect, face="none"):
    ax = fig.add_axes(rect)
    ax.set_facecolor(face)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return ax


def _goban(fig, rect, trace, title=None):
    """The trace position, drawn as a board. Returns the axes to overlay on."""
    size = trace["board_size"]
    ax = fig.add_axes(rect)
    ax.set_facecolor(GOBAN)
    for i in range(size):
        ax.plot([0, size - 1], [i, i], color=GRID, lw=0.5, zorder=1)
        ax.plot([i, i], [0, size - 1], color=GRID, lw=0.5, zorder=1)
    for r, c, color in trace["stones"]:
        ax.add_patch(Circle((c, r), 0.42, zorder=5,
                            facecolor=BLACK_STONE if color == BLACK else WHITE_STONE,
                            edgecolor="#00000066", lw=0.6))
    ax.set_xlim(-1, size)
    ax.set_ylim(size, -1)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")
    for spine in ax.spines.values():
        spine.set_color(CARD_BORDER)
    if title:
        ax.set_title(title, color=TEXT_MAIN, fontsize=11, pad=8)
    return ax


def _hbars(ax, labels, values, displays, colors=None, xlabel="", log=False):
    spots = range(len(labels))
    colors = colors or [ACCENT] * len(labels)
    ax.barh(list(spots), values, color=colors, height=0.62, zorder=3)
    ax.set_yticks(list(spots))
    ax.set_yticklabels(labels, fontsize=10, color=TEXT_MAIN)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel, fontsize=9.5, color=TEXT_MUTE)
    ax.tick_params(axis="x", labelsize=9, colors=TEXT_MUTE)
    ax.grid(axis="x", color=CARD_BORDER, lw=0.5, alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(CARD_BORDER)
    span = max(values) if values else 1
    if log:
        floor = min(v for v in values if v > 0) / 2
        ax.set_xscale("log")
        ax.set_xlim(floor, span * 2.4)
        for i, (value, shown) in enumerate(zip(values, displays)):
            ax.text(value * 1.12, i, shown, va="center", fontsize=9.5,
                    color=TEXT_MAIN, fontweight="bold")
    else:
        ax.set_xlim(0, span * 1.20)
        for i, (value, shown) in enumerate(zip(values, displays)):
            ax.text(value + span * 0.02, i, shown, va="center", fontsize=9.5,
                    color=TEXT_MAIN, fontweight="bold")


def _ratio_bars(ax, labels, ratios, colors, xlabel):
    """Bars for numbers either side of 1, drawn from 1 rather than from 0.

    A ratio chart on a plain axis is misleading in both directions: on a
    linear scale one 50x bar flattens everything else, and on a log scale a
    0.4x bar reaches almost as far as a 1.0x one. Plotting the log of the
    ratio puts break-even at the origin, so "helps" runs right, "costs" runs
    left, and equal factors get equal lengths.
    """
    import math

    spots = list(range(len(labels)))
    lengths = [math.log2(r) if r > 0 else 0 for r in ratios]
    ax.barh(spots, lengths, color=colors, height=0.62, zorder=3)
    ax.set_yticks(spots)
    ax.set_yticklabels(labels, fontsize=10, color=TEXT_MAIN)
    ax.invert_yaxis()
    ax.axvline(0, color=TEXT_MAIN, lw=1.2, zorder=4)

    reach = max(abs(v) for v in lengths) if lengths else 1
    ticks = [t for t in (-2, -1, 0, 1, 2, 3, 4, 5, 6) if abs(t) <= reach + 1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{2.0 ** t:g}x" for t in ticks])
    ax.set_xlim(min(-1.0, min(lengths) - 0.7), max(lengths) + 1.1)
    ax.set_xlabel(xlabel, fontsize=9.5, color=TEXT_MUTE)
    ax.tick_params(labelsize=9, colors=TEXT_MUTE)
    ax.grid(axis="x", color=CARD_BORDER, lw=0.5, alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(CARD_BORDER)
    for i, (length, ratio) in enumerate(zip(lengths, ratios)):
        offset = 0.12 if length >= 0 else -0.12
        ax.text(length + offset, i, f"{ratio:.1f}x", va="center",
                ha="left" if length >= 0 else "right",
                fontsize=9.5, color=TEXT_MAIN, fontweight="bold")


def _funnel(ax, stages):
    """A row of boxes with arrows, each labelled with a count."""
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    gap = 0.34
    width = (10 - 0.5 - gap * (len(stages) - 1)) / len(stages)
    for i, (count, label) in enumerate(stages):
        left = i * (width + gap) + 0.25
        ax.add_patch(Rectangle((left, 0.85), width, 1.35, zorder=2,
                               facecolor=CARD, edgecolor=ACCENT, lw=1.4,
                               joinstyle="round"))
        ax.text(left + width / 2, 1.72, f"{count}", ha="center",
                fontsize=19, color=ACCENT, fontweight="bold", zorder=3)
        ax.text(left + width / 2, 1.16, textwrap.fill(label, 17), ha="center",
                va="center", fontsize=8.4, color=TEXT_MUTE, zorder=3)
        if i < len(stages) - 1:
            ax.add_patch(FancyArrow(left + width + 0.05, 1.52, gap - 0.14, 0,
                                    width=0.03, head_width=0.16,
                                    head_length=0.14, length_includes_head=True,
                                    color=TEXT_MUTE, zorder=3))


def _micro(data, key):
    """One micro-benchmark by its stable key, not by its display name."""
    for row in data["micro"]:
        if row["key"] == key:
            return row
    raise KeyError(f"no micro-benchmark keyed {key!r}")


# ---------- panels ----------
#
# Each panel takes the figure and the measurements, draws itself into the
# content area, and returns the caption printed underneath.


def panel_overview(fig, data):
    trace = data["trace"]
    ax = _blank_axes(fig, [0.06, 0.575, 0.88, 0.245])
    _funnel(ax, [
        (361, "cells on the goban"),
        (trace["space_cells"], "inside the windows"),
        (trace["candidates"], "with a stone in reach"),
        (len(trace["shortlist"]), "shortlisted"),
        (len(trace["ranked"]), "actually searched"),
    ])

    steps = [
        ("1  Confine", "cluster the stones, keep a rectangle around each"),
        ("2  Shortlist", "empty cells with a stone in reach, ranked by crowding"),
        ("3  Rank", "play each one, read the running evaluation, take it back"),
        ("4  Search", "negamax with alpha-beta, deepening two plies at a time"),
    ]
    ax2 = _blank_axes(fig, [0.06, 0.275, 0.88, 0.27])
    ax2.set_xlim(0, 4)
    ax2.set_ylim(0, 1)
    for i, (head, body) in enumerate(steps):
        ax2.add_patch(Rectangle((i + 0.04, 0.12), 0.92, 0.76, zorder=2,
                                facecolor=CARD, edgecolor=CARD_BORDER, lw=1))
        ax2.text(i + 0.5, 0.70, head, ha="center", fontsize=12.5,
                 color=ACCENT, fontweight="bold", zorder=3)
        ax2.text(i + 0.5, 0.44, textwrap.fill(body, 26), ha="center",
                 va="center", fontsize=9, color=TEXT_MUTE, zorder=3)

    return ("Every half-second the engine repeats these four stages. The "
            "funnel is the whole point: ranking a move means playing it, and "
            "that is the most expensive thing here, so almost everything is "
            "thrown out before it is ever scored.")


def panel_space(fig, data):
    trace = data["trace"]
    ax = _goban(fig, [0.055, 0.27, 0.40, 0.55], trace)
    for r0, c0, r1, c1 in trace["windows"]:
        ax.add_patch(Rectangle((c0 - 0.5, r0 - 0.5), c1 - c0 + 1, r1 - r0 + 1,
                               facecolor=ACCENT, alpha=0.16, zorder=3,
                               edgecolor=ACCENT, lw=1.8, linestyle=(0, (5, 3))))

    ax2 = _blank_axes(fig, [0.52, 0.27, 0.42, 0.55], face=CARD)
    for spine in ax2.spines.values():
        spine.set_visible(True)
        spine.set_color(CARD_BORDER)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    lines = [
        ("Windows", f"{len(trace['windows'])}"),
        ("Cells searched", f"{trace['space_cells']} of 361"),
        ("Share of the board", f"{100 * trace['space_cells'] / 361:.0f} %"),
    ]
    for i, (key, value) in enumerate(lines):
        y = 0.85 - i * 0.16
        ax2.text(0.07, y, key, fontsize=11, color=TEXT_MUTE)
        ax2.text(0.93, y, value, fontsize=15, color=ACCENT, ha="right",
                 fontweight="bold")
    ax2.text(0.07, 0.34, _wrap(
        "Stones within three cells of each other form a cluster; each cluster "
        "gives one rectangle, grown by a two-cell margin. Two rectangles merge "
        "only while the merge wastes little area, so a fight in one corner "
        "never drags the opposite corner into the search.", 46),
        fontsize=9.5, color=TEXT_MAIN, va="top")

    return ("A single bounding box around every stone would cover most of the "
            "board as soon as play spreads. Several rectangles do not.")


def panel_proximity(fig, data):
    trace = data["trace"]
    ax = _goban(fig, [0.055, 0.27, 0.40, 0.55], trace)
    peak = max((max(row) for row in trace["proximity"]), default=1) or 1
    occupied = {(r, c) for r, c, _ in trace["stones"]}
    for r, row in enumerate(trace["proximity"]):
        for c, weight in enumerate(row):
            if not weight or (r, c) in occupied:
                continue
            ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, zorder=2,
                                   facecolor=ACCENT, edgecolor="none",
                                   alpha=0.10 + 0.62 * weight / peak))

    micro = _micro(data, "shortlist")
    ax2 = fig.add_axes([0.56, 0.53, 0.36, 0.20])
    ax2.set_facecolor(BG)
    _hbars(ax2,
           ["counted per node", "kept up to date"],
           [micro["slow"] * 1e6, micro["fast"] * 1e6],
           [f"{micro['slow'] * 1e6:.0f} us", f"{micro['fast'] * 1e6:.0f} us"],
           colors=[DANGER, SUCCESS],
           xlabel="microseconds to shortlist one node")

    card = _blank_axes(fig, [0.56, 0.27, 0.36, 0.20], face=CARD)
    for spine in card.spines.values():
        spine.set_visible(True)
        spine.set_color(CARD_BORDER)
    card.set_xlim(0, 1)
    card.set_ylim(0, 1)
    card.text(0.05, 0.86, _wrap(
        "A stone landing on the board adds its weight to the sixteen cells "
        "around it, and taking it back subtracts it again. The geometry is "
        "resolved once at import, so the update is a flat loop with no "
        "arithmetic and no bounds test.", 44),
        fontsize=9.3, color=TEXT_MAIN, va="top")

    return _wrap(
        f"Each empty cell carries a count of the stones within two steps, "
        f"updated when a stone appears or disappears rather than recomputed. "
        f"That is {micro['speedup']:.0f} times cheaper per node -- and a node "
        f"does this once, every time.")


def panel_shortlist(fig, data):
    trace = data["trace"]
    ax = _goban(fig, [0.055, 0.27, 0.40, 0.55], trace)
    for rank, (_, r, c) in enumerate(trace["shortlist"], start=1):
        ax.add_patch(Circle((c, r), 0.40, facecolor="none", edgecolor=ACCENT,
                            lw=1.6, zorder=4))
        ax.text(c, r, str(rank), ha="center", va="center", fontsize=6.5,
                color=TEXT_MAIN, fontweight="bold", zorder=6)

    ax2 = _blank_axes(fig, [0.52, 0.27, 0.42, 0.55], face=CARD)
    for spine in ax2.spines.values():
        spine.set_visible(True)
        spine.set_color(CARD_BORDER)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.text(0.07, 0.90, "Crowding is a crude measure", fontsize=12,
             color=ACCENT, fontweight="bold", va="top")
    ax2.text(0.07, 0.79, _wrap(
        "It counts neighbours in every direction alike, so it rewards a blob "
        "of stones and says nothing about a line. The move that completes or "
        "blocks a five is often a lonely cell at the end of a row, ranked "
        "below a dozen cells in the middle of a crowd.\n\n"
        "So before anything is thrown away, the cells about to be cut are "
        "checked for that one thing, and a cell that makes or stops a five "
        "goes to the front instead of over the edge.\n\n"
        "Without that check the engine drops the only move stopping a four "
        "and loses games it had already won.", 46),
        fontsize=9.5, color=TEXT_MAIN, va="top")

    return (f"{len(trace['shortlist'])} cells survive the cheap pass, out of "
            f"{trace['candidates']} with a stone in reach.")


def panel_ranking(fig, data):
    trace = data["trace"]
    ax = _goban(fig, [0.055, 0.27, 0.40, 0.55], trace)
    for rank, (_, r, c, _, _) in enumerate(trace["ranked"], start=1):
        ax.add_patch(Circle((c, r), 0.40, zorder=4, edgecolor=ACCENT, lw=1.8,
                            facecolor=ACCENT if rank == 1 else "none",
                            alpha=1.0 if rank > 1 else 0.45))
        ax.text(c, r, str(rank), ha="center", va="center", fontsize=6.5,
                color=TEXT_MAIN, fontweight="bold", zorder=6)

    top = trace["ranked"][:8]
    ax2 = fig.add_axes([0.55, 0.29, 0.39, 0.50])
    ax2.set_facecolor(BG)
    floor = min(score for score, *_ in top)
    _hbars(ax2,
           [f"{i}. ({r}, {c})" for i, (_, r, c, _, _) in enumerate(top, 1)],
           [score - floor + 1 for score, *_ in top],
           [f"{score:,}".replace(",", " ") for score, *_ in top],
           xlabel="static score after the move (offset to fit)")

    forced = trace["forced"]
    tail = ("Nothing is forced here, so every candidate stands."
            if not forced else
            f"The opponent would win outright at {forced[0]}, so everything "
            f"that does not answer it is dropped.")
    return _wrap(
        "Now the real ranking: each shortlisted cell is played, the running "
        "evaluation is read off, and the move is taken back. This order is "
        "what alpha-beta lives on -- and at the last ply the score is also "
        "the leaf value, so ordering and evaluating are one pass. " + tail)


def panel_alphabeta(fig, data):
    pruning = data["pruning"]
    ax = _blank_axes(fig, [0.045, 0.345, 0.52, 0.32])
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.3, 3.6)
    ax.set_aspect("equal")     # sinon les noeuds sont des ellipses

    def node(x, y, cut=False):
        ax.add_patch(Circle((x, y), 0.30, zorder=4,
                            facecolor=SOFT if cut else CARD,
                            edgecolor=DANGER if cut else ACCENT,
                            lw=1.5, alpha=0.45 if cut else 1))
        if cut:
            ax.plot([x - 0.19, x + 0.19], [y - 0.19, y + 0.19],
                    color=DANGER, lw=1.6, zorder=5)

    node(6, 2.9)
    kids = [2.4, 6, 9.6]
    for i, x in enumerate(kids):
        node(x, 1.8, cut=False)
        ax.plot([6, x], [2.62, 2.06], color=TEXT_MUTE, lw=1, zorder=2)
        for j, dx in enumerate((-1.0, 0, 1.0)):
            cut = i > 0 and j > 0
            node(x + dx, 0.6, cut=cut)
            ax.plot([x, x + dx], [1.53, 0.86], zorder=2, lw=1,
                    color=DANGER if cut else TEXT_MUTE,
                    alpha=0.45 if cut else 1)
    ax.text(6, -0.12, "crossed nodes are never visited: the branch above "
                      "them cannot change the answer", ha="center",
            fontsize=8.5, color=TEXT_MUTE)

    ax2 = fig.add_axes([0.63, 0.385, 0.31, 0.24])
    ax2.set_facecolor(BG)
    ax2.set_facecolor(BG)
    _hbars(ax2, ["no pruning", "alpha-beta"],
           [pruning["full"], pruning["pruned"]],
           [f"{pruning['full']}", f"{pruning['pruned']}"],
           colors=[DANGER, SUCCESS],
           xlabel=f"nodes visited at depth {pruning['depth']}")

    return _wrap(
        f"Alpha-beta drops any branch that cannot change the result, which "
        f"here saves {pruning['saved'] * 100:.0f}% of the nodes "
        f"({pruning['full']} down to {pruning['pruned']}) -- the same answer "
        f"in {pruning['pruned_seconds'] * 1000:.0f} ms instead of "
        f"{pruning['full_seconds'] * 1000:.0f} ms. The saving depends "
        f"entirely on trying good moves first, which is what the previous two "
        f"panels were for. Search a node's moves in the worst order and "
        f"alpha-beta saves nothing at all.")


def panel_beam(fig, data):
    beam = data["beam"]
    widths = list(beam["by_ply"])
    plies = list(range(len(widths) + 3))
    widths = widths + [beam["deep"]] * 3

    ax = fig.add_axes([0.075, 0.30, 0.40, 0.50])
    ax.set_facecolor(BG)
    ax.bar(plies, widths, color=ACCENT, width=0.66, zorder=3)
    for x, w in zip(plies, widths):
        ax.text(x, w + 0.3, str(w), ha="center", fontsize=10,
                color=TEXT_MAIN, fontweight="bold")
    ax.set_xlabel("ply (distance from the root)", fontsize=10, color=TEXT_MUTE)
    ax.set_ylabel("moves expanded", fontsize=10, color=TEXT_MUTE)
    ax.set_xticks(plies)
    ax.tick_params(labelsize=9, colors=TEXT_MUTE)
    ax.grid(axis="y", color=CARD_BORDER, lw=0.5, alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.set_ylim(0, max(widths) * 1.22)

    beam_case = next((c for c in data["ablations"]["cases"]
                      if c["name"] == "Narrowing beam"), None)
    ax2 = _blank_axes(fig, [0.53, 0.27, 0.41, 0.55], face=CARD)
    for spine in ax2.spines.values():
        spine.set_visible(True)
        spine.set_color(CARD_BORDER)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.text(0.07, 0.92, "Why it narrows", fontsize=12.5, color=ACCENT,
             fontweight="bold", va="top")
    text = (
        "Ten moves per node grows the tree by about 2.9 per level even after "
        "alpha-beta. Ten levels of that is a hundred thousand nodes: half a "
        "minute against a half-second budget.\n\n"
        "Width is needed where the move is chosen, near the root. Deeper down "
        "the line is already committed and only needs confirming, so the beam "
        "narrows to two.\n\n"
        "The root is the exception: it keeps its full width while the "
        f"iterations are cheap and drops to {beam['root_deep']} from depth "
        f"{beam['root_narrows_at']} on. Narrowing a root a shallow search has "
        "already sorted costs far less than starting narrow.")
    if beam_case:
        text += (f"\n\nWith a flat width instead, the same search takes "
                 f"{beam_case['cost']:.0f} times as long.")
    ax2.text(0.07, 0.81, _wrap(text, 44), fontsize=9.5, color=TEXT_MAIN,
             va="top")

    return ("This is the one change that puts ten plies inside the budget. "
            "It is also the one that costs the most playing strength, which "
            "the last panel comes back to.")


def panel_deepening(fig, data):
    rows = [row for row in data["deepening"]["rows"] if row["nodes"]]
    depths = [row["depth"] for row in rows]
    nodes = [row["nodes"] for row in rows]
    times = [row["seconds"] * 1000 for row in rows]

    ax = fig.add_axes([0.075, 0.30, 0.48, 0.50])
    ax.set_facecolor(BG)
    ax.bar(depths, nodes, width=1.2, color=ACCENT, zorder=3, label="nodes")
    ax.set_xlabel("depth completed", fontsize=10, color=TEXT_MUTE)
    ax.set_ylabel("nodes visited", fontsize=10, color=ACCENT)
    ax.set_xticks(depths)
    ax.tick_params(labelsize=9, colors=TEXT_MUTE)
    ax.grid(axis="y", color=CARD_BORDER, lw=0.5, alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    twin = ax.twinx()
    twin.plot(depths, times, color=DANGER, lw=2, marker="o", ms=5, zorder=5)
    twin.set_ylabel("milliseconds", fontsize=10, color=DANGER)
    twin.tick_params(labelsize=9, colors=TEXT_MUTE)
    for spine in ("top", "left"):
        twin.spines[spine].set_visible(False)

    ax2 = _blank_axes(fig, [0.60, 0.27, 0.34, 0.55], face=CARD)
    for spine in ax2.spines.values():
        spine.set_visible(True)
        spine.set_color(CARD_BORDER)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.text(0.09, 0.92, "Even depths only", fontsize=12.5, color=ACCENT,
             fontweight="bold", va="top")
    parity = data["parity"]
    ax2.text(0.09, 0.81, _wrap(
        "A leaf is scored right after somebody moved, and the evaluation has "
        "no idea a reply is coming -- so whoever moved last always looks "
        "better than they are. A search ending on our own move inherits that "
        "flattery whole.\n\n"
        "Stepping two plies at a time ends every search on the opponent's "
        "reply, which cancels it. Halving the number of iterations pays for "
        "the coarser steps, so it costs no depth:\n\n"
        f"over {parity['positions']} positions at the same budget, "
        f"{parity['even']['depth']:.1f} plies stepping by two against "
        f"{parity['every']['depth']:.1f} stepping by one.", 33),
        fontsize=9.3, color=TEXT_MAIN, va="top")

    return _wrap(
        "Depth 2, then 4, then 6... keeping the best move of the last "
        "completed depth, so a search cut off by the clock falls back on a "
        "finished answer rather than a half-formed one. Each iteration also "
        "leaves its ordering behind for the next, which is why the deeper "
        "ones cost less than their size suggests.")


def panel_table(fig, data):
    deep = data["deepening"]
    budget = data["table_budget"]

    ax = fig.add_axes([0.075, 0.42, 0.36, 0.26])
    ax.set_facecolor(BG)
    _hbars(ax, ["without the table", "with the table"],
           [budget["without"], budget["with"]],
           [f"{budget['without']:.1f}", f"{budget['with']:.1f}"],
           colors=[DANGER, SUCCESS],
           xlabel=f"plies reached in {data['budget']:.2f} s"
                  f" ({budget['positions']} positions)")

    ax2 = _blank_axes(fig, [0.50, 0.27, 0.44, 0.55], face=CARD)
    for spine in ax2.spines.values():
        spine.set_visible(True)
        spine.set_color(CARD_BORDER)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.text(0.06, 0.93, "Keeping what was already worked out",
             fontsize=12.5, color=ACCENT, fontweight="bold", va="top")
    ax2.text(0.06, 0.82, _wrap(
        "Playing A then B leaves the goban exactly as playing B then A does, "
        "so a plain tree search solves the same position over and over. Each "
        "result is filed under a Zobrist key -- one 64-bit number updated by "
        "a single xor whenever a stone, a capture counter or the turn "
        "changes -- and every later path that lands there stops.\n\n"
        "The table also survives from one move of the game to the next. The "
        "tree itself cannot: the opponent's reply moves the root. But its "
        "conclusions are keyed by position, not by path, so whatever the "
        "opponent plays, everything already proved about the positions still "
        "reachable is still there.", 48),
        fontsize=9.5, color=TEXT_MAIN, va="top")
    ax2.text(0.06, 0.16,
             f"{deep['table_entries']:,} positions filed  ·  "
             f"{deep['table_hits']:,} lookups answered".replace(",", " "),
             fontsize=10, color=ACCENT, fontweight="bold")

    return ("At a fixed shallow depth the table barely pays: too few "
            "positions repeat for the lookup to earn itself back. Under the "
            "real budget, where the search goes as deep as it can, positions "
            "start repeating and it is worth about a ply.")


def panel_ablations(fig, data):
    cases = data["ablations"]["cases"]
    ax = fig.add_axes([0.26, 0.30, 0.66, 0.50])
    ax.set_facecolor(BG)
    colors = [SUCCESS if case["cost"] >= 1.15 else
              (TEXT_MUTE if case["cost"] >= 0.95 else DANGER)
              for case in cases]
    _ratio_bars(ax, [case["name"] for case in cases],
                [case["cost"] for case in cases], colors,
                "how much slower the same search is without it"
                "  --  left of the line means it costs time")

    return _wrap(
        f"Each one switched off and the same depth-{data['ablations']['depth']} "
        f"search run again. Grey and red bars "
        f"are pieces the engine is faster without -- they stay in because "
        f"they buy correct play rather than speed: the tactical promotion "
        f"stops the engine dropping the only move that blocks a five, and the "
        f"table earns its keep under a clock rather than at a fixed depth.")


def panel_micro(fig, data):
    micro = data["micro"]
    ax = fig.add_axes([0.26, 0.32, 0.66, 0.46])
    ax.set_facecolor(BG)
    _hbars(ax, [m["name"] for m in micro],
           [m["speedup"] for m in micro],
           [f"{m['speedup']:.0f}x" for m in micro],
           xlabel="engine version against the obvious version")
    ax.set_xscale("log")
    ax.set_xlim(1, max(m["speedup"] for m in micro) * 3)

    return _wrap(
        "The obvious way to compute each of these lives in viz/naive.py, and "
        "the tests check that it returns exactly what the engine returns -- "
        "otherwise the comparison would be measuring two different things. "
        "Scoring is the extreme case: the evaluator keeps one score per line "
        "and refreshes only the four lines a changed cell belongs to, instead "
        "of re-reading the goban.")


def panel_depths(fig, data):
    survey = data["survey"]
    counts = {}
    for row in survey:
        counts[row["depth"]] = counts.get(row["depth"], 0) + 1
    depths = sorted(counts)

    ax = fig.add_axes([0.075, 0.30, 0.50, 0.50])
    ax.set_facecolor(BG)
    ax.bar(depths, [counts[d] for d in depths], width=1.2, zorder=3,
           color=[SUCCESS if d >= 10 else SOFT for d in depths],
           edgecolor=CARD_BORDER, lw=0.8)
    for d in depths:
        ax.text(d, counts[d] + 0.15, str(counts[d]), ha="center", fontsize=9,
                color=TEXT_MUTE)
    ax.axvline(9, color=DANGER, lw=1.4, ls="--", zorder=5)
    ax.text(8.8, max(counts.values()) * 1.02, "the subject asks for 10",
            fontsize=9.5, color=DANGER, ha="right")
    ax.set_xlabel("plies reached", fontsize=10, color=TEXT_MUTE)
    ax.set_ylabel("positions", fontsize=10, color=TEXT_MUTE)
    ax.set_xticks(depths)
    ax.tick_params(labelsize=9, colors=TEXT_MUTE)
    ax.grid(axis="y", color=CARD_BORDER, lw=0.5, alpha=0.5, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    contested = [row for row in survey if not row["solved"]]
    reached = sum(1 for row in contested if row["depth"] >= 10)
    ax2 = _blank_axes(fig, [0.62, 0.30, 0.32, 0.50], face=CARD)
    for spine in ax2.spines.values():
        spine.set_visible(True)
        spine.set_color(CARD_BORDER)
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    stats = [
        (f"{reached}/{len(contested)}", "contested positions\nreaching 10+"),
        (f"{max(row['depth'] for row in survey)}", "deepest search"),
        (f"{len(survey) - len(contested)}", "solved outright,\nso stopped early"),
    ]
    for i, (value, label) in enumerate(stats):
        y = 0.86 - i * 0.30
        ax2.text(0.10, y, value, fontsize=21, color=ACCENT, fontweight="bold")
        ax2.text(0.10, y - 0.09, label, fontsize=9, color=TEXT_MUTE, va="top")

    return _wrap(
        f"{len(survey)} positions taken from games played out at random. The "
        f"pale bars are not failures: those searches proved a forced win and "
        f"stopped, because no deeper search could say anything new.\n\n"
        f"Depth is bought, not found. The same engine set ten moves wide at "
        f"every ply reaches only four or five plies and still wins 18 of 24 "
        f"games against this one: extra plies mostly re-measure the same "
        f"shapes, so width helps a static evaluation more than depth does. "
        f"The subject grades depth, so depth is what the beam is tuned for; "
        f"both settings are in ai/config.py with the measurements behind "
        f"them.")


PANELS = [
    ("How a move is chosen", "the four stages, and the funnel", panel_overview),
    ("Where it may look", "several rectangles, not one box", panel_space),
    ("How crowded a cell is", "counted once, then kept up to date", panel_proximity),
    ("The shortlist", "cheap first, and one thing checked properly", panel_shortlist),
    ("The real ranking", "play it, score it, take it back", panel_ranking),
    ("Alpha-beta", "not looking at what cannot matter", panel_alphabeta),
    ("The beam", "wide where it decides, narrow where it confirms", panel_beam),
    ("Iterative deepening", "two plies at a time, until the clock stops it",
     panel_deepening),
    ("The transposition table", "the same position, reached twice", panel_table),
    ("Every optimisation, weighed", "measured by removing it", panel_ablations),
    ("Cost of the operations", "against the obvious implementation", panel_micro),
    ("How deep it gets", "over positions from real games", panel_depths),
]


# ---------- the deck ----------


def render_panel(fig, data, at):
    """Draw panel `at` into `fig`, chrome included. Used by the deck and the PDF."""
    title, subtitle, panel = PANELS[at]

    fig.text(0.06, 0.945, title, fontsize=22, color=TEXT_MAIN,
             fontweight="bold", va="center")
    fig.text(0.06, 0.893, subtitle, fontsize=12, color=TEXT_MUTE, va="center")
    fig.text(0.94, 0.945, f"{at + 1} / {len(PANELS)}", fontsize=12,
             color=TEXT_MUTE, ha="right", va="center")

    rail = fig.add_axes([0.06, 0.858, 0.88, 0.006])
    rail.set_xticks([])
    rail.set_yticks([])
    rail.set_facecolor(SOFT)
    for spine in rail.spines.values():
        spine.set_visible(False)
    rail.add_patch(Rectangle((0, 0), (at + 1) / len(PANELS), 1,
                             facecolor=ACCENT, edgecolor="none"))

    caption = panel(fig, data)
    if caption:
        fig.text(0.06, CAPTION_Y, _wrap(caption, CAPTION_WIDTH), fontsize=10.5,
                 color=TEXT_MAIN, va="top", linespacing=1.45)


def save_pdf(data, path):
    """The whole deck as one PDF, one panel per page."""
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(path) as pdf:
        for at in range(len(PANELS)):
            fig = plt.figure(figsize=(14, 8.5), facecolor=BG)
            render_panel(fig, data, at)
            pdf.savefig(fig, facecolor=BG)
            plt.close(fig)


class Deck:
    """The window: chrome, navigation, and one panel at a time."""

    def __init__(self, data):
        self.data = data
        self.at = 0
        self.fig = plt.figure(figsize=(14, 8.5), facecolor=BG)
        self.fig.canvas.manager.set_window_title("Gomoku - how the engine thinks")
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self._draw()

    # -- navigation

    def _on_key(self, event):
        if event.key in ("right", "down", " ", "n"):
            self.go(1)
        elif event.key in ("left", "up", "p"):
            self.go(-1)
        elif event.key in ("q", "escape"):
            plt.close(self.fig)
        elif event.key == "home":
            self.at = 0
            self._draw()
        elif event.key == "end":
            self.at = len(PANELS) - 1
            self._draw()

    def go(self, step):
        self.at = max(0, min(len(PANELS) - 1, self.at + step))
        self._draw()

    # -- drawing

    def _draw(self):
        self.fig.clear()
        render_panel(self.fig, self.data, self.at)
        self._buttons()
        self.fig.canvas.draw_idle()

    def _buttons(self):
        # Kept on the instance: matplotlib drops widgets that are not
        # referenced, and the callbacks stop firing.
        self._prev_ax = self.fig.add_axes([0.755, 0.012, 0.085, 0.042])
        self._next_ax = self.fig.add_axes([0.850, 0.012, 0.085, 0.042])
        self.prev = Button(self._prev_ax, "< Back", color="#EAD8B0",
                           hovercolor="#D6C098")
        self.next = Button(self._next_ax, "Next >", color="#D4E4EA",
                           hovercolor="#B8D0DA")
        for button in (self.prev, self.next):
            button.label.set_fontsize(10)
            button.label.set_color(TEXT_MAIN)
        self.prev.on_clicked(lambda _event: self.go(-1))
        self.next.on_clicked(lambda _event: self.go(1))
        self.fig.text(0.06, 0.028,
                      "arrow keys to move  ·  Q to quit", fontsize=9,
                      color=TEXT_MUTE)


def show(data):
    Deck(data)
    plt.show()
