"""The h* oracle and the Milestone-1 verification suite (design doc,
Section 6.5 and Risk 1).

WHAT AND WHY
  We enumerate the ENTIRE configuration space (every legal placement of
  the N*C balls into T tubes, quotiented by tube permutation), build the
  full forward edge relation, and compute exact h*(s) for every state.

  Direction of the h* computation: the graph is DIRECTED and there are
  many goal states, so the right tool is a multi-source BACKWARD breadth-
  first search from the set of all goal states, over the REVERSED edge
  relation.  A forward search from each state would be quadratic in the
  space; a backward sweep is one pass.  Every state never reached backward
  has h* = infinity (it cannot reach any goal -- a "dead" state in the
  broad sense, which is itself a number we want for RQ4).

  Trust: the oracle builds reverse adjacency by REVERSING THE FORWARD
  EDGES, not by calling Domain.predecessors().  That way the oracle does
  not depend on the correctness of the (subtle) reverse-move derivation;
  instead, predecessors() is *validated against* the oracle's edge set
  (check P below).

  We enumerate over canonical (tube-sorted) states.  This is sound because
  tube permutation commutes with the move relation and preserves goals, so
  distances in the quotient equal distances in the full graph (design doc
  2.8).

CHECKS (numbering follows the Milestone-1 prompt)
  1. Admissibility: h(s) <= h*(s) for all s with finite h*, all heuristics,
     under the matching cost model.  Violations are reported with three
     concrete counterexamples.
  2. Consistency:  h(s) <= c(s,s') + h(s') over every edge.
  3. Dominance chain h4 >= h3 >= max(h1, h2), with strictness frequencies.
  4. Mean h/h* per heuristic over solvable non-goal states.
  5. Canonicalization soundness (permutation invariance + no bad merges).
  6. L1 subsumes pruning rules P1/P3 (design doc 2.6).
  7. Effective branching factor after L1.
  P. predecessors() == reversed forward edges, state by state.

Stdlib only; runs under PyPy.
"""

from __future__ import annotations

import random
import time
from collections import deque
from heapq import heappush, heappop

from .domain import Domain, tube_height
from . import heuristics as H

INF = float("inf")


# --------------------------------------------------------------------- #
# Full-space enumeration                                                #
# --------------------------------------------------------------------- #

def _all_tube_contents(n_colors: int, capacity: int):
    """Every possible packed tube content as a bytes of length `capacity`
    (colours 1..N then zero padding), together with its colour-count
    vector.  Count: sum_{l=0..C} N^l -- small (e.g. 121 for N=3, C=4)."""
    out = []
    def rec(prefix):
        counts = [0] * (n_colors + 1)
        for x in prefix:
            counts[x] += 1
        tube = bytes(prefix) + bytes(capacity - len(prefix))
        out.append((tube, tuple(counts[1:])))
        if len(prefix) < capacity:
            for x in range(1, n_colors + 1):
                rec(prefix + [x])
    rec([])
    return out


def enumerate_space(dom: Domain):
    """All canonical states of the (N, C, E) configuration space: choose a
    lexicographically NON-DECREASING sequence of T tube contents whose
    colour counts sum to C each.  Non-decreasing <=> canonical under tube
    permutation, so each equivalence class is produced exactly once."""
    N, C, T = dom.N, dom.C, dom.T
    contents = _all_tube_contents(N, C)
    contents.sort()                      # so states come out canonical
    target = tuple([C] * N)
    states = []
    counts = [0] * N
    chosen = []

    def rec(start_idx, balls_left, tubes_left):
        if tubes_left == 0:
            if balls_left == 0:
                states.append(tuple(chosen))
            return
        if balls_left > tubes_left * C:
            return                      # cannot fit remaining balls
        for i in range(start_idx, len(contents)):
            tube, cvec = contents[i]
            ok = True
            for c in range(N):
                if counts[c] + cvec[c] > C:
                    ok = False
                    break
            if not ok:
                continue
            for c in range(N):
                counts[c] += cvec[c]
            chosen.append(tube)
            rec(i, balls_left - sum(cvec), tubes_left - 1)
            chosen.pop()
            for c in range(N):
                counts[c] -= cvec[c]

    rec(0, N * C, T)
    return states


