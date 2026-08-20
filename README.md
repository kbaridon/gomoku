# Gomoku — 42 Project

Gomoku on a 19×19 goban with captures, endgame capture, and the
double-three ban. Written in Python with a pure matplotlib UI and a
minimax / alpha-beta engine.

This is the 42 `gomoku` project. Rules engine, UI and AI are complete:
play human vs human, human vs AI or AI vs AI.

## Getting started

```bash
make        # create .venv + install deps
make run    # launch the game
make viz    # the studio: one position, five ways of taking it apart

# or manually:
source .venv/bin/activate && python gomoku.py
```

Click an intersection to place a stone. `R` restarts, `Q` quits. The
same actions are also available as buttons in the bottom-right of the
window.

## Rules implemented

All rules from the subject except the AI:

- **19×19 board**, unlimited stones, Black plays first, turns alternate.
- **Win by alignment** of five *or more* stones on any axis.
- **Captures** by flanking a pair (`X O O X`) — only pairs, never
  singles or triples. Checked in all eight unit directions from the
  placed stone. Self-capture is impossible: placing between two
  opponent stones does not remove your own stone.
- **Win by capture** at 10 captured opponent stones.
- **Endgame capture**: aligning five wins immediately *only when nothing
  can answer it*. If a capture could take a stone out of the row, or the
  opponent is within one move of ten captured stones, the win is
  *pending* instead and they get their turn to try. A turn that cannot
  change the result is not offered — the game just ends.
- **Double-three forbidden**: any move creating ≥ 2 free-threes is
  rejected, *unless* the same move captures at least one pair (subject
  appendix).

## UI overview

- **Board (left):** goban colors, 4-4 / 10-10 / 16-16 hoshi, columns
  A–S, rows 1–19, red dot on the last move.
- **Status card:** current player with stone icon and live thinking
  clock. Turns orange with `! break the line or you lose !` when the
  mover is under a pending-alignment threat.
- **Player cards:** one per color, active player highlighted. Shows
  moves played, per-player average time, capture count as `N / 10` and
  a green→red progress bar (red at 8/10 — danger zone).
- **Timing card:** last-move time per color, total moves, overall
  average in bold.
- **Game end:** big centered banner over a dimmed board with winner,
  win reason, final average and total moves.

## Architecture

Flat layout for the game, one package for the engine.

