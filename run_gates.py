"""Milestone 2 correctness gates (run BEFORE the calibration pilot).

Gate 1  ORACLE GATE.  For every oracle-enumerable config (N=3 C in {3,4}
        E in {1,2,3}; N=4 C=3 E in {1,2}): sample >= `--sample` states
        with finite h*, run A*-EARLY with each of h0..h4 from each, and
        assert returned cost == h* EXACTLY under M1.  Repeat a smaller
        sample under M2 (h0..h5; h5 is M2-admissible).  Any mismatch is a
        stop-the-line bug and aborts with the offending state printed.
Gate 2  Every solved run's move list passes Domain.validate_solution
        (checked inline on every single oracle-gate run).
Gate 3  reopened == 0 on every run with a consistent heuristic --
        enforced as a hard assertion inside A* (assert_no_reopen=True).
Gate 4  Dominance ordering sanity: on a shared instance set, mean
        expansions must not increase along h0 -> h1 -> h3 -> h4 (report
        per-instance, hard-check only the means, per the M2 prompt).
Gate 5  Determinism: two runs of the same config produce identical
        deterministic Stats and identical move lists.

Usage:  python3 scripts/run_gates.py [--sample 200] [--m2-sample 60]
                                     [--fast]   (tiny samples, smoke only)
"""

from __future__ import annotations

import argparse
import random
import sys
import time

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


def oracle_gate(n, c, e, sample, m2_sample, seed=12345):
    t0 = time.time()
    dom1 = Domain(n, c, e, canon_level="L1", cost_model="M1")
    states = enumerate_space(dom1)
    _index, fwd = build_graph(dom1, states)
    hs1, _ = h_star(dom1, states, fwd, "M1")
    hs2, _ = h_star(dom1, states, fwd, "M2")
    finite = [i for i in range(len(states)) if hs1[i] is not INF and hs1[i] != INF]
    rng = random.Random(seed)
    picks = rng.sample(finite, min(sample, len(finite)))

    early = AStarEarly(assert_no_reopen=True, goal_test="early")
    late = AStarEarly(assert_no_reopen=True, goal_test="late")
    runs = 0
    t_h0 = 0.0
    m2_early_gaps = []
    # M1: the EARLY variant itself must be exactly optimal (the prompt's
    # stop-the-line assertion).  M2: EARLY is *provably allowed* to
    # overshoot (non-unit costs; verified by counterexample in the gate
    # development log), so the implementation-correctness assertion moves
    # to LATE, and EARLY's gap is recorded as free RQ5 pilot data.
    for cm, hs, names, npick in (
            ("M1", hs1, ("h0", "h1", "h2", "h3", "h4"), picks),
            ("M2", hs2, ("h0", "h1", "h2", "h3", "h4", "h5"),
             picks[:m2_sample])):
        dom = Domain(n, c, e, canon_level="L1", cost_model=cm)
        for name in names:
            heu = H.make(name)
            for i in npick:
                s0 = states[i]
                alg = early if cm == "M1" else late
                r = alg.solve(dom, s0, heu, LIMITS)
                runs += 1
                if not r.solved or r.cost != hs[i]:
                    print(f"\n*** ORACLE MISMATCH ({cm}, {alg.name}, {name}) "
                          f"N={n} C={c} E={e}: A*={r.cost if r.solved else 'UNSOLVED'} "
                          f"h*={hs[i]}\n{dom.pretty(s0)}", flush=True)
                    sys.exit(1)
                if r.cost > 0:                    # gate 2, every run
                    dom.validate_solution(s0, r.moves)
                    if cm == "M1":
                        assert r.cost == len(r.moves)
                if cm == "M2":                    # measure EARLY's M2 gap
                    re_ = early.solve(dom, s0, heu, LIMITS)
                    runs += 1
                    assert re_.solved and re_.cost >= hs[i]
                    if re_.cost > 0:
                        dom.validate_solution(s0, re_.moves)
                    m2_early_gaps.append(re_.cost - hs[i])
                if name == "h0":
                    t_h0 += r.stats.wall_time_s
    gaps_pos = [g for g in m2_early_gaps if g > 0]
    print(f"[gate1+2+3 OK] N={n} C={c} E={e}: {runs} A* runs "
          f"(M1 EARLY x{len(picks)} x5h == h*; M2 LATE x{min(m2_sample, len(picks))} x6h == h*), "
          f"all solutions validated, 0 reopenings; "
          f"M2 EARLY suboptimal on {len(gaps_pos)}/{len(m2_early_gaps)} "
          f"(max gap {max(m2_early_gaps) if m2_early_gaps else 0}) "
          f"({time.time()-t0:.0f}s, h0 share {t_h0:.0f}s)", flush=True)


