# Gomoku — 42 Project

Two-player, same-machine Gomoku on a 19×19 goban with captures, endgame
capture, and the double-three ban. Written in Python with a pure
matplotlib UI.

This is the 42 `gomoku` project. The AI
part is on the roadmap (see [TODO](#todo)); the rules engine and UI are
complete.

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

Flat layout — five short modules, no package indirection.

| File          | Role                                                    |
| ------------- | ------------------------------------------------------- |
| `gomoku.py`   | Entry point. Wires a `Game` to a `GomokuUI`.            |
| `board.py`    | `Board` grid + capture detection + alignment scanning.  |
| `rules.py`    | Move legality: free-threes, double-three ban.           |
| `game.py`     | Turn order, capture counters, timers, win resolution.   |
| `ui.py`       | matplotlib canvas, drawing, input handling.             |

Each module has one clear responsibility. `board.py` is pure state and
geometry — no notion of turns. `rules.py` reads the board and answers
"is this move legal?". `game.py` is the only thing that mutates state
per turn. `ui.py` is the only thing that touches matplotlib.

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

What the 42 subject still asks for. Ordered by priority.

### Mandatory

- [ ] **AI opponent (min-max with alpha-beta pruning).**
      Plug into `Game.play(r, c)` from a controller loop — the rest of
      the code doesn't need to change. Needs a heuristic that
      recognizes free-threes, four-threats, captures, and the pending
      alignment state.
- [ ] **0.5s move time cap for the AI.** Iterative deepening so the
      search returns the best move found so far when time runs out.
- [ ] **Move suggestion / hint mode.** Reuse the AI to highlight a
      recommended move for the human player.
- [ ] **Human vs AI and AI vs AI modes** in the UI — colour choice at
      game start.
- [ ] **Performance display** — show the AI's think time per move
      (already have the plumbing for human timing; extend it).


## Sanity checks

--> Github workflow