| File          | Role                                                    |
| ------------- | ------------------------------------------------------- |
| `gomoku.py`   | Entry point. Wires a `Game` to a `GomokuUI`.            |
| `board.py`    | `Board` grid + capture detection + alignment scanning.  |
| `rules.py`    | Move legality, and whether a stone can be captured.     |
| `game.py`     | Turn order, capture counters, timers, win resolution.   |
| `ui.py`       | matplotlib canvas, drawing, input handling.             |
| `ai/`         | The engine — see [The AI](#the-ai).                     |
| `viz/`        | `make viz` — the studio: how a move gets chosen.        |

Each module has one clear responsibility. `board.py` is pure state and
geometry — no notion of turns. `rules.py` reads the board and answers
"is this move legal?". `game.py` is the only thing that mutates state
per turn. `ui.py` is the only thing that touches matplotlib. `ai/` only
reads a `Game` and answers with a move — it never mutates it.

## The AI

`ai.choose_move(game)` returns the move to play. The same call serves the
AI players and the human hint.

| Module                | Role                                                   |
| --------------------- | ------------------------------------------------------ |
| `ai/engine.py`        | Negamax + alpha-beta + iterative deepening + the beam. |
| `ai/search_space.py`  | Rectangular windows and candidate move ranking.        |
| `ai/state.py`         | Undoable copy of a game, used as a search node.        |
| `ai/evaluation.py`    | Incremental, line-by-line board scoring.               |
| `ai/shapes.py`        | Double-three ban and five-in-a-row, read off the lines.|
| `ai/patterns.py`      | What a shape is worth.                                 |
| `ai/lines.py`         | Pre-computed line and neighbourhood geometry.          |
| `ai/transposition.py` | What the search already knows about a position.        |
| `ai/zobrist.py`       | The keys that table is indexed by.                     |
| `ai/reporting.py`     | Terminal trace of the depths reached.                  |
| `ai/config.py`        | Every tunable constant.                                |

### Search space — multiple rectangular windows

Looking at all 361 intersections is hopeless, and the usual single
bounding box around every stone wastes most of its area as soon as the
game spreads to two corners. So the space is a *set* of rectangles:

1. stones within Chebyshev distance `CLUSTER_RADIUS` of each other are
   grouped into clusters;
2. each cluster gives one rectangle — its bounding box;
3. two rectangles are merged only while their union wastes less than
   `MAX_WASTE_RATIO` of its own area, so a local fight keeps its own
   small window instead of being swallowed by a distant one;
4. each surviving window is grown by `WINDOW_MARGIN`, the border where
   the next stone is likely to land.

Four stones in two opposite corners give two windows of about 30 cells
instead of one box of 361. The windows are computed once per turn: the
few stones the search adds always fall inside them or in their margin.

### Algorithm — alpha-beta minimax

Negamax form: a single routine handles both sides by negating the value
returned by the deeper call. On top of the plain algorithm:

- **Alpha-beta pruning** — branches that cannot change the result are
  cut. The payoff depends entirely on move ordering, hence the next
  point.
- **Two-stage move ordering.** A cheap proximity pass shortlists the
  most crowded cells of the windows; those are then really played and
  scored, and the best of them are searched. At the last ply that score
  *is* the leaf value, so ordering and evaluation are the same pass.
  Proximity counts neighbours, not lines, so before anything is cut, the
  cells about to go are checked for one thing: would a stone there make a
  line of `CRITICAL_RUN` for *either* colour? Those go to the front.
  Without it the engine is blind in a specific and fatal way — the move
  that turns a three into an open four has one neighbour, while the cells
  alongside the three have three each, so neither side generated the
  winning extension and games ran to a quick alignment. That check looks
  only `TACTICAL_TAIL` places past the cut, which is a compromise and not
  good enough for the one move that must never be missed: the cells that
  complete a *five* come from `Evaluator.decisive_cells`, which knows
  where they are without ranking anything and rescues them from anywhere.
  A capture that reaches ten stones is rescued the same way, and had the
  same bug: the cell completing it has one neighbour and makes a run of
  three, so with the opponent at eight captured stones the engine would
  answer at the far end of the board and lose on the spot.
- **An asymmetric evaluation.** The opponent's shapes weigh
  `DEFENCE_WEIGHT` times one's own. A symmetric score makes building a
  three and blocking a three come out even; they are not even, because
  whoever ignores the other's three loses the tempo.
- **A narrowing beam.** A node expands `BRANCHING_BY_PLY[ply]` moves:
  sixteen at the root, then four, three, and two from the fourth ply on.
  Width matters where the move is chosen; deep down the line is already
  committed. A flat width of ten cannot reach ten plies in half a second
  — this is the single change that makes the depth possible, and those
  widths are the widest that still get there.
- **Transposition table.** Positions reached by different move orders
  are the same position. Results are filed under a Zobrist key and
  reused, including from one move of the game to the next, which is
  worth about a ply.
- **Principal variation search.** After the first move of a node, the
  rest only have to prove they are *not* better, which a null window
  does far more cheaply. Only the rare move that beats it is re-searched.
- **Iterative deepening, two plies at a time.** Depth 2, then 4, then
  6... keeping the best move of the last *completed* depth. Even depths
  only: a leaf is scored right after somebody moved, so whoever moved
  last always looks better than they are, and ending on the opponent's
  reply cancels it. Halving the number of iterations pays for the
  coarser steps, so the depth reached is the same either way.
- **Incremental evaluation.** A full board scan per node is far too
  expensive, so the evaluator keeps one score per line and refreshes
  only the four lines a changed cell belongs to. Playing and taking back
  a move costs a handful of line re-scores, and identical lines are
  memoised.
- **Early exit** on a proven win or loss: a deeper search cannot say
  anything new.

`make viz ARGS=--panels` measures every one of these by switching it off
and running the same search again.

### Time control

`TIME_BUDGET` in `ai/config.py` is the wall clock a move may spend
thinking. It is set to **0.45s**, for a move capped at the 0.5s the
subject asks for; the rest is the margin the bookkeeping after the
search needs, since the deadline is only tested between nodes and the
last one still has to finish.

Measured over 32 positions taken from played-out games, the engine
reaches **ten plies or more in almost every position that is not already
decided**, and up to fourteen. The positions where it stops shallow are
the ones where it proved a forced win and had no reason to go on.

There is a real trade behind that, and it is worth stating plainly:
width helps a static evaluation more than depth does, because extra
plies mostly re-measure the same shapes. The same engine set ten moves
wide at every ply reaches only four or five plies and still wins **18 of
24 games** against this one. The subject grades depth, so depth is what
the beam is tuned for; `BRANCHING_BY_PLY` in `ai/config.py` carries both
settings and the measurements behind them, and switching is a one-line
change.

Measuring that is easy to get wrong. Both engines are deterministic, so
a duel from a handful of fixed openings is a dozen fixed outcomes rather
than a dozen samples: a 12-game run of the same pair gave the opposite
answer to the 24-game run over varied openings.

### Watching it think

The board is a matplotlib window, so the search reports to the terminal
instead. Every move prints the depths as they complete, and the end of
the session prints the deepest search reached:

```
Black searching: 2 4 6 8 10 12   -> (8, 9) in 0.45s (depth 12)
White searching: 2 4 6 8 10   -> (7, 10) in 0.45s (depth 10)

Engine: 26 moves searched, deepest search reached depth 14.
```

Depths step by two because the search only ends on the opponent's reply.
A move that ends early — an opening move, or a forced win found at depth
4 — simply lists fewer depths.

To see it think rather than read a running total, `make viz` opens the
studio: one position, which you build by clicking intersections, and
five chapters that each take it apart a different way. Every number in
them is measured on that position when you look at it — nothing is
stored, nothing is asserted.

| Chapter | What it shows |
| ------- | ------------- |
| **1 Candidates** | The funnel from 361 intersections down to the moves actually searched. Click a stage to see it drawn on the goban, and the beam's width ply by ply underneath. |
| **2 Alpha-beta** | The tree the search really walked. Click a move to follow it down; each node shows its alpha-beta window, which moves got a null window, which had to be re-searched, and which were generated but never looked at because a cutoff came first. |
| **3 Deepening** | Space steps one more depth. The budget bar fills in, and the best move changes — or does not — as the depth grows. |
| **4 Optimisations** | Click any row to switch that one optimisation off and re-run the same search on this position. Bars are drawn from 1x, so "costs time" runs left and "saves time" runs right. |
| **5 Evaluation** | Click an empty intersection to see exactly what a stone there would be worth: the four lines through it, the shapes on each before and after, and the `DEFENCE_WEIGHT` applied to the opponent's half. |

`make viz ARGS=--explore` is the smaller view of what the engine sees,
and `make viz ARGS=--panels` a fixed report of the same measurements;
`--save deck.pdf` writes that one out.

### Evaluation

A line is scored from one player's point of view as a string (`X` own,
`O` opponent, `.` empty, `#` edge of the board). Offensive shapes are
matched from the strongest down — five, open four, four, free three,
and so on — and the stones of a matched shape are masked out so that the
same stones are never counted twice. Capture weaknesses (`OXX.`) are
matched separately, without masking, because a pair can be both part of
a strong three and one move away from being captured. Captured stones
are worth a growing bonus, ten of them being a win.