def dominance_gate(runs_per_cfg=30):
    """Gate 4: mean expansions non-increasing along the dominance chain.
    (Per-instance inversions are legal -- tie-breaking noise -- so we
    report them but hard-check only the means, as the prompt says.)"""
    alg = AStarEarly(assert_no_reopen=True)
    for (n, c, e) in [(3, 4, 2), (4, 3, 2)]:
        dom = Domain(n, c, e)
        means = {}
        inversions = 0
        per_h = {name: [] for name in ("h0", "h1", "h2", "h3", "h4")}
        seeds = [s for s in range(200) if dom.solvable(dom.generate_instance(s))][:runs_per_cfg]
        for seed in seeds:
            s0 = dom.generate_instance(seed)
            row = {}
            for name in per_h:
                r = alg.solve(dom, s0, H.make(name), LIMITS)
                assert r.solved
                row[name] = r.stats.expanded
                per_h[name].append(r.stats.expanded)
            if not (row["h0"] >= row["h1"] >= row["h3"] >= row["h4"]):
                inversions += 1
        for name, xs in per_h.items():
            means[name] = sum(xs) / len(xs)
        chain_ok = means["h0"] >= means["h1"] >= means["h3"] >= means["h4"]
        print(f"[gate4 {'OK' if chain_ok else 'FAIL'}] N={n} C={c} E={e} "
              f"mean expanded: " +
              " ".join(f"{k}={means[k]:.1f}" for k in ("h0", "h1", "h2", "h3", "h4")) +
              f"; per-instance inversions {inversions}/{len(seeds)}", flush=True)
        assert chain_ok, "mean expansions increased along the dominance chain"


def determinism_gate():
    """Gate 5: identical deterministic Stats + identical moves, twice."""
    alg = AStarEarly(assert_no_reopen=True)
    for (n, c, e, seed) in [(4, 4, 2, 7), (5, 4, 2, 3)]:
        dom = Domain(n, c, e)
        s0 = dom.generate_instance(seed)
        r1 = alg.solve(dom, s0, H.make("h4"), LIMITS)
        r2 = alg.solve(dom, s0, H.make("h4"), LIMITS)
        assert r1.stats.deterministic_tuple() == r2.stats.deterministic_tuple()
        assert r1.moves == r2.moves and r1.cost == r2.cost
        print(f"[gate5 OK] N={n} C={c} E={e} seed={seed}: two runs "
              f"bit-identical (cost={r1.cost}, expanded={r1.stats.expanded})",
              flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--m2-sample", type=int, default=60)
    ap.add_argument("--fast", action="store_true")
    args = ap.parse_args()
    if args.fast:
        args.sample, args.m2_sample = 20, 8

    t0 = time.time()
    determinism_gate()
    dominance_gate(runs_per_cfg=10 if args.fast else 30)
    for (n, c, e) in CONFIGS:
        oracle_gate(n, c, e, args.sample, args.m2_sample)
    print(f"\nALL GATES PASSED in {time.time()-t0:.0f}s", flush=True)
