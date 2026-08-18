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
- **Endgame capture**: aligning five does not win immediately. It
  becomes a *pending* win — the opponent has one turn to break every
  alignment via capture, or win by capture themselves. Otherwise the
  aligning player wins on the opponent's turn.
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
| `rules.py`    | Move legality: free-threes, double-three ban.           |
| `game.py`     | Turn order, capture counters, timers, win resolution.   |
| `ui.py`       | matplotlib canvas, drawing, input handling.             |
| `ai/`         | The engine — see [The AI](#the-ai).                     |

Each module has one clear responsibility. `board.py` is pure state and
geometry — no notion of turns. `rules.py` reads the board and answers
"is this move legal?". `game.py` is the only thing that mutates state
per turn. `ui.py` is the only thing that touches matplotlib. `ai/` only
reads a `Game` and answers with a move — it never mutates it.

## The AI

`ai.choose_move(game)` returns the move to play. The same call serves the
AI players and the human hint.

| Module               | Role                                                    |
| -------------------- | ------------------------------------------------------- |
| `ai/engine.py`       | Minimax (negamax) + alpha-beta + iterative deepening.   |
| `ai/search_space.py` | Rectangular windows and candidate move ranking.         |
| `ai/state.py`        | Undoable copy of a game, used as a search node.         |
| `ai/evaluation.py`   | Incremental, line-by-line board scoring.                |
| `ai/patterns.py`     | What a shape is worth.                                  |
| `ai/lines.py`        | Pre-computed line geometry of the goban.                |
| `ai/reporting.py`    | Terminal trace of the depths reached.                   |
| `ai/config.py`       | Every tunable constant.                                 |

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
- **Two-stage move ordering.** A cheap proximity pass keeps the
  `SHORTLIST_SIZE` most crowded cells of the windows; those are then
  really played and scored, and the best `BRANCHING` of them are
  searched. At the last ply that score *is* the leaf value, so ordering
  and evaluation are the same pass.
- **Iterative deepening.** Depth 1, then 2, then 3... keeping the best
  move of the last *completed* depth. The search stops once
  `TIME_BUDGET` is spent, so the move played is always the product of a
  full search. The previous depth's best move is tried first at the next
  depth.
- **Incremental evaluation.** A full board scan per node is far too
  expensive, so the evaluator keeps one score per line and refreshes
  only the four lines a changed cell belongs to. Playing and taking back
  a move costs a handful of line re-scores, and identical lines are
  memoised.
- **Early exit** on a proven win or loss: a deeper search cannot say
  anything new.

### Time control

`TIME_BUDGET` in `ai/config.py` is the wall clock a move may spend
thinking, a margin kept aside for the bookkeeping that follows the
search. It is set to **0.85s**, for a move capped at 0.9s. Note that the
42 subject asks for 0.5s per move: `TIME_BUDGET = 0.45` restores that,
at the cost of roughly one ply of depth.

In practice the engine reaches depth 4 in the middlegame, and much
deeper when the position is forcing.

### Watching it think

The board is a matplotlib window, so the search reports to the terminal
instead. Every move prints the depths as they complete, and the end of
the session prints the deepest search reached:

```
Black searching: 1 2 3 4   -> (8, 9) in 0.85s (depth 4)
White searching: 1 2 3 4 5   -> (7, 10) in 0.61s (depth 5)

Engine: 26 moves searched, deepest search reached depth 5.
```

A move that ends early -- an opening move, or a forced win found at
depth 3 -- simply lists fewer depths.

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
- [x] **Move suggestion / hint mode** — same engine, one call.
- [x] **Human vs AI and AI vs AI modes**, colour choice at game start.
- [x] **Performance display** — think time per move, per player.

### Possible improvements

- [ ] **Transposition table** — the same position is reached through
      several move orders and is searched again every time.
- [ ] **Threat-space search** — following forcing moves past the nominal
      depth would find longer forced wins.
- [ ] **Tuning the pattern table** by self-play; the current values are
      hand-picked, not fitted.


## Sanity checks

--> Github workflow
