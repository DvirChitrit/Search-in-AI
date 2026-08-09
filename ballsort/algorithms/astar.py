"""A* with the EARLY goal test (design doc 5.3 controls; Paper2earlylate).

This is the reference implementation whose OPEN discipline every later
algorithm copies verbatim:

  OPEN entry     = (f, -g, insertion_counter, node_index)   in a heapq
  tie-breaking   = f, then MAX g, then FIFO (Asai & Fukunaga 2017)
  duplicate det. = canonical key over OPEN u CLOSED, best-g per key
  goal test      = at GENERATION time (early), including s0 itself

NODE STORAGE.  heapq entries carry only an index into a side list
`nodes`; nodes hold (concrete_state, parent_index, move, g, h).  Keys are
canonical (design doc 2.8) but states are CONCRETE, and every generated
move is a legal move of the parent's concrete state -- so walking parent
pointers reconstructs a move sequence that Domain.validate_solution
accepts from the actual s0.  Canonicalization only merges *keys*; it
never touches the states we search over.

REOPENING (design doc 5.3 control #3).  `best_g` maps key -> cheapest g
known; `closed` is the set of expanded keys.  On generating a child whose
key has a strictly cheaper g than recorded: if the key is closed, it is
re-opened (removed from `closed`, counted in Stats.reopened) and pushed
again.  With a CONSISTENT heuristic this must never fire -- the theory
says the first expansion of a key already has optimal g -- so
`assert_no_reopen=True` turns the counter into a hard assertion (used in
the test gates; experiments count instead, per the M2 prompt).

Stale heap entries are handled lazily: an entry is skipped at pop time if
its key is already closed or its g is no longer the best known.  This is
the standard heapq idiom (no decrease-key); `open_max_size` therefore
counts live+stale entries, which is the honest measure of OPEN's actual
memory footprint.

CANON-TIME ACCOUNTING (design doc RQ1).  Every Domain.key() call in the
search is wrapped in a perf_counter() pair and counted, so canon_calls /
canon_time_s land in the CSV without a profiler.  Overhead: two
perf_counter() calls cost ~100-150 ns against a key() cost of ~1 us at
pilot sizes -- roughly 10-15% *of the canonicalization slice*, and only
a few percent of total wall time.  The measured overhead is quantified
in the calibration report; `canon_timing=False` disables the wrapping
(calls are still counted) if we ever need the last few percent.

EARLY-GOAL-TEST CAVEAT (flagged, then verified empirically by the oracle
gate): returning at generation is provably optimal when h(s)=0 only at
goals (true for h4 in this domain).  For heuristics with zero-plateaus
(h0..h3) a +1-suboptimal return is conceivable in theory under M1 when a
zero-h non-goal node wins the (f,-g) tie against the optimal path's
frontier.  The oracle gate asserts cost == h* exactly on thousands of
runs precisely to catch this if it occurs in practice.

Stdlib only (PyPy compatibility).
"""

from __future__ import annotations

import time
from heapq import heappush, heappop

from .base import Limits, Result, Stats

# Peak-RSS measurement is platform-specific.  `resource` is Unix-only
# (absent on Windows), so we degrade gracefully: Unix uses getrusage,
# Windows uses the Win32 API via ctypes, and anything else reports 0.0
# (RSS is a reported metric, never a correctness input -- the runner's
# hard memory cap is enforced separately and also platform-guarded).
try:
    import resource as _resource

    def _rss_mb() -> float:
        # ru_maxrss is KB on Linux, bytes on macOS.
        kb = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
        import sys
        return (kb / (1024.0 * 1024.0)) if sys.platform == "darwin" else (kb / 1024.0)
except ImportError:                                    # Windows
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        def _rss_mb() -> float:
            try:
                c = _PMC()
                c.cb = ctypes.sizeof(c)
                h = ctypes.windll.kernel32.GetCurrentProcess()
                if ctypes.windll.psapi.GetProcessMemoryInfo(
                        h, ctypes.byref(c), c.cb):
                    return c.PeakWorkingSetSize / (1024.0 * 1024.0)
            except Exception:
                pass
            return 0.0
    except Exception:
        def _rss_mb() -> float:
            return 0.0