# --------------------------------------------------------------------- #
# Graph construction and h*                                             #
# --------------------------------------------------------------------- #

def build_graph(dom: Domain, states):
    """index maps + forward edges (u -> list of (v, k)) with k = balls
    poured, so both cost models can be derived from one edge set."""
    index = {dom.key(s): i for i, s in enumerate(states)}
    fwd = [[] for _ in states]
    for i, s in enumerate(states):
        for mv, child, _cost in dom.successors(s):
            j = index[dom.key(child)]
            fwd[i].append((j, mv.k))
    return index, fwd


def h_star(dom: Domain, states, fwd, cost_model: str):
    """Exact goal distance for every state via multi-source backward
    search over reversed edges: BFS for M1 (unit costs), Dijkstra for M2."""
    n = len(states)
    rev = [[] for _ in range(n)]
    for u, lst in enumerate(fwd):
        for v, k in lst:
            rev[v].append((u, k))
    goals = [i for i, s in enumerate(states) if dom.is_goal(s)]
    dist = [INF] * n
    if cost_model == "M1":
        dq = deque()
        for g in goals:
            dist[g] = 0
            dq.append(g)
        while dq:
            v = dq.popleft()
            for u, _k in rev[v]:
                if dist[u] is INF or dist[u] == INF:
                    dist[u] = dist[v] + 1
                    dq.append(u)
    else:  # M2: edge cost = k
        pq = []
        for g in goals:
            dist[g] = 0
            heappush(pq, (0, g))
        while pq:
            d, v = heappop(pq)
            if d > dist[v]:
                continue
            for u, k in rev[v]:
                nd = d + k
                if nd < dist[u]:
                    dist[u] = nd
                    heappush(pq, (nd, u))
    return dist, goals


# --------------------------------------------------------------------- #
# The verification suite                                                #
# --------------------------------------------------------------------- #