The search plays by the real rules: captures, win by capture and the
"align five, then survive the opponent's answer" endgame are all
reproduced in `ai/state.py`. An alignment the opponent cannot break is
scored as an immediate win; a breakable one only wins if the opponent
fails to break it.

## Design choices

Notable calls where reasonable people would disagree:

1. **Pure matplotlib** — no seaborn. `mpl_connect` for input, `Circle`
   / `Rectangle` / `FancyBboxPatch` for the board and cards,
   `matplotlib.widgets.Button` for Restart / Quit, and
   `fig.canvas.new_timer` for the live clock.
2. **Captures counted in stones**, not pairs. The subject says "capture
   10 of your opponent's stones", so the threshold is 10 stones.
3. **Double-three exemption keyed on any capture.** Plain reading of
   the appendix: if the same move produces any captures, the
   double-three check is skipped.
4. **Pending-win state machine for endgame capture** — the game defers
   the win by one turn rather than trying to prove at move time whether
   the aligning player is "really" going to win.
5. **Coordinates `(row, col)` with row 0 at the top.** UI inverts the Y
   axis. Rows 1–19, columns A–S (continuous, not skipping I).
6. **Timer is thinking time until a legal move.** Illegal clicks do not
   stop the clock.
7. **Reset in place** — `R` calls `self.game.__init__()` so the UI's
   binding stays stable.
8. **Game-over is a full-board banner**, not a subtle sidebar note.
9. **No undo** — deliberately, to keep the timer meaningful. Reset is
   the escape hatch.

## TODO

### Done

- [x] **AI opponent** — minimax with alpha-beta pruning.
- [x] **Move time cap** — iterative deepening keeps the best move of the
      last completed depth. `TIME_BUDGET`, in `ai/config.py`.
- [x] **Ten plies deep** within the 0.5s cap, through a beam that
      narrows with depth. See [Time control](#time-control).
- [x] **Transposition table** — Zobrist-keyed, and kept from one move of
      the game to the next.
- [x] **Move suggestion / hint mode** — same engine, one call.
- [x] **Human vs AI and AI vs AI modes**, colour choice at game start.
- [x] **Performance display** — think time per move, per player.
- [x] **`make viz`** — the studio: five interactive chapters taking one
      position apart, every number measured live on it.

### Possible improvements

- [ ] **Quiescence on threats** — the leaf evaluation still has no idea
      a reply is coming, and stepping two plies at a time cancels the
      bias without removing it. Extending forcing lines past the nominal
      depth is the textbook fix and it was tried here: it lost **21-27**
      over 48 games, and **42-54** over 96 including a 26-22 control.
      The extension costs depth everywhere to fix a leaf that is only
      sometimes wrong. Worth revisiting, but only with a way to extend
      that does not spend the budget uniformly.
- [ ] **Recovering the width** — the engine is tuned for depth because
      the subject grades depth; a sharper evaluation would need less
      width to play as well, and would close the gap.
- [ ] **Tuning the pattern table** by self-play; the current values are
      hand-picked, not fitted. This is the most promising of the three:
      the evaluation, not the search, is what the engine is short of.


## Sanity checks

--> Github workflow
