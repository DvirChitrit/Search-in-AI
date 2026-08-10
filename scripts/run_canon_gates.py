"""Milestone 3a: canonicalization soundness gates for L2/L3.

Ground truth is the full S_T x S_N orbit relation.  `enumerate_space`
already yields one representative per S_T (tube-permutation) class, so
the S_N (colour) quotient is added on top exactly as the M3a prompt
prescribes: apply each of the N! colour permutations to each enumerated
state, re-sort tubes (L1), and take the minimum resulting key as the
ORBIT KEY.  Two states are in the same orbit iff their orbit keys are
equal -- min-over-orbit is itself a complete invariant, and with N <= 4
(<= 24 permutations) it is exhaustively computable, no union-find needed.

Gates (any failure prints a concrete counterexample and exits 1):
  (a) SAFE      -- no Lk key (k in {2,3}) merges two distinct orbits.
  (b) COMPLETE  -- |distinct L3 keys| == |orbits| on every config.
  (c) LADDER    -- |L0| >= |L1| >= |L2| >= |L3| == |orbits|; the four
                   counts per config are the state-space half of RQ1.
                   |L1| = enumerated states; |L2|/|L3| = distinct keys
                   over them (both are tube-order invariant, so counting
                   on S_T representatives is exact); |L0| = the raw count
                   = sum over representatives of T!/prod(mult!) distinct
                   tube orderings (states with repeated identical tubes
                   have fewer than T! raw forms -- the exact stabilizer
                   correction, not the /T! approximation).
  (d) h INVARIANCE  -- h(s) == h(canonical_L3(s)) for h0..h4, all states.
  (e) h* INVARIANCE -- h*(s) == h*(canonical_L3(s)) under M1, all states.
  (f) OPTIMALITY + PATH VALIDITY -- A*-EARLY with h0..h4 at canon L2 and
      L3 from >= --sample finite-h* states returns cost == h* EXACTLY
      (M1) and every move list passes Domain.validate_solution from the
      CONCRETE s0 (canonical keys, concrete states: design doc 2.8).

Usage: python3 scripts/run_canon_gates.py [--sample 100] [--fast]
Writes the ladder table to results/canon_ladder.csv (Deliverable 2c /
reproducibility mandate: the report's table regenerates from here).
"""

from __future__ import annotations

import argparse
import csv
import os
import math
import random
import sys
import time
from collections import Counter
from itertools import permutations

sys.path.insert(0, ".")

from ballsort.domain import Domain
from ballsort import heuristics as H
from ballsort.oracle import enumerate_space, build_graph, h_star, INF
from ballsort.algorithms.base import Limits
from ballsort.algorithms.astar import AStarEarly

CONFIGS = [(3, 3, 1), (3, 3, 2), (3, 3, 3),
           (3, 4, 1), (3, 4, 2), (3, 4, 3),
           (4, 3, 1), (4, 3, 2)]

LIMITS = Limits(wall_s=None, max_generated=None, max_rss_mb=None)


def color_tables(n: int):
    """One 256-byte translate table per colour permutation of 1..n."""
    tabs = []
    for p in permutations(range(1, n + 1)):
        tbl = bytearray(range(256))
        for c, pc in zip(range(1, n + 1), p):
            tbl[c] = pc
        tabs.append(bytes(tbl))
    return tabs


def orbit_key(s, tabs):
    """Min over all colour relabelings of the L1 key: the ground truth."""
    best = None
    for tb in tabs:
        k = b"".join(sorted(t.translate(tb) for t in s))
        if best is None or k < best:
            best = k
    return best


def raw_count(s, T):
    """Distinct tube orderings of one S_T representative: T!/prod(m_i!)
    over the multiplicities of identical tubes (exact, per-state)."""
    d = math.factorial(T)
    for m in Counter(s).values():
        d //= math.factorial(m)
    return d


