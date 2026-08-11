"""Generate the Stage A (M3b) grid JSONs from results/stageA_seeds.json.

Why one grid file per (N,C,E) cell: the runner's grid dict holds ONE
seed list for the whole cross product, and mechanism (b) gives each cell
its own 50 precomputed solvable seeds.  Splitting per cell keeps the
runner unchanged (its resume works across files because run_key covers
the full config, and all files append to the same CSV).

Emits, under grids/:
  stageA_N{n}E{e}.json          -- solvable core+h1 arm: canon {L0..L3}
                                   x heuristic {h1,h4} x 50 solvable seeds
  stageA_unsolv_N{n}E1.json     -- prediction-iv workload: canon {L0..L3}
                                   x h1 x 50 unsolvable seeds
All A*-EARLY, M1, goal_test early, runner-default tie-break/dup_policy,
caps 60s / 5e6 generated / 3072 MB (design doc 5.2).
`solvable_filter` is ON everywhere so `instance_solvable` is recorded.
Stdlib only; deterministic.
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(__file__)
SEEDS = os.path.join(HERE, "..", "results", "stageA_seeds.json")
OUT = os.path.join(HERE, "..", "grids")

LIMITS = {"wall_s": 60, "max_generated": 5_000_000, "max_rss_mb": 3072}
COMMON = {"cost_model": "M1", "algorithm": "astar_early", "algo_param": "",
          "goal_test": "early", "canon_level": ["L0", "L1", "L2", "L3"]}


def emit(path, grid, solvable_filter=True):
    # solvable_filter=True short-circuits unsolvable seeds into
    # "unsolvable_instance" rows WITHOUT running the search -- correct
    # for the solvable core, fatal for the prediction-(iv) exhaustion
    # workload, whose whole point is that A* runs to exhaustion.  The
    # unsolvable grids therefore set it False; their seeds' unsolvability
    # is documented in results/stageA_seeds.json and re-proven by every
    # row ending solved=False with no cap triggered.
    spec = {"grid": grid, "limits": LIMITS, "solvable_filter": solvable_filter}
    with open(path, "w") as fh:
        json.dump(spec, fh, indent=1)
    print("wrote", os.path.normpath(path))


def main():
    os.makedirs(OUT, exist_ok=True)
    seeds = json.load(open(SEEDS))
    for key, cell in seeds["solvable"].items():
        n, c, e = (int(x) for x in key.split(","))
        grid = dict(COMMON, n_colors=n, capacity=c, n_empty=e,
                    heuristic=["h1", "h4"], instance_seed=cell["seeds"])
        emit(os.path.join(OUT, f"stageA_N{n}E{e}.json"), grid)
    for key, cell in seeds["unsolvable"].items():
        n, c, e = (int(x) for x in key.split(","))
        grid = dict(COMMON, n_colors=n, capacity=c, n_empty=e,
                    heuristic="h1", instance_seed=cell["seeds"])
        emit(os.path.join(OUT, f"stageA_unsolv_N{n}E{e}.json"), grid,
             solvable_filter=False)


if __name__ == "__main__":
    main()