class AStarEarly:
    """A*-EARLY.  One instance is stateless across solve() calls."""

    name = "astar_early"

    def __init__(self, assert_no_reopen: bool = False, canon_timing: bool = True,
                 goal_test: str = "early"):
        """goal_test="early" (default, design doc 5.3 control #2) tests
        children at generation; "late" tests at expansion -- the classic
        variant that keeps A* optimal under NON-unit costs (M2), where
        the early test provably may return suboptimal solutions (that gap
        is itself the RQ5 experiment; the M2 oracle gate therefore
        asserts optimality for LATE and measures the EARLY gap)."""
        if goal_test not in ("early", "late"):
            raise ValueError(goal_test)
        self.assert_no_reopen = assert_no_reopen
        self.canon_timing = canon_timing
        self.goal_test = goal_test
        self.name = "astar_" + goal_test

    def solve(self, domain, s0, heuristic, limits: Limits) -> Result:
        st = Stats()
        t0 = time.perf_counter()
        key = domain.key
        h_inc = heuristic.h_incremental
        successors = domain.successors
        is_goal = domain.is_goal
        early = (self.goal_test == "early")
        timing = self.canon_timing
        pc = time.perf_counter

        def finish(solved, reason, cost, goal_node_idx):
            st.wall_time_s = pc() - t0
            st.peak_rss_mb = _rss_mb()
            moves = None
            if solved:
                st.first_incumbent_time_s = st.wall_time_s
                # Reconstruct by parent pointers; nodes[i] = (state,
                # parent, move, g, h).  Concrete moves from concrete
                # states => replayable from s0.
                moves = []
                i = goal_node_idx
                while i is not None:
                    _s, parent, mv, _g, _h = nodes[i]
                    if mv is not None:
                        moves.append((mv.src, mv.dst))
                    i = parent
                moves.reverse()
            return Result(solved, reason, cost, moves, st)

        # --- root -----------------------------------------------------
        if timing:
            tk = pc(); k0 = key(s0); st.canon_time_s += pc() - tk
        else:
            k0 = key(s0)
        st.canon_calls += 1
        h0 = heuristic.h(s0)
        st.h_evaluations += 1
        nodes = [(s0, None, None, 0, h0)]     # side list; heap holds indices
        st.generated = 1
        if is_goal(s0):                        # early test includes s0
            return finish(True, None, 0, 0)

        open_heap = [(h0, 0, 0, 0)]            # (f, -g, counter, node_idx)
        counter = 1
        best_g = {k0: 0}
        key_of_idx = {0: k0}   # node's key, filled at generation, so pops
        closed = set()         # never re-canonicalize (would double
                               # canon_calls and muddy the RQ1 accounting)
        check_every = limits.check_every
        wall_deadline = None if limits.wall_s is None else t0 + limits.wall_s
        max_gen = limits.max_generated
        max_rss = limits.max_rss_mb

        while open_heap:
            f, neg_g, _tie, idx = heappop(open_heap)
            state, _parent, _mv, g, h = nodes[idx]
            # Lazy stale-entry rejection: an entry is dead if its key was
            # expanded already, or a cheaper path to the key was pushed
            # after this entry.  A node is live iff its key is not closed
            # AND best_g[key] equals its own g.
            ck = key_of_idx[idx]
            if ck in closed or best_g.get(ck, -1) != g:
                continue                        # stale
            if not early and is_goal(state):
                # LATE goal test: a popped goal has minimal f = g over
                # OPEN, which with admissible h proves optimality under
                # any positive edge costs (incl. M2) -- the standard
                # Dijkstra/A* argument the early test forfeits.
                return finish(True, None, g, idx)
            closed.add(ck)
            if len(closed) > st.closed_max_size:
                st.closed_max_size = len(closed)
            st.expanded += 1

            # Cheap periodic limit checks (design doc: not every node).
            if st.expanded % check_every == 0:
                now = pc()
                if wall_deadline is not None and now > wall_deadline:
                    return finish(False, "wall", None, None)
                if max_rss is not None and _rss_mb() > max_rss:
                    return finish(False, "memory", None, None)

            n_children = 0
            for mv, child, cost in successors(state):
                n_children += 1
                st.generated += 1
                # Early goal test: at generation time (Paper2earlylate).
                if early and is_goal(child):
                    gc = g + cost
                    ci = len(nodes)
                    nodes.append((child, idx, mv, gc, 0))
                    return finish(True, None, gc, ci)
                if timing:
                    tk = pc(); ckid = key(child); st.canon_time_s += pc() - tk
                else:
                    ckid = key(child)
                st.canon_calls += 1
                gc = g + cost
                old = best_g.get(ckid)
                if old is not None:
                    st.duplicates_detected += 1
                    if old <= gc:
                        continue                # not an improvement
                    # Strictly cheaper path to a known key.
                    if ckid in closed:
                        # With consistent h this is impossible; count it
                        # (experiments) or die loudly (test gates).
                        st.reopened += 1
                        if self.assert_no_reopen:
                            raise AssertionError(
                                f"reopen with supposedly consistent "
                                f"{heuristic.name}: key g {old} -> {gc}")
                        closed.discard(ckid)
                # New key, or improved path: (re)insert.
                hc = h_inc(h, state, mv, child)
                st.h_evaluations += 1
                ci = len(nodes)
                nodes.append((child, idx, mv, gc, hc))
                key_of_idx[ci] = ckid
                best_g[ckid] = gc
                heappush(open_heap, (gc + hc, -gc, counter, ci))
                counter += 1
                if len(open_heap) > st.open_max_size:
                    st.open_max_size = len(open_heap)
                if max_gen is not None and st.generated >= max_gen:
                    return finish(False, "generated", None, None)
            if n_children == 0:
                # Non-goal with no legal move: cheap provable dead end
                # (design doc 3.6), discovered for free at expansion.
                st.dead_ends_detected += 1

        # OPEN exhausted without reaching a goal: s0 provably cannot reach
        # any goal within the caps -- report as unsolved, no timeout.
        return finish(False, None, None, None)
