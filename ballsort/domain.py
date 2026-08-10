"""Ball Sort Puzzle domain.

Formalization follows Section 2 of ballsort_design_doc.md.

STATE ENCODING (design doc 6.2)
    A state is a tuple of T `bytes` objects, one per tube.  Each tube is a
    fixed-length bytes of length C: colours are 1..N, and 0 is padding above
    the topmost ball.  Index 0 is the BOTTOM of the tube.  Balls are always
    packed: all non-zero entries come before all zero entries.

    Example, C=4:  b"\\x02\\x02\\x01\\x00"  is a tube with colour 2 at the
    bottom, another 2, colour 1 on top, one free slot.

    Why tuple-of-bytes: hashable, compact, and `sorted(state)` +
    `b"".join(...)` gives the L1 canonical key in one line of C-speed code.

MOVES
    Pour semantics (design doc 2.3): a move takes the maximal same-coloured
    run at the top of the source tube and pours it onto the destination,
    truncated by the destination's free space.  Legality: src != dst, src
    non-empty, dst not full, and (dst empty or top(dst) == moved colour).

COST MODELS (design doc 2.4)
    "M1": every move costs 1 (primary).
    "M2": a move of k balls costs k (secondary).

GOAL (G_strict, per the answer to open question 1)
    Every tube is empty, or full (height == C) and monochromatic.

CANONICALIZATION (design doc 2.9) -- the full ladder, Milestone 3a
    L0: raw key  = concatenation of tubes in given order.
    L1: sort the tube-bytes lexicographically, then concatenate.
    L2: L1 + colour relabeling by the partition-refinement signature;
        colours whose signatures the refinement cannot separate keep an
        ARBITRARY (original-id) relative order.  SAFE but INCOMPLETE.
    L3: L2 + backtracking over the residual equal-signature colour cells,
        taking the lexicographic minimum key over every label assignment
        consistent with the cell structure.  SAFE and COMPLETE.

    Safety of L2/L3 holds BY CONSTRUCTION, independent of how the colour
    permutation is chosen: both levels return L1(pi(s)) for some colour
    permutation pi, so key(s) == key(s') implies L1(pi(s)) == L1(pi'(s')),
    i.e. pi(s) and pi'(s') are tube-permutation equivalent, hence s and s'
    are in the same S_T x S_N orbit.  What the CHOICE of pi controls is
    completeness (one key per orbit), which is exactly what the M3 oracle
    gates verify empirically (scripts/run_canon_gates.py).

This module is dependency-free (stdlib only) so it runs unmodified under
PyPy.
"""

from __future__ import annotations

import random
from typing import Iterator, NamedTuple, Optional

State = tuple  # tuple[bytes, ...]; kept loose for PyPy-friendly simplicity


class Move(NamedTuple):
    """A pour move.  `src`/`dst` index tubes in the *concrete* state tuple.

    `color` and `k` (number of balls poured) are redundant with the state --
    they are derivable from (state, src, dst) -- but carrying them makes
    incremental heuristic updates and debugging much cheaper.  The validator
    recomputes them from scratch and must agree.
    """

    src: int
    dst: int
    color: int
    k: int


def tube_height(tube: bytes) -> int:
    """Number of balls in the tube.  Balls are packed, so the height is the
    index of the first zero byte (or len(tube) if there is none)."""
    i = tube.find(0)
    return len(tube) if i < 0 else i


def top_run(tube: bytes) -> "tuple[int, int]":
    """(colour, length) of the maximal same-coloured run at the top.
    Returns (0, 0) for an empty tube."""
    h = tube_height(tube)
    if h == 0:
        return (0, 0)
    x = tube[h - 1]
    r = 1
    i = h - 2
    while i >= 0 and tube[i] == x:
        r += 1
        i -= 1
    return (x, r)


def bottom_run_len(tube: bytes) -> int:
    """Length of the maximal same-coloured run at the BOTTOM (0 if empty)."""
    if tube[0] == 0:
        return 0
    x = tube[0]
    r = 1
    n = len(tube)
    while r < n and tube[r] == x:
        r += 1
    return r


