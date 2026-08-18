"""Tunable knobs for the engine.

Everything the search can be tweaked with lives here so that experimenting
does not require touching the algorithms themselves.
"""

# ---------- time control ----------

# Wall clock a single move may spend thinking, with a margin kept for the
# bookkeeping that follows the search. The 42 subject caps a move at 0.5s,
# which means TIME_BUDGET = 0.45; the value below trades that compliance for
# roughly one extra ply of depth.
TIME_BUDGET = 0.85

# Hard ceiling on iterative deepening. Reaching it means the position is
# simple enough that going deeper is pointless.
MAX_DEPTH = 10

# ---------- search space ----------

# Two stones closer than this (Chebyshev distance) belong to the same cluster.
CLUSTER_RADIUS = 3

# Cells added around a cluster's bounding box: the playable border.
WINDOW_MARGIN = 2

# Two windows are merged when the area their union wastes stays below this
# fraction of the union. Higher = fewer, fatter windows.
MAX_WASTE_RATIO = 0.30

# ---------- branching ----------

# Cells kept after the cheap proximity pre-ranking, then after the full
# evaluation ordering. The root is allowed to look a bit wider.
SHORTLIST_SIZE = 20
BRANCHING = 10
ROOT_BRANCHING = 16