def gate_config(n, c, e, sample, csv_rows):
    t0 = time.time()
    dom1 = Domain(n, c, e, canon_level="L1")
    dom2 = Domain(n, c, e, canon_level="L2")
    dom3 = Domain(n, c, e, canon_level="L3")
    states = enumerate_space(dom1)
    ns = len(states)
    tabs = color_tables(n)

    # Ground truth + all three key levels in one pass over the space.
    okeys, k2s, k3s = [], [], []
    for s in states:
        okeys.append(orbit_key(s, tabs))
        k2s.append(dom2.key(s))
        k3s.append(dom3.key(s))

    # -- (a) SAFE: one orbit per Lk key ---------------------------------
    for lvl, ks, dom in (("L2", k2s, dom2), ("L3", k3s, dom3)):
        seen = {}
        for i, k in enumerate(ks):
            j = seen.setdefault(k, i)
            if okeys[j] != okeys[i]:
                print(f"\n*** GATE (a) FAIL: {lvl} merges two orbits "
                      f"(N={n} C={c} E={e}).  Shared key {k.hex()}\n"
                      f"state A:\n{dom.pretty(states[j])}\n"
                      f"state B:\n{dom.pretty(states[i])}", flush=True)
                sys.exit(1)

    n_orbits = len(set(okeys))
    n2, n3 = len(set(k2s)), len(set(k3s))

    # -- (b) COMPLETE: L3 keys == orbits --------------------------------
    if n3 != n_orbits:
        # Find an orbit with two L3 keys and print it.
        by_orbit = {}
        for i, ok in enumerate(okeys):
            by_orbit.setdefault(ok, set()).add(k3s[i])
        for ok, kk in by_orbit.items():
            if len(kk) > 1:
                idxs = [i for i, o in enumerate(okeys) if o == ok][:2]
                print(f"\n*** GATE (b) FAIL: one orbit, {len(kk)} L3 keys "
                      f"(N={n} C={c} E={e}):\n"
                      f"{dom3.pretty(states[idxs[0]])}\n---\n"
                      f"{dom3.pretty(states[idxs[1]])}", flush=True)
                sys.exit(1)

    # -- (c) LADDER -----------------------------------------------------
    n0 = sum(raw_count(s, dom1.T) for s in states)
    if not (n0 >= ns >= n2 >= n3 == n_orbits):
        print(f"\n*** GATE (c) FAIL: ladder not monotone "
              f"N={n} C={c} E={e}: L0={n0} L1={ns} L2={n2} L3={n3} "
              f"orbits={n_orbits}", flush=True)
        sys.exit(1)
    csv_rows.append(dict(N=n, C=c, E=e, L0=n0, L1=ns, L2=n2, L3=n3,
                         orbits=n_orbits))

    # -- (d) h invariance under canonical_L3 ----------------------------
    heus = {name: H.make(name) for name in ("h0", "h1", "h2", "h3", "h4")}
    for i, s in enumerate(states):
        cs = dom3.canonical_state(s)
        for name, heu in heus.items():
            if heu.h(s) != heu.h(cs):
                print(f"\n*** GATE (d) FAIL: {name}(s) != {name}(canon3(s)) "
                      f"N={n} C={c} E={e}:\n{dom3.pretty(s)}", flush=True)
                sys.exit(1)

    # -- (e) h* invariance under canonical_L3 (M1) ----------------------
    _index, fwd = build_graph(dom1, states)
    hs1, _ = h_star(dom1, states, fwd, "M1")
    index_l1 = {dom1.key(s): i for i, s in enumerate(states)}
    for i, s in enumerate(states):
        j = index_l1[dom1.key(dom3.canonical_state(s))]
        if hs1[i] != hs1[j]:
            print(f"\n*** GATE (e) FAIL: h*(s)={hs1[i]} != "
                  f"h*(canon3(s))={hs1[j]} N={n} C={c} E={e}:\n"
                  f"{dom3.pretty(s)}", flush=True)
            sys.exit(1)

    # -- (f) optimality + path validity at L2 and L3 --------------------
    finite = [i for i in range(ns) if hs1[i] != INF]
    rng = random.Random(20260809)
    picks = rng.sample(finite, min(sample, len(finite)))
    alg = AStarEarly(assert_no_reopen=True, goal_test="early")
    runs = 0
    for dom in (dom2, dom3):
        for name, heu in heus.items():
            for i in picks:
                s0 = states[i]
                r = alg.solve(dom, s0, heu, LIMITS)
                runs += 1
                if not r.solved or r.cost != hs1[i]:
                    print(f"\n*** GATE (f) FAIL ({dom.canon_level}, {name}) "
                          f"N={n} C={c} E={e}: A*="
                          f"{r.cost if r.solved else 'UNSOLVED'} "
                          f"h*={hs1[i]}\n{dom.pretty(s0)}", flush=True)
                    sys.exit(1)
                if r.cost > 0:
                    dom.validate_solution(s0, r.moves)   # concrete replay

    print(f"[canon gates OK] N={n} C={c} E={e}: "
          f"L0={n0} L1={ns} L2={n2} L3={n3} orbits={n_orbits} | "
          f"safe(a) complete(b) ladder(c) h-inv(d) h*-inv(e) on all {ns} "
          f"states; (f) {runs} A* runs == h*, all paths validated "
          f"({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--configs", default="",
                    help="comma list like '3,3,1;3,3,2' to run a subset "
                         "(ladder CSV is appended per config)")
    args = ap.parse_args()
    if args.fast:
        args.sample = 10
    configs = CONFIGS if not args.configs else [
        tuple(int(x) for x in grp.split(","))
        for grp in args.configs.split(";")]

    t0 = time.time()
    rows = []
    for (n, c, e) in configs:
        gate_config(n, c, e, args.sample, rows)
    path = "results/canon_ladder.csv"
    header = not os.path.exists(path) or not args.configs
    mode = "w" if header else "a"
    with open(path, mode, newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if header:
            w.writeheader()
        w.writerows(rows)
    print(f"\nALL CANON GATES PASSED in {time.time()-t0:.0f}s; "
          f"ladder table -> results/canon_ladder.csv", flush=True)