def runs_in_tube(tube: bytes) -> int:
    """Number of maximal same-coloured runs in the tube."""
    prev = 0
    r = 0
    for b in tube:
        if b == 0:
            break
        if b != prev:
            r += 1
            prev = b
    return r


class Domain:
    """The Ball Sort domain for fixed (N, C, E).

    canon_level: "L0" or "L1" for now ("L2"/"L3" reserved for Milestone 3).
    cost_model:  "M1" (unit) or "M2" (cost = balls moved).
    """

    def __init__(self, n_colors: int, capacity: int, n_empty: int,
                 canon_level: str = "L1", cost_model: str = "M1"):
        if n_colors < 1 or capacity < 1 or n_empty < 0:
            raise ValueError("bad parameters")
        if n_colors > 255:
            raise ValueError("colours must fit in a byte")
        if canon_level not in ("L0", "L1", "L2", "L3"):
            raise ValueError(f"unknown canon_level {canon_level!r}")
        if cost_model not in ("M1", "M2"):
            raise ValueError(f"unknown cost_model {cost_model!r}")
        self.N = n_colors
        self.C = capacity
        self.E = n_empty
        self.T = n_colors + n_empty
        self.canon_level = canon_level
        self.cost_model = cost_model
        self._empty_tube = bytes(capacity)

    # ------------------------------------------------------------------ #
    # Instance generation                                                #
    # ------------------------------------------------------------------ #

    def generate_instance(self, seed: int) -> State:
        """Uniformly random instance: shuffle the N*C-ball multiset and deal
        it into the first N tubes at full capacity; E tubes empty.
        Deterministic and reproducible from (N, C, E, seed): random.Random
        is the Mersenne Twister, identical across CPython and PyPy."""
        rng = random.Random(seed)
        balls = [c for c in range(1, self.N + 1) for _ in range(self.C)]
        rng.shuffle(balls)
        tubes = []
        for i in range(self.N):
            tubes.append(bytes(balls[i * self.C:(i + 1) * self.C]))
        tubes.extend(self._empty_tube for _ in range(self.E))
        return tuple(tubes)

    # ------------------------------------------------------------------ #
    # Goal test                                                          #
    # ------------------------------------------------------------------ #

    def is_goal(self, s: State) -> bool:
        """G_strict: every tube empty, or full and monochromatic."""
        for t in s:
            if t[0] == 0:
                continue                      # empty
            if t[-1] == 0:
                return False                  # partially filled
            x = t[0]
            for b in t:
                if b != x:
                    return False              # full but mixed
        return True

    def sorted_tubes_count(self, s: State) -> int:
        """Number of full monochromatic tubes; goal iff this equals N.
        (The O(1) *incremental* version of this counter lives in the search
        node, not here: the count changes only when a move fills a tube
        monochromatically or pours out of one.)"""
        cnt = 0
        for t in s:
            if t[0] != 0 and t[-1] != 0 and t == bytes([t[0]]) * self.C:
                cnt += 1
        return cnt

    # ------------------------------------------------------------------ #
    # Successors (forward pour moves)                                    #
    # ------------------------------------------------------------------ #

    def successors(self, s: State) -> Iterator["tuple[Move, State, int]"]:
        """Yield (move, child, cost) for every legal pour move, in a fixed
        deterministic order (src index, then dst index) -- design doc 5.3
        control #5."""
        C = self.C
        heights = [tube_height(t) for t in s]
        for a, ta in enumerate(s):
            ha = heights[a]
            if ha == 0:
                continue
            x, r = top_run(ta)
            for b, tb in enumerate(s):
                if b == a:
                    continue
                hb = heights[b]
                if hb == C:
                    continue                          # destination full
                if hb > 0 and tb[hb - 1] != x:
                    continue                          # top colour mismatch
                k = min(r, C - hb)                    # pour, truncated
                child = self._apply(s, a, b, x, k, ha, hb)
                cost = 1 if self.cost_model == "M1" else k
                yield Move(a, b, x, k), child, cost

    def _apply(self, s: State, a: int, b: int, x: int, k: int,
               ha: int, hb: int) -> State:
        """Build the child state: remove k balls from the top of tube a,
        add k balls of colour x on top of tube b."""
        new_a = bytearray(s[a])
        for i in range(ha - k, ha):
            new_a[i] = 0
        new_b = bytearray(s[b])
        for i in range(hb, hb + k):
            new_b[i] = x
        out = list(s)
        out[a] = bytes(new_a)
        out[b] = bytes(new_b)
        return tuple(out)

    def apply_move(self, s: State, src: int, dst: int) -> "tuple[Move, State, int]":
        """Apply the pour move (src -> dst) if legal, else raise ValueError.
        Recomputes colour and k from the state -- used by the validator."""
        if src == dst:
            raise ValueError("src == dst")
        ha = tube_height(s[src])
        if ha == 0:
            raise ValueError("source empty")
        hb = tube_height(s[dst])
        if hb == self.C:
            raise ValueError("destination full")
        x, r = top_run(s[src])
        if hb > 0 and s[dst][hb - 1] != x:
            raise ValueError("top colour mismatch")
        k = min(r, self.C - hb)
        child = self._apply(s, src, dst, x, k, ha, hb)
        cost = 1 if self.cost_model == "M1" else k
        return Move(src, dst, x, k), child, cost

    # ------------------------------------------------------------------ #
    # Predecessors (backward moves)                                      #
    # ------------------------------------------------------------------ #

    def predecessors(self, s: State) -> Iterator["tuple[Move, State, int]"]:
        """Yield (move, parent, cost) such that applying `move` to `parent`
        (forward) produces exactly `s`.

        THE REVERSE-MOVE LEGALITY CONDITION, derived (this is the part we
        must be able to explain out loud):

        A forward move poured k balls of colour x from tube a onto tube b.
        So in the parent p:  p[a] = s[a] + k copies of x on top,
                             p[b] = s[b] with its top k balls removed.
        For (b, k, a) to be a valid reverse choice, ALL of the following:

        (R1) The top run of s[b] has colour x and length L >= k
             -- the k balls we un-pour must actually sit on top of b.
        (R2) If k == L, the run must be b's ENTIRE content.
             Otherwise p[b] would be non-empty with a top colour != x, and
             the forward move onto it would have been illegal.
             (If k < L, p[b]'s top is still x -- always legal.)
        (R3) height(s[a]) + k <= C -- the balls must fit back on a.
        (R4) The pour-maximality condition.  Forward pours move
             k' = min(run(a in p), free(b in p)).  We need k' == k.
             run(a in p) = k + t, where t = length of the x-run at the top
             of s[a] (t = 0 if s[a] is empty or its top is not x).
             free(b in p) = free(b in s) + k.
             min(k + t, free_s(b) + k) == k  <=>  min(t, free_s(b)) == 0,
             i.e.  (top of s[a] is not colour x)  OR  (s[b] is full in s).
             Intuition: if a still has x on top AND b has free space, the
             forward pour would have taken those extra x's too -- so this
             (a, b, k) cannot be the move that produced s.

        Note the asymmetry with successors(): forward moves have exactly one
        k per (a, b) pair; reverse moves enumerate a RANGE of k per (b, a).
        The graph is genuinely directed -- most forward moves have no legal
        inverse move in the puzzle itself; predecessors() inverts the edge
        relation, it does not play the puzzle backwards.
        """
        C = self.C
        heights = [tube_height(t) for t in s]
        for b, tb in enumerate(s):
            hb = heights[b]
            if hb == 0:
                continue
            x, L = top_run(tb)
            run_is_entire_tube = (L == hb)
            free_b = C - hb
            for k in range(1, L + 1):
                if k == L and not run_is_entire_tube:
                    continue                                       # (R2)
                for a, ta in enumerate(s):
                    if a == b:
                        continue
                    ha = heights[a]
                    if ha + k > C:
                        continue                                   # (R3)
                    if free_b != 0 and ha > 0 and ta[ha - 1] == x:
                        continue                                   # (R4)
                    # Build the parent.
                    pa = bytearray(ta)
                    for i in range(ha, ha + k):
                        pa[i] = x
                    pb = bytearray(tb)
                    for i in range(hb - k, hb):
                        pb[i] = 0
                    out = list(s)
                    out[a] = bytes(pa)
                    out[b] = bytes(pb)
                    parent = tuple(out)
                    cost = 1 if self.cost_model == "M1" else k
                    yield Move(a, b, x, k), parent, cost

    # ------------------------------------------------------------------ #
    # Canonicalization / duplicate-detection keys                        #
    # ------------------------------------------------------------------ #

    def key(self, s: State) -> bytes:
        """Duplicate-detection key at the configured canonicalization level.
        Safe (design doc 2.9): equal keys imply symmetric states."""
        lvl = self.canon_level
        if lvl == "L0":
            return b"".join(s)
        if lvl == "L1":
            return b"".join(sorted(s))        # L1: tube order is irrelevant
        if lvl == "L2":
            tbl = self._l2_table(s)
            return b"".join(sorted(t.translate(tbl) for t in s))
        return self._l3_key_state(s)[0]       # L3

    def canonical_state(self, s: State) -> State:
        """The canonical representative itself (tubes relabeled per the
        canon level, then sorted), used when we want to *search over*
        canonical states, e.g. in the oracle and the solvability DFS.
        NOTE (design doc 2.8): search algorithms must NOT use this to
        replace the states they store -- keys are canonical, stored states
        stay concrete, so parent-pointer paths replay from the real s0."""
        lvl = self.canon_level
        if lvl == "L0":
            return s
        if lvl == "L1":
            return tuple(sorted(s))
        if lvl == "L2":
            tbl = self._l2_table(s)
            return tuple(sorted(t.translate(tbl) for t in s))
        return self._l3_key_state(s)[1]       # L3

    # -- colour partition refinement (L2/L3 machinery, design doc 2.9) -- #

    def _refine_colors(self, s: State) -> "list[tuple[int, ...]]":
        """Partition the colours 1..N of state `s` into cells of
        signature-indistinguishable colours, and return the cells in a
        canonical (signature-sorted) order.

        THE SIGNATURE (design doc 2.9, implemented faithfully): for each
        colour c, the multiset over c's runs of
            (run length, height of the run's bottom in its tube,
             number of balls in that tube, run-is-at-tube-bottom).
        These facts are LABEL-FREE (they never mention which colour a
        neighbouring ball has) and TUBE-ORDER-FREE (a multiset over runs),
        so the base signature is invariant under S_T and *equivariant*
        under S_N: relabeling colours permutes the signatures along with
        the colours but never changes any signature's value.  That
        equivariance is what makes the induced partition an orbit
        invariant -- the load-bearing fact for L3's completeness.

        THE REFINEMENT LOOP: colours with equal base signatures may still
        be structurally different through their CONTEXT -- which kinds of
        colours sit directly below/above their runs.  So we iterate:
        extend every run tuple with the current cell ids of the colours
        immediately below and above the run (sentinel -1 when the run
        touches the tube bottom / is topmost), prepend the colour's own
        current cell id, and re-partition on the extended signatures.
        Because each new signature contains the old cell id, every round
        REFINES the previous partition (cells only split, never merge),
        so the loop reaches a fixed point in at most N rounds; we stop
        when a round no longer increases the number of cells (equal count
        + refinement ==> identical partition).  Cell ids are always
        assigned by sorting signature values, so they too are orbit
        invariants, and feeding them back keeps the whole loop
        equivariant.
        """
        N = self.N
        # 1. Collect every run of every colour with its structural facts.
        #    runs[c] = list of (run_len, bottom_h, tube_balls, at_bottom,
        #                       colour_below, colour_above)
        runs = {c: [] for c in range(1, N + 1)}
        for t in s:
            h = tube_height(t)
            i = 0
            while i < h:
                x = t[i]
                j = i
                while j < h and t[j] == x:
                    j += 1
                below = t[i - 1] if i > 0 else 0
                above = t[j] if j < h else 0
                runs[x].append((j - i, i, h, i == 0, below, above))
                i = j
        # 2. Initial partition from the label-free base signature.
        base = {c: tuple(sorted((rl, bh, th, ab)
                                for rl, bh, th, ab, _lo, _hi in rs))
                for c, rs in runs.items()}
        rank = {v: i for i, v in enumerate(sorted(set(base.values())))}
        cell_of = {c: rank[base[c]] for c in runs}
        n_cells = len(rank)
        # 3. Refine to a fixed point.
        while n_cells < N:
            sig = {}
            for c, rs in runs.items():
                ext = tuple(sorted(
                    (rl, bh, th, ab,
                     cell_of[lo] if lo else -1,
                     cell_of[hi] if hi else -1)
                    for rl, bh, th, ab, lo, hi in rs))
                sig[c] = (cell_of[c], ext)
            rank = {v: i for i, v in enumerate(sorted(set(sig.values())))}
            new_cell = {c: rank[sig[c]] for c in sig}
            if len(rank) == n_cells:
                cell_of = new_cell      # same partition, canonical ranks
                break
            cell_of, n_cells = new_cell, len(rank)
        # 4. Cells in canonical (rank) order; colours inside a cell sorted
        #    by original id purely for determinism of iteration.
        cells: "dict[int, list[int]]" = {}
        for c, r in cell_of.items():
            cells.setdefault(r, []).append(c)
        return [tuple(sorted(cells[r])) for r in sorted(cells)]

    def _l2_table(self, s: State) -> bytes:
        """The L2 relabeling table: cells receive consecutive label blocks
        in canonical cell order; INSIDE a cell, colours keep their original
        relative order.  That within-cell tie-break is deliberate and is
        exactly where L2's incompleteness lives: original colour ids are
        NOT an orbit invariant, so two orbit-equivalent states whose
        refinement leaves a multi-colour cell can land on different keys.
        (Never on the same key for different orbits -- see the safety
        argument in the module docstring.)  Byte 0 (padding) and bytes
        above N map to themselves."""
        cells = self._refine_colors(s)
        tbl = bytearray(range(256))
        nxt = 1
        for cell in cells:
            for c in cell:                   # ascending original id
                tbl[c] = nxt
                nxt += 1
        return bytes(tbl)

    def _l3_key_state(self, s: State) -> "tuple[bytes, State]":
        """L3 = L2 + backtracking over the residual cells: try EVERY label
        assignment consistent with the cell structure (each cell keeps its
        canonical label block; the |cell|! orders within each block are
        enumerated) and return the lexicographically minimum
        (key, relabeled-sorted-state) pair.

        Why this is COMPLETE (one key per orbit): if s' = rho(tau(s)) for
        a colour permutation rho and tube permutation tau, equivariance of
        the refinement gives that s' has the same cells with the same
        signatures, with colour memberships mapped through rho.  Hence the
        set of candidate relabeled states of s' is exactly the tau-image
        of the candidate set of s, and tube-sorting (L1) erases tau -- so
        both states minimise over the SAME set of byte strings and get the
        same key.  (The oracle gate checks this exhaustively rather than
        trusting the argument: |distinct L3 keys| == |orbits|.)

        Cost: factorial in the largest residual cell, which the refinement
        keeps at 1-2 colours in practice (design doc 2.9); the all-
        singleton fast path below is the common case and costs the same
        as L2."""
        cells = self._refine_colors(s)
        # Fast path: refinement separated every colour -> L3 == L2.
        if all(len(cell) == 1 for cell in cells):
            tbl = bytearray(range(256))
            nxt = 1
            for cell in cells:
                tbl[cell[0]] = nxt
                nxt += 1
            tb = bytes(tbl)
            tubes = sorted(t.translate(tb) for t in s)
            return b"".join(tubes), tuple(tubes)
        # General path: enumerate within-cell orders (product over cells).
        from itertools import permutations, product
        starts = []
        nxt = 1
        perm_lists = []
        for cell in cells:
            starts.append(nxt)
            nxt += len(cell)
            perm_lists.append(list(permutations(cell)) if len(cell) > 1
                              else [cell])
        best_key = None
        best_tubes = None
        for combo in product(*perm_lists):
            tbl = bytearray(range(256))
            for cell_perm, st in zip(combo, starts):
                for off, c in enumerate(cell_perm):
                    tbl[c] = st + off
            tb = bytes(tbl)
            tubes = sorted(t.translate(tb) for t in s)
            k = b"".join(tubes)
            if best_key is None or k < best_key:
                best_key, best_tubes = k, tubes
        return best_key, tuple(best_tubes)

    # ------------------------------------------------------------------ #
    # Dead-end detection                                                 #
    # ------------------------------------------------------------------ #

    def is_dead_end(self, s: State) -> bool:
        """Cheap provable dead end (design doc 3.6): a non-goal state with
        no legal move at all.  Under pour semantics that means: no empty
        tube with a non-mono... more precisely, no (a, b) pair passes the
        legality test.  Equivalent quick test: there is no non-full tube
        that is empty or whose top matches some other tube's top."""
        if self.is_goal(s):
            return False
        for _ in self.successors(s):
            return False
        return True

    # ------------------------------------------------------------------ #
    # Satisficing solvability solver (decision procedure, NOT optimal)    #
    # ------------------------------------------------------------------ #

    def solvable(self, s: State, node_cap: int = 2_000_000) -> Optional[bool]:
        """DFS over canonical states with a visited set.

        Move ordering (design doc 2.10): prefer moves that complete a tube,
        then moves with smaller h4 in the child, and de-prioritise moves
        onto an empty tube when a same-colour destination exists.  The
        ordering only affects speed, never the answer.

        Returns True (solvable), False (exhausted the reachable space
        without a goal -- provably unsolvable), or None (node cap hit --
        undecided).  With canonical dedup the reachable quotient space is
        finite, so False is a proof.
        """
        from .heuristics import H4          # local import: no cycle at load
        h4 = H4()
        start = self.canonical_state(s)
        if self.is_goal(start):
            return True
        visited = {self.key(start)}
        stack = [start]
        expanded = 0
        while stack:
            cur = stack.pop()
            expanded += 1
            if expanded > node_cap:
                return None
            children = []
            for mv, child, _cost in self.successors(cur):
                ck = self.key(child)
                if ck in visited:
                    continue
                visited.add(ck)
                if self.is_goal(child):
                    return True
                # Ordering score: (completed a tube?, moved-to-empty?, h4).
                dst_tube = child[mv.dst]
                completed = (dst_tube[-1] != 0
                             and dst_tube == bytes([mv.color]) * self.C)
                to_empty = (cur[mv.dst][0] == 0)
                children.append(((not completed, to_empty, h4.h(child)),
                                 self.canonical_state(child)))
            # DFS stack: push worst first so the best is popped first.
            children.sort(key=lambda p: p[0], reverse=True)
            stack.extend(c for _score, c in children)
        return False

    # ------------------------------------------------------------------ #
    # Validation and debugging                                           #
    # ------------------------------------------------------------------ #

    def validate_solution(self, s0: State, moves) -> State:
        """Replay a list of (src, dst) pairs (or Move tuples) from s0.
        Raises ValueError on any illegal move or if the final state is not
        a goal.  Returns the final state."""
        s = s0
        for i, m in enumerate(moves):
            src, dst = m[0], m[1]
            try:
                _mv, s, _cost = self.apply_move(s, src, dst)
            except ValueError as e:
                raise ValueError(f"illegal move #{i} ({src}->{dst}): {e}")
        if not self.is_goal(s):
            raise ValueError("move sequence does not end at a goal state")
        return s

    def pretty(self, s: State) -> str:
        """Human-readable state, tubes side by side, top row = tube tops."""
        C = self.C
        rows = []
        for level in range(C - 1, -1, -1):
            cells = []
            for t in s:
                v = t[level]
                cells.append(f"{v:2d}" if v else " .")
            rows.append("|" + "|".join(cells) + "|")
        rows.append("+" + "--+" * len(s))
        rows.append(" " + " ".join(f"{i:2d}" for i in range(len(s))))
        return "\n".join(rows)
