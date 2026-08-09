"""Heuristics for the Ball Sort domain (design doc, Section 3).

Notation (for a state s):
  run           maximal contiguous same-colour block inside one tube
  R(s)          total number of runs over all tubes
  n_ne(s)       number of non-empty tubes
  N             number of colours
  D(s)          number of DISTINCT colours that appear at the bottom
                (index 0) of some tube

The five heuristics, with their design-doc definitions rewritten in the
per-tube form actually implemented here (the equivalences are one-liners
and are asserted in the test suite):

  h1 = sum_t max(0, runs(t) - 1)            = R - n_ne
  h2 = sum_c (tubes(c) - 1)                 = sum_t distinct(t) - N
  h3 = sum_c (runs(c) - 1)                  = R - N
  h4 = sum_c (runs(c) - bottom(c))          = R - D
  h5 = # balls strictly above the bottom run of their tube
     = sum_t (height(t) - bottom_run_len(t))

Admissibility / consistency claims (to be VERDICTED by the oracle, not
assumed):  h1..h4 admissible+consistent under cost model M1 (and hence M2,
since M2 edge costs are >= M1's);  h5 admissible+consistent under M2 only,
deliberately inadmissible under M1.

INCREMENTAL EVALUATION
  h1, h2, h3, h5 are sums of per-tube contributions, and a move touches
  exactly two tubes, so:
      h(child) = h(parent) - contrib(parent[src]) - contrib(parent[dst])
                           + contrib(child[src])  + contrib(child[dst])
  This is O(C) per move -- constant for a fixed instance, no full rescan.
  h4 = R - D: R updates the same way; D needs one O(T) scan of the tube
  bottoms of parent and child.  So h4's update is O(T + C).

  When CHECK_INCREMENTAL is True every incremental result is cross-checked
  against a from-scratch evaluation (used in the test suite; off in
  experiments).
"""

from __future__ import annotations

from .domain import (State, Move, tube_height, runs_in_tube, bottom_run_len)

# Flip to True in tests to verify every incremental update from scratch.
CHECK_INCREMENTAL = False


class Heuristic:
    """Base class.  Subclasses set the metadata and implement either
    `_tube_contrib` + `_offset` (per-tube-decomposable case) or override
    `h` and `h_incremental` directly."""

    name = "h?"
    # Cost models under which the claims hold, e.g. ("M1", "M2").
    admissible_under: "tuple[str, ...]" = ()
    consistent_under: "tuple[str, ...]" = ()

    def h(self, s: State) -> int:
        raise NotImplementedError

    def h_incremental(self, parent_h: int, parent: State, move: Move,
                      child: State) -> int:
        raise NotImplementedError

    # -- shared machinery for per-tube-decomposable heuristics ---------- #

    def _tube_contrib(self, tube: bytes) -> int:
        raise NotImplementedError

    def _offset(self, s: State) -> int:
        return 0

    def _h_decomposable(self, s: State) -> int:
        total = 0
        for t in s:
            total += self._tube_contrib(t)
        return total + self._offset(s)

    def _h_inc_decomposable(self, parent_h: int, parent: State, move: Move,
                            child: State) -> int:
        a, b = move.src, move.dst
        out = (parent_h
               - self._tube_contrib(parent[a]) - self._tube_contrib(parent[b])
               + self._tube_contrib(child[a]) + self._tube_contrib(child[b]))
        if CHECK_INCREMENTAL:
            fresh = self.h(child)
            assert out == fresh, (
                f"{self.name} incremental={out} scratch={fresh} move={move}")
        return out


class H0(Heuristic):
    """The zero heuristic (turns A* into UCS / BFS)."""
    name = "h0"
    admissible_under = ("M1", "M2")
    consistent_under = ("M1", "M2")

    def h(self, s: State) -> int:
        return 0

    def h_incremental(self, parent_h, parent, move, child) -> int:
        return 0


class H1(Heuristic):
    """h1 = sum_t max(0, runs(t) - 1): every non-bottom run of a tube must
    leave that tube at least once."""
    name = "h1"
    admissible_under = ("M1", "M2")
    consistent_under = ("M1", "M2")

    def _tube_contrib(self, tube: bytes) -> int:
        r = runs_in_tube(tube)
        return r - 1 if r > 1 else 0

    def h(self, s: State) -> int:
        return self._h_decomposable(s)

    h_incremental = Heuristic._h_inc_decomposable


