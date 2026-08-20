"""Gomoku engine.

    ai.engine         minimax + alpha-beta, iterative deepening
    ai.transposition  what the search already knows about a position
    ai.zobrist        the keys that table is indexed by
    ai.shapes         local shape questions, read off the lines
    ai.reporting      terminal trace of the depths reached
    ai.search_space   the rectangular windows the search is restricted to
    ai.state          undoable game copy used as a search node
    ai.evaluation     incremental, line by line board scoring
    ai.patterns       what a shape is worth
    ai.lines          pre-computed line geometry
    ai.config         every tunable constant
"""

from .engine import choose_move, reset_tables
from .reporting import print_search_summary

__all__ = ["choose_move", "print_search_summary", "reset_tables"]
