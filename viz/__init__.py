"""How the engine chooses a move, explained by a live engine.

    make viz

`viz.measure` runs the real search and records what it did -- the funnel of
candidates, the tree it walked, the depths it completed, the cost of each
optimisation switched off. `viz.studio` draws that as five interactive
chapters over a position you build yourself; `viz.explore` is the smaller,
older view of what the engine sees; `viz.show` is the same measurements as a
fixed report. `viz.naive` holds the obvious, slow way to compute the things
the engine computes cleverly, so a comparison can put a number on each
optimisation instead of asserting it helps.

Nothing here is imported by the game or by the engine.
"""
