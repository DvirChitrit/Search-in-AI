"""Stage A (M3b) seed precomputation -- mechanism (b) of the M3b prompt.

For every Stage A cell (N in {3,4,5,6}, C=4, E in {1,2,3}) enumerate
seeds 0,1,2,... with `Domain.solvable` until 50 SOLVABLE seeds are
collected, and record the observed unsolvable fraction on the way (free
RQ4-adjacent data; it also cross-checks M2's measured fractions).

For the unsolvable-only workload (prediction iv) collect the first 50
UNSOLVABLE seeds at (N in {4,5}, C=4, E=1).

Output: results/stageA_seeds.json
    {"solvable": {"N,C,E": {"seeds": [...50...], "seeds_scanned": k,
                             "unsolvable_frac": f, "undecided": u}},
     "unsolvable": {...same shape...}}

Solvability is a property of (N, C, E, seed) only -- canon level and
heuristic do not enter -- so one scan serves every arm of the grid.
Stdlib only; deterministic; re-runnable.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ballsort.domain import Domain  # noqa: E402

C = 4
SOLVABLE_CELLS = [(n, C, e) for n in (3, 4, 5, 6) for e in (1, 2, 3)]
UNSOLVABLE_CELLS = [(4, C, 1), (5, C, 1)]
WANT = 50
SEED_BUDGET = 5000            # hard stop per cell; report if hit
NODE_CAP = 2_000_000          # same cap the runner's filter uses


def scan(n, c, e, want_solvable: bool):
    dom = Domain(n, c, e, canon_level="L1", cost_model="M1")
    hits, scanned, undecided = [], 0, 0
    n_unsolvable = 0
    seed = 0
    t0 = time.time()
    while len(hits) < WANT and seed < SEED_BUDGET:
        s0 = dom.generate_instance(seed)
        sv = dom.solvable(s0, node_cap=NODE_CAP)
        scanned += 1
        if sv is None:
            undecided += 1
        elif sv is False:
            n_unsolvable += 1
            if not want_solvable:
                hits.append(seed)
        else:
            if want_solvable:
                hits.append(seed)
        seed += 1
    frac = n_unsolvable / scanned if scanned else float("nan")
    print(f"  N={n} C={c} E={e} want={'solv' if want_solvable else 'unsolv'}: "
          f"{len(hits)}/{WANT} in {scanned} seeds "
          f"(unsolvable frac {frac:.3f}, undecided {undecided}, "
          f"{time.time()-t0:.1f}s)", flush=True)
    return {"seeds": hits, "seeds_scanned": scanned,
            "unsolvable_frac": round(frac, 4), "undecided": undecided}


def main():
    out = {"solvable": {}, "unsolvable": {}}
    print("[stageA_seeds] solvable cells:")
    for n, c, e in SOLVABLE_CELLS:
        out["solvable"][f"{n},{c},{e}"] = scan(n, c, e, True)
    print("[stageA_seeds] unsolvable cells (prediction iv):")
    for n, c, e in UNSOLVABLE_CELLS:
        out["unsolvable"][f"{n},{c},{e}"] = scan(n, c, e, False)
    path = os.path.join(os.path.dirname(__file__), "..",
                        "results", "stageA_seeds.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"[stageA_seeds] wrote {os.path.normpath(path)}")


if __name__ == "__main__":
    main()