def verify_config(n_colors, capacity, n_empty, sample_seed=0, report=print):
    """Run every check for one (N, C, E).  Returns a dict of results."""
    t0 = time.time()
    dom = Domain(n_colors, capacity, n_empty, canon_level="L1")
    states = enumerate_space(dom)
    index, fwd = build_graph(dom, states)
    n = len(states)
    n_edges = sum(len(l) for l in fwd)
    hs_m1, goals = h_star(dom, states, fwd, "M1")
    hs_m2, _ = h_star(dom, states, fwd, "M2")
    n_dead = sum(1 for d in hs_m1 if d == INF)

    res = {
        "N": n_colors, "C": capacity, "E": n_empty,
        "canonical_states": n, "edges": n_edges, "goal_states": len(goals),
        "states_hstar_inf": n_dead,
        "frac_hstar_inf": n_dead / n,
    }
    report(f"\n=== (N={n_colors}, C={capacity}, E={n_empty}) "
           f"{n} canonical states, {n_edges} edges, "
           f"{len(goals)} goal state(s), "
           f"{n_dead} ({100*n_dead/n:.1f}%) cannot reach a goal ===")

    heus = {name: H.make(name) for name in ("h1", "h2", "h3", "h4", "h5")}

    # -- Check 1: admissibility ------------------------------------------
    for name, heu in heus.items():
        for cm, hs in (("M1", hs_m1), ("M2", hs_m2)):
            claimed = cm in heu.admissible_under
            viol = []
            for i, s in enumerate(states):
                if hs[i] == INF:
                    continue
                if heu.h(s) > hs[i]:
                    viol.append(i)
                    if len(viol) >= 3 and not claimed:
                        break
            key = f"adm_{name}_{cm}"
            res[key] = len(viol)
            if claimed and viol:
                report(f"  [FAIL] {name} claimed admissible under {cm}: "
                       f"{len(viol)} violations. Counterexamples:")
                for i in viol[:3]:
                    report(f"    h={heus[name].h(states[i])} "
                           f"h*={hs[i]}\n{dom.pretty(states[i])}")
            elif claimed:
                report(f"  [ok] {name} admissible under {cm} "
                       f"(0 violations / {n - (n_dead if cm else 0)} states)")
            elif not claimed and viol:
                report(f"  [ok] {name} NOT claimed admissible under {cm}, "
                       f"and indeed {len(viol)}+ violations exist "
                       f"(expected for h5/M1)")
            else:
                report(f"  [note] {name} not claimed admissible under {cm}, "
                       f"but no violation found in this config")

    # -- Check 2: consistency --------------------------------------------
    for name, heu in heus.items():
        for cm in ("M1", "M2"):
            claimed = cm in heu.consistent_under
            bad = 0
            example = None
            for u, lst in enumerate(fwd):
                hu = heu.h(states[u])
                for v, k in lst:
                    c = 1 if cm == "M1" else k
                    hv = heu.h(states[v])
                    if hu > c + hv:
                        bad += 1
                        if example is None:
                            example = (u, v, hu, hv, c)
            res[f"cons_{name}_{cm}"] = bad
            if claimed and bad:
                u, v, hu, hv, c = example
                report(f"  [FAIL] {name} claimed consistent under {cm}: "
                       f"{bad} violating edges, e.g. h(u)={hu} > "
                       f"c={c} + h(v)={hv}")
            elif claimed:
                report(f"  [ok] {name} consistent under {cm} "
                       f"({n_edges} edges checked)")

    # -- Check 3: dominance chain ---------------------------------------
    strict_43 = strict_3max = viol_dom = 0
    for s in states:
        v1, v2, v3, v4 = (heus["h1"].h(s), heus["h2"].h(s),
                          heus["h3"].h(s), heus["h4"].h(s))
        m = max(v1, v2)
        if not (v4 >= v3 >= m):
            viol_dom += 1
        if v4 > v3:
            strict_43 += 1
        if v3 > m:
            strict_3max += 1
    res["dominance_violations"] = viol_dom
    res["strict_h4_gt_h3"] = strict_43 / n
    res["strict_h3_gt_maxh1h2"] = strict_3max / n
    report(f"  [{'ok' if viol_dom == 0 else 'FAIL'}] dominance "
           f"h4>=h3>=max(h1,h2): {viol_dom} violations; "
           f"h4>h3 strictly on {100*strict_43/n:.1f}% of states, "
           f"h3>max(h1,h2) on {100*strict_3max/n:.1f}%")

    # -- Check 4: informedness h/h* -------------------------------------
    for name, heu in heus.items():
        cm_hs = hs_m2 if name == "h5" else hs_m1
        num = den = 0
        for i, s in enumerate(states):
            if cm_hs[i] == INF or cm_hs[i] == 0:
                continue
            num += heu.h(s) / cm_hs[i]
            den += 1
        res[f"informedness_{name}"] = num / den if den else None
        cm = "M2" if name == "h5" else "M1"
        if den:
            report(f"  informedness mean h/h* [{cm}] {name}: {num/den:.3f}")

    # -- Check 5: canonicalization soundness ----------------------------
    rng = random.Random(sample_seed)
    perm_ok = True
    for _ in range(500):
        s = states[rng.randrange(n)]
        perm = list(s)
        rng.shuffle(perm)
        if dom.key(tuple(perm)) != dom.key(s):
            perm_ok = False
            break
    # "No bad merges": within the enumerated space, distinct canonical
    # states must have distinct keys -- exhaustive, not sampled:
    merge_ok = (len({dom.key(s) for s in states}) == n)
    res["canon_perm_invariant"] = perm_ok
    res["canon_no_bad_merges"] = merge_ok
    report(f"  [{'ok' if perm_ok and merge_ok else 'FAIL'}] L1 soundness: "
           f"permutation-invariant={perm_ok}, injective on classes={merge_ok}")

    # -- Check 6: does L1 subsume pruning rules P1 / P3? ----------------
    # P1: move from a monochromatic tube onto an empty tube.
    # P3: move onto an empty tube when another empty tube exists.
    # Claim (design doc 2.6): every child produced by a P1 move is L1-equal
    # to its parent (self-loop in the quotient), and P3 moves produce
    # duplicate children among siblings.
    p1_moves = p1_selfloops = 0
    p3_moves = p3_dup_children = 0
    for s in states:
        child_keys = {}
        empties = sum(1 for t in s if t[0] == 0)
        for mv, child, _cost in dom.successors(s):
            ck = dom.key(child)
            src_t = s[mv.src]
            src_mono = (src_t[0] != 0 and
                        tube_height(src_t) ==
                        len([b for b in src_t if b == src_t[0] and b]))
            # simpler: source tube is monochromatic (all balls same colour)
            hgt = tube_height(src_t)
            src_mono = all(src_t[i] == src_t[0] for i in range(hgt))
            dst_empty = (s[mv.dst][0] == 0)
            if src_mono and dst_empty:
                p1_moves += 1
                if ck == dom.key(s):
                    p1_selfloops += 1
            if dst_empty and empties >= 2:
                p3_moves += 1
                if ck in child_keys:
                    p3_dup_children += 1
            child_keys[ck] = child_keys.get(ck, 0) + 1
    res["p1_moves"] = p1_moves
    res["p1_detected_as_selfloop"] = p1_selfloops
    res["p3_moves"] = p3_moves
    res["p3_detected_as_duplicate"] = p3_dup_children
    ok6 = (p1_moves == p1_selfloops)
    report(f"  [{'ok' if ok6 else 'PARTIAL'}] P1 subsumption: "
           f"{p1_selfloops}/{p1_moves} P1 moves are L1 self-loops; "
           f"P3: {p3_dup_children}/{p3_moves} to-empty moves (2+ empties) "
           f"are duplicates of an earlier sibling")

    # -- Check 7: effective branching factor after L1 -------------------
    tot_children = tot_distinct = tot_nonparent = 0
    for i, s in enumerate(states):
        keys = set()
        for _mv, child, _c in dom.successors(s):
            keys.add(dom.key(child))
        tot_children += len(fwd[i])
        keys.discard(dom.key(s))
        tot_distinct += len(keys) + (1 if dom.key(s) in
                                     {dom.key(c) for _m, c, _ in
                                      dom.successors(s)} else 0)
        tot_nonparent += len(keys)
    res["b_raw"] = tot_children / n
    res["b_eff_L1"] = tot_nonparent / n
    report(f"  branching: raw {tot_children/n:.2f}, "
           f"effective after L1 (distinct, non-self) {tot_nonparent/n:.2f}")

    # -- Check P: predecessors() vs reversed forward edges --------------
    # Comparison is at the SET level of (parent_key, k), not multiset.
    # Reason (verified empirically before this check was finalised): in
    # the quotient graph, edge multiplicity is direction-dependent.  If a
    # parent has two identical tubes {x^j, x^j}, the two concrete forward
    # moves i->j and j->i produce permutation-equivalent children, so the
    # forward relation from the parent REPRESENTATIVE records two edges;
    # but the child representative has a single merged tube, so exactly
    # one reverse triple exists.  predecessors() is correct at the
    # concrete-state level (round-trip test in tests/), and equivariance
    # guarantees set-level agreement of (parent_key, k) -- which is what
    # backward search needs.  This asymmetry is itself a reportable fact
    # about symmetry reduction (a parent with a non-trivial stabilizer
    # "loses" duplicate edges in the quotient).
    rev_map = {}
    for u, lst in enumerate(fwd):
        ku = dom.key(states[u])
        for v, k in lst:
            rev_map.setdefault(dom.key(states[v]), set()).add((ku, k))
    pred_bad = 0
    for i, s in enumerate(states):
        got = {(dom.key(p), mv.k) for mv, p, _c in dom.predecessors(s)}
        want = rev_map.get(dom.key(s), set())
        if got != want:
            pred_bad += 1
            if pred_bad <= 2:
                missing = want - got
                extra = got - want
                report(f"  [FAIL] predecessors mismatch at state:\n"
                       f"{dom.pretty(s)}\n    missing {len(missing)}, "
                       f"spurious {len(extra)}")
    res["predecessor_mismatches"] = pred_bad
    if pred_bad == 0:
        report(f"  [ok] predecessors() inverts the forward edge relation "
               f"(set of (parent,k)) on all {n} states")

    res["seconds"] = round(time.time() - t0, 1)
    report(f"  ({res['seconds']}s)")
    return res