class H2(Heuristic):
    """h2 = sum_c (tubes(c) - 1) = sum_t distinct(t) - N: each colour spread
    over t tubes needs >= t-1 consolidating moves under G_strict."""
    name = "h2"
    admissible_under = ("M1", "M2")
    consistent_under = ("M1", "M2")

    def __init__(self):
        self._n_colors = None   # inferred lazily; equals N of the instance

    def _tube_contrib(self, tube: bytes) -> int:
        # number of distinct colours in the tube
        seen = 0
        distinct = 0
        for x in tube:
            if x == 0:
                break
            bit = 1 << x
            if not (seen & bit):
                seen |= bit
                distinct += 1
        return distinct

    def _offset(self, s: State) -> int:
        # subtract N = number of distinct colours present in the state.
        # For a well-formed instance every colour is present, so this is N;
        # computing it from the state keeps the class instance-agnostic.
        seen = 0
        for t in s:
            for x in t:
                if x == 0:
                    break
                seen |= 1 << x
        return -bin(seen).count("1")

    def h(self, s: State) -> int:
        return self._h_decomposable(s)

    def h_incremental(self, parent_h, parent, move, child) -> int:
        # The offset (-N) is identical for parent and child: colours are
        # never created or destroyed by a move.  So the decomposable update
        # is exact as long as we cancel the offsets, which it does, because
        # parent_h already contains -N and the four contrib terms don't.
        a, b = move.src, move.dst
        out = (parent_h
               - self._tube_contrib(parent[a]) - self._tube_contrib(parent[b])
               + self._tube_contrib(child[a]) + self._tube_contrib(child[b]))
        if CHECK_INCREMENTAL:
            fresh = self.h(child)
            assert out == fresh, (
                f"{self.name} incremental={out} scratch={fresh} move={move}")
        return out


class H3(Heuristic):
    """h3 = R - N: total runs minus colours.  Dominates h1 and h2."""
    name = "h3"
    admissible_under = ("M1", "M2")
    consistent_under = ("M1", "M2")

    def _tube_contrib(self, tube: bytes) -> int:
        return runs_in_tube(tube)

    def _offset(self, s: State) -> int:
        seen = 0
        for t in s:
            for x in t:
                if x == 0:
                    break
                seen |= 1 << x
        return -bin(seen).count("1")

    def h(self, s: State) -> int:
        return self._h_decomposable(s)

    def h_incremental(self, parent_h, parent, move, child) -> int:
        a, b = move.src, move.dst
        out = (parent_h
               - self._tube_contrib(parent[a]) - self._tube_contrib(parent[b])
               + self._tube_contrib(child[a]) + self._tube_contrib(child[b]))
        if CHECK_INCREMENTAL:
            fresh = self.h(child)
            assert out == fresh, (
                f"{self.name} incremental={out} scratch={fresh} move={move}")
        return out


class H4(Heuristic):
    """h4 = R - D, where D = # distinct colours appearing at some tube
    bottom.  Rationale: at most one run of colour c can avoid ever moving,
    and only a bottom run can.  Dominates h3 because D <= N."""
    name = "h4"
    admissible_under = ("M1", "M2")
    consistent_under = ("M1", "M2")

    @staticmethod
    def _D(s: State) -> int:
        seen = 0
        for t in s:
            x = t[0]
            if x:
                seen |= 1 << x
        return bin(seen).count("1")

    def h(self, s: State) -> int:
        R = 0
        for t in s:
            R += runs_in_tube(t)
        return R - self._D(s)

    def h_incremental(self, parent_h, parent, move, child) -> int:
        a, b = move.src, move.dst
        # R updates per-tube; D is rescanned over the T tube bottoms (O(T)).
        dR = (runs_in_tube(child[a]) + runs_in_tube(child[b])
              - runs_in_tube(parent[a]) - runs_in_tube(parent[b]))
        out = parent_h + dR - self._D(child) + self._D(parent)
        if CHECK_INCREMENTAL:
            fresh = self.h(child)
            assert out == fresh, (
                f"{self.name} incremental={out} scratch={fresh} move={move}")
        return out


class H5(Heuristic):
    """h5 = # balls strictly above the bottom run of their tube.
    Admissible + consistent under M2 (each such ball must move at least
    once, at cost 1 per ball).  DELIBERATELY inadmissible under M1 -- used
    there as the inadmissible heuristic for WA*/GBFS/beam."""
    name = "h5"
    admissible_under = ("M2",)
    consistent_under = ("M2",)

    def _tube_contrib(self, tube: bytes) -> int:
        h = tube_height(tube)
        if h == 0:
            return 0
        return h - bottom_run_len(tube)

    def h(self, s: State) -> int:
        return self._h_decomposable(s)

    h_incremental = Heuristic._h_inc_decomposable


ALL_HEURISTICS = {cls.name: cls for cls in (H0, H1, H2, H3, H4, H5)}


def make(name: str) -> Heuristic:
    return ALL_HEURISTICS[name]()
