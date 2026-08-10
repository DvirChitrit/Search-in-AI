"""Milestone 3a, Deliverable 3: per-level canonicalization cost/benefit
on REAL A* runs at Stage-A-ish sizes -- the search half of RQ1.

Grid (fixed in this file so the run is fully reproducible from the repo):
  N in {4, 5, 6}, C = 4, E in {1, 2}
  heuristics {h1, h4}   -- h1 (weak) makes the L0->L1 effect visible;
                           h4 shows the deployed-heuristic contrast
                           (calibration report: h4 hides L0 inflation).
  canon levels {L0, L1, L2, L3}
  --seeds solvable instances per (N, E) cell, found by seed oversampling
  with Domain.solvable (E=1 needs it; unsolvable seeds are skipped and
  logged).  Caps per run: 60 s wall / 5e6 generated / 3072 MB.

Same instance set for every (heuristic, level) arm, so the per-level
comparison is paired.  A*-EARLY under M1 (Stage A's algorithm/cost
model); canon_calls / canon_time_s accounting stays ON.

Output: one CSV row per run -> results/canon_pilot.csv (crash-safe
append with a resume check on (N,C,E,seed,heuristic,level), mirroring
the runner's run_key discipline without touching runner.py, which is
read-only this session).  Every number in canon_report.md regenerates
via  python3 analysis/canon_summary.py results/canon_pilot.csv .

Usage: python3 scripts/measure_canon.py [--seeds 5] [--out results/canon_pilot.csv]
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

sys.path.insert(0, ".")

from ballsort.domain import Domain
from ballsort import heuristics as H
from ballsort.algorithms.base import Limits
from ballsort.algorithms.astar import AStarEarly

CELLS = [(n, 4, e) for n in (4, 5, 6) for e in (1, 2)]
LEVELS = ("L0", "L1", "L2", "L3")
HEURISTICS = ("h1", "h4")
LIMITS = Limits(wall_s=60.0, max_generated=5_000_000, max_rss_mb=3072.0)

FIELDS = ["N", "C", "E", "seed", "heuristic", "canon_level",
          "solved", "timeout_reason", "cost",
          "expanded", "generated", "duplicates_detected", "reopened",
          "canon_calls", "canon_time_s", "wall_time_s", "h_evaluations",
          "open_max_size", "closed_max_size", "peak_rss_mb"]


def solvable_seeds(n, c, e, want, log=print):
    """First `want` seeds whose instance is solvable (decision via the
    satisficing DFS), scanning seeds 0,1,2,...; reports the unsolvable
    fraction encountered -- do not silently filter (design doc 2.10)."""
    dom = Domain(n, c, e)
    out, tried, seed = [], 0, 0
    while len(out) < want and seed < 5000:
        s0 = dom.generate_instance(seed)
        v = dom.solvable(s0)
        tried += 1
        if v is True:
            out.append(seed)
        seed += 1
    log(f"  seeds N={n} C={c} E={e}: {len(out)} solvable from {tried} "
        f"sampled ({100*(1-len(out)/tried):.0f}% unsolvable)")
    return out


def done_keys(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {(int(r["N"]), int(r["C"]), int(r["E"]), int(r["seed"]),
                 r["heuristic"], r["canon_level"])
                for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--out", default="results/canon_pilot.csv")
    args = ap.parse_args()

    done = done_keys(args.out)
    new_file = not os.path.exists(args.out)
    f = open(args.out, "a", newline="")
    w = csv.DictWriter(f, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
        f.flush()

    alg = AStarEarly(goal_test="early")     # reopen COUNTED, not asserted
    t00 = time.time()
    for (n, c, e) in CELLS:
        seeds = solvable_seeds(n, c, e, args.seeds)
        for seed in seeds:
            for heu_name in HEURISTICS:
                for lvl in LEVELS:
                    k = (n, c, e, seed, heu_name, lvl)
                    if k in done:
                        continue
                    dom = Domain(n, c, e, canon_level=lvl)
                    s0 = dom.generate_instance(seed)
                    r = alg.solve(dom, s0, H.make(heu_name), LIMITS)
                    if r.solved and r.cost > 0:
                        dom.validate_solution(s0, r.moves)
                    st = r.stats
                    w.writerow(dict(
                        N=n, C=c, E=e, seed=seed, heuristic=heu_name,
                        canon_level=lvl, solved=int(r.solved),
                        timeout_reason=r.timeout_reason or "",
                        cost=r.cost if r.solved else "",
                        expanded=st.expanded, generated=st.generated,
                        duplicates_detected=st.duplicates_detected,
                        reopened=st.reopened, canon_calls=st.canon_calls,
                        canon_time_s=round(st.canon_time_s, 6),
                        wall_time_s=round(st.wall_time_s, 4),
                        h_evaluations=st.h_evaluations,
                        open_max_size=st.open_max_size,
                        closed_max_size=st.closed_max_size,
                        peak_rss_mb=round(st.peak_rss_mb, 1)))
                    f.flush()               # crash-safe: row-at-a-time
                    print(f"  N={n} E={e} seed={seed} {heu_name} {lvl}: "
                          f"{'ok' if r.solved else r.timeout_reason} "
                          f"exp={st.expanded} gen={st.generated} "
                          f"t={st.wall_time_s:.2f}s "
                          f"canon={1e6*st.canon_time_s/max(1,st.canon_calls):.1f}us/call",
                          flush=True)
    f.close()
    print(f"done in {time.time()-t00:.0f}s -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
