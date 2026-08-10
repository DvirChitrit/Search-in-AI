"""Milestone 3a analysis: aggregate results/canon_pilot.csv (and print
results/canon_ladder.csv) into the tables in results/canon_report.md.

This is the seed of the analysis/ layer (design doc 6.1): every number
in the report regenerates by running this script on the committed CSVs
-- nothing lives only in a chat transcript (course guideline / prompt
plan failure-point mandate).

Usage: python3 analysis/canon_summary.py [results/canon_pilot.csv]
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict


def geomean(xs):
    if not xs:
        return float("nan")
    p = 1.0
    for x in xs:
        p *= x
    return p ** (1.0 / len(xs))


def load(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main(pilot_path="results/canon_pilot.csv",
         ladder_path="results/canon_ladder.csv"):
    # ------------------------------------------------------------------
    # Table 0: the state-space ladder (gate 2c output, printed verbatim).
    # ------------------------------------------------------------------
    if os.path.exists(ladder_path):
        print("== State-space ladder (distinct keys; exact, exhaustive) ==")
        print(f"{'N':>2} {'C':>2} {'E':>2} {'L0':>12} {'L1':>8} {'L2':>7} "
              f"{'L3':>7} {'orbits':>7} {'L0/L1':>7} {'L1/L3':>6}")
        for r in load(ladder_path):
            l0, l1, l2, l3, orb = (int(r[k]) for k in
                                   ("L0", "L1", "L2", "L3", "orbits"))
            print(f"{r['N']:>2} {r['C']:>2} {r['E']:>2} {l0:>12} {l1:>8} "
                  f"{l2:>7} {l3:>7} {orb:>7} {l0/l1:>7.1f} {l1/l3:>6.2f}")
        print()

    rows = load(pilot_path)
    levels = ("L0", "L1", "L2", "L3")

    # Index: (N,E,heuristic,level) -> list of rows; and pair by instance.
    by_arm = defaultdict(list)
    by_inst = defaultdict(dict)      # (N,E,h,seed) -> level -> row
    for r in rows:
        n, e = int(r["N"]), int(r["E"])
        by_arm[(n, e, r["heuristic"], r["canon_level"])].append(r)
        by_inst[(n, e, r["heuristic"], int(r["seed"]))][r["canon_level"]] = r

    # ------------------------------------------------------------------
    # Table 1: per-node canonicalization cost per level (us/call).
    # ------------------------------------------------------------------
    print("== Per-node canonicalization cost (canon_time_s/canon_calls, "
          "us/call; mean over runs) and canon share of wall time ==")
    print(f"{'N':>2} {'E':>2} {'h':>3} " +
          " ".join(f"{l+'us':>7} {l+'%':>5}" for l in levels))
    for n in (4, 5, 6):
        for e in (1, 2):
            for h in ("h1", "h4"):
                cells = []
                for l in levels:
                    rs = by_arm.get((n, e, h, l), [])
                    us = [1e6 * float(r["canon_time_s"]) /
                          max(1, int(r["canon_calls"])) for r in rs]
                    share = [float(r["canon_time_s"]) /
                             max(1e-9, float(r["wall_time_s"])) for r in rs]
                    cells.append((sum(us) / len(us) if us else float("nan"),
                                  100 * sum(share) / len(share) if share
                                  else float("nan")))
                print(f"{n:>2} {e:>2} {h:>3} " +
                      " ".join(f"{u:>7.1f} {s:>5.1f}" for u, s in cells))
    print()

    # ------------------------------------------------------------------
    # Table 2: node-count and wall-clock ratios vs L1 (paired geomeans).
    # Solved-everywhere instances only, so ratios are like-for-like.
    # ------------------------------------------------------------------
    print("== Paired per-instance ratios (geomean over instances solved "
          "at every level) ==")
    hdr = (f"{'N':>2} {'E':>2} {'h':>3} {'inst':>4} "
           f"{'expL0/L1':>8} {'genL0/L1':>8} {'dupL0/L1':>8} {'tL0/L1':>7} "
           f"{'expL1/L3':>8} {'genL1/L3':>8} {'tL1/tL3':>7} "
           f"{'expL2/L3':>8} {'tL2/tL3':>7}")
    print(hdr)
    for n in (4, 5, 6):
        for e in (1, 2):
            for h in ("h1", "h4"):
                packs = [v for (kn, ke, kh, _s), v in by_inst.items()
                         if (kn, ke, kh) == (n, e, h)
                         and all(l in v and v[l]["solved"] == "1"
                                 for l in levels)]
                if not packs:
                    continue
                def ratio(a, b, field, cast=int):
                    return geomean([max(1, cast(p[a][field])) /
                                    max(1, cast(p[b][field]))
                                    if cast is int else
                                    max(1e-6, float(p[a][field])) /
                                    max(1e-6, float(p[b][field]))
                                    for p in packs])
                print(f"{n:>2} {e:>2} {h:>3} {len(packs):>4} "
                      f"{ratio('L0','L1','expanded'):>8.2f} "
                      f"{ratio('L0','L1','generated'):>8.2f} "
                      f"{ratio('L0','L1','duplicates_detected'):>8.2f} "
                      f"{ratio('L0','L1','wall_time_s',float):>7.2f} "
                      f"{ratio('L1','L3','expanded'):>8.2f} "
                      f"{ratio('L1','L3','generated'):>8.2f} "
                      f"{ratio('L1','L3','wall_time_s',float):>7.2f} "
                      f"{ratio('L2','L3','expanded'):>8.2f} "
                      f"{ratio('L2','L3','wall_time_s',float):>7.2f}")
    print("\n(ratios > 1 mean the LEFT level costs more: expL0/L1=3 means "
          "L1 expands 3x fewer nodes than L0; tL1/tL3 < 1 means L1 is "
          "FASTER than L3 in wall-clock.)")

    # ------------------------------------------------------------------
    # Coverage within the caps.
    # ------------------------------------------------------------------
    print("\n== Coverage within caps (60s / 5e6 generated / 3072MB) ==")
    tot = defaultdict(lambda: [0, 0])
    for r in rows:
        t = tot[(r["heuristic"], r["canon_level"])]
        t[0] += 1
        t[1] += int(r["solved"])
    for (h, l), (a, b) in sorted(tot.items()):
        note = "" if a == b else f"  <-- {a-b} timeout(s)"
        print(f"  {h} {l}: {b}/{a} solved{note}")


if __name__ == "__main__":
    main(*sys.argv[1:])
