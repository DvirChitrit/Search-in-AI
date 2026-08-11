"""Milestone 3b analysis: Stage A (RQ1, the canonicalization ablation).

Reads ONLY committed artifacts:
    results/stageA.csv          -- 4,800 solvable-core + h1-arm runs
    results/stageA_unsolv.csv   -- 400 prediction-(iv) exhaustion runs
    results/canon_ladder.csv    -- M3a's exact state-space ladder (reused)

Regenerates EVERY number and figure in results/stageA_report.md:
    results/figures/stageA_h1.png, stageA_h4.png   (THE RQ1 figure)
    stdout: coverage, per-level medians/geomeans, paired ratio tables
            (L0/L1, L1/L2, L2/L3, L1/L3), optimal-cost cross-level
            consistency check, unsolvable-cell comparison.

Method notes (design doc 6.1 + M3a conventions):
  * Paired ratios are geomeans over SOLVED-EVERYWHERE instances only --
    an instance enters a cell's ratio row iff all four canon levels
    solved it within caps under that heuristic.  Coverage is reported
    separately so timeouts are never hidden inside an average.
  * The analysis layer is NOT the hot path: matplotlib is allowed here
    (declared in requirements.txt); ballsort/ itself stays stdlib-only.

Usage: python3 analysis/stageA_analysis.py
"""

from __future__ import annotations

import csv
import math
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
FIGDIR = os.path.join(RESULTS, "figures")

LEVELS = ["L0", "L1", "L2", "L3"]
RATIO_PAIRS = [("L0", "L1"), ("L1", "L2"), ("L2", "L3"), ("L1", "L3")]
METRICS = ["expanded", "generated", "duplicates_detected", "wall_time_s"]


def load(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def geomean(xs):
    xs = [x for x in xs if x > 0 and not math.isnan(x)]
    if not xs:
        return float("nan")
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def median(xs):
    xs = sorted(x for x in xs if not math.isnan(x))
    if not xs:
        return float("nan")
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def index_rows(rows):
    """(N, E, heuristic, level) -> {seed: row}  (solved rows keep stats)."""
    ix = defaultdict(dict)
    for r in rows:
        key = (int(r["n_colors"]), int(r["n_empty"]),
               r["heuristic"], r["canon_level"])
        ix[key][int(r["instance_seed"])] = r
    return ix


def solved(r):
    return r is not None and r.get("solved") == "True"


# ------------------------------------------------------------------ #
# 1. Coverage                                                        #
# ------------------------------------------------------------------ #

def coverage_table(ix, cells, heuristics, out):
    out.append("\n## Coverage: solved-within-caps per cell (of 50)\n")
    hdr = "| N | E | h | " + " | ".join(LEVELS) + " | solved-everywhere |"
    out.append(hdr)
    out.append("|---|---|---|" + "---:|" * (len(LEVELS) + 1))
    for (n, e) in cells:
        for h in heuristics:
            counts, common = [], None
            for lvl in LEVELS:
                cell = ix.get((n, e, h, lvl), {})
                sv = {sd for sd, r in cell.items() if solved(r)}
                counts.append(len(sv))
                common = sv if common is None else (common & sv)
            out.append(f"| {n} | {e} | {h} | " +
                       " | ".join(str(c) for c in counts) +
                       f" | {len(common)} |")


# ------------------------------------------------------------------ #
# 2. Per-level medians + paired ratios                               #
# ------------------------------------------------------------------ #

def ratio_tables(ix, cells, heuristics, out):
    for metric, short in [("expanded", "exp"), ("generated", "gen"),
                          ("duplicates_detected", "dup"),
                          ("wall_time_s", "t")]:
        out.append(f"\n## {metric}: per-level median (solved rows) and "
                   f"paired geomean ratios (solved-everywhere)\n")
        out.append("| N | E | h | " +
                   " | ".join(f"med {l}" for l in LEVELS) + " | " +
                   " | ".join(f"{short} {a}/{b}" for a, b in RATIO_PAIRS) +
                   " |")
        out.append("|---|---|---|" + "---:|" * (len(LEVELS) + len(RATIO_PAIRS)))
        for (n, e) in cells:
            for h in heuristics:
                cellmap = {l: ix.get((n, e, h, l), {}) for l in LEVELS}
                common = None
                for l in LEVELS:
                    sv = {sd for sd, r in cellmap[l].items() if solved(r)}
                    common = sv if common is None else (common & sv)
                meds = []
                for l in LEVELS:
                    vals = [fnum(r[metric]) for r in cellmap[l].values()
                            if solved(r)]
                    m = median(vals)
                    meds.append(f"{m:.4f}" if metric == "wall_time_s"
                                else f"{m:.0f}")
                rats = []
                for a, b in RATIO_PAIRS:
                    pairs = []
                    for sd in common:
                        va = fnum(cellmap[a][sd][metric])
                        vb = fnum(cellmap[b][sd][metric])
                        if va > 0 and vb > 0:
                            pairs.append(va / vb)
                    rats.append(f"{geomean(pairs):.2f}")
                out.append(f"| {n} | {e} | {h} | " + " | ".join(meds) +
                           " | " + " | ".join(rats) + " |")


# ------------------------------------------------------------------ #
# 3. Optimal-cost consistency across levels (free soundness regress) #
# ------------------------------------------------------------------ #

def cost_consistency(ix, cells, heuristics, out):
    bad, checked = [], 0
    for (n, e) in cells:
        for h in heuristics:
            per_seed = defaultdict(dict)
            for lvl in LEVELS:
                for sd, r in ix.get((n, e, h, lvl), {}).items():
                    if solved(r):
                        per_seed[sd][lvl] = fnum(r["solution_cost"])
            for sd, costs in per_seed.items():
                if len(costs) >= 2:
                    checked += 1
                    if len({round(c, 9) for c in costs.values()}) != 1:
                        bad.append((n, e, h, sd, costs))
    out.append(f"\n## Cross-level optimal-cost consistency: "
               f"{checked} (cell,seed) groups checked, "
               f"{len(bad)} mismatches"
               + (" -- SOUNDNESS REGRESSION!" if bad else " (all identical)"))
    for b in bad[:20]:
        out.append(f"  MISMATCH {b}")


# ------------------------------------------------------------------ #
# 4. Unsolvable-cell (prediction iv) comparison                      #
# ------------------------------------------------------------------ #

def unsolv_table(rows, out):
    out.append("\n## Prediction (iv): unsolvable E=1 exhaustion workload "
               "(h1; medians over 50 instances)\n")
    ix = index_rows(rows)
    cells = sorted({(int(r["n_colors"]), int(r["n_empty"])) for r in rows})
    out.append("| N | E | level | completed | median exp | median gen "
               "| median wall_s | max exp |")
    out.append("|---|---|---|---:|---:|---:|---:|---:|")
    for (n, e) in cells:
        for lvl in LEVELS:
            cell = ix.get((n, e, "h1", lvl), {})
            done = [r for r in cell.values()
                    if r["timeout_reason"] in ("", "None", None)
                    or fnum(r["expanded"]) >= 0]
            # exhaustion completed = search ended without cap trigger
            comp = [r for r in cell.values()
                    if r.get("solved") == "False"
                    and r.get("timeout_reason") in ("", "None")]
            exps = [fnum(r["expanded"]) for r in comp]
            gens = [fnum(r["generated"]) for r in comp]
            ts = [fnum(r["wall_time_s"]) for r in comp]
            mx = max(exps) if exps else float("nan")
            out.append(f"| {n} | {e} | {lvl} | {len(comp)}/{len(cell)} "
                       f"| {median(exps):.0f} | {median(gens):.0f} "
                       f"| {median(ts):.4f} | {mx:.0f} |")


# ------------------------------------------------------------------ #
# 5. The state-space half (reuse M3a's ladder verbatim)              #
# ------------------------------------------------------------------ #

def ladder_table(out):
    path = os.path.join(RESULTS, "canon_ladder.csv")
    out.append("\n## State-space half of RQ1 (M3a's exact ladder, reused "
               "not recomputed -- results/canon_ladder.csv)\n")
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        out.append("| N | C | E | L0 | L1 | L2 | L3 | L0/L1 | L1/L3 |")
        out.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
        for r in rd:
            l0, l1, l3 = int(r["L0"]), int(r["L1"]), int(r["L3"])
            out.append(f"| {r['N']} | {r['C']} | {r['E']} | {l0:,} | {l1:,} "
                       f"| {int(r['L2']):,} | {l3:,} "
                       f"| {l0/l1:.1f} | {l1/l3:.2f} |")


# ------------------------------------------------------------------ #
# THE FIGURE                                                         #
# ------------------------------------------------------------------ #

def make_figure(ix, cells, heuristic, path):
    """2 rows (geomean expanded / geomean wall s) x 3 cols (E=1,2,3);
    lines = canon level; x = N; log y."""
    Es = sorted({e for _, e in cells})
    Ns = sorted({n for n, _ in cells})
    fig, axes = plt.subplots(2, len(Es), figsize=(11, 6.2),
                             sharex=True)
    colors = {"L0": "#888888", "L1": "#1f77b4",
              "L2": "#ff7f0e", "L3": "#d62728"}
    markers = {"L0": "s", "L1": "o", "L2": "^", "L3": "v"}
    for col, e in enumerate(Es):
        for row, metric in enumerate(["expanded", "wall_time_s"]):
            ax = axes[row][col]
            for lvl in LEVELS:
                xs, ys = [], []
                for n in Ns:
                    vals = [fnum(r[metric])
                            for r in ix.get((n, e, heuristic, lvl),
                                            {}).values() if solved(r)]
                    g = geomean(vals)
                    if not math.isnan(g):
                        xs.append(n)
                        ys.append(g)
                ax.plot(xs, ys, color=colors[lvl], marker=markers[lvl],
                        label=lvl, lw=1.6, ms=5)
            ax.set_yscale("log")
            ax.grid(True, which="both", alpha=0.25, lw=0.5)
            if row == 0:
                ax.set_title(f"E = {e}")
            if row == 1:
                ax.set_xlabel("N (colors), C = 4")
            ax.set_xticks(Ns)
            if col == 0:
                ax.set_ylabel("geomean expanded" if row == 0
                              else "geomean wall time (s)")
    axes[0][0].legend(title="canon", fontsize=8, title_fontsize=8)
    fig.suptitle(f"Stage A (RQ1): canonicalization ablation, A*-EARLY, M1, "
                 f"{heuristic}  (50 solvable instances/cell)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=160)
    plt.close(fig)
    print(f"[fig] wrote {os.path.normpath(path)}")


# ------------------------------------------------------------------ #

def main():
    stagea = load(os.path.join(RESULTS, "stageA.csv"))
    unsolv = load(os.path.join(RESULTS, "stageA_unsolv.csv"))
    os.makedirs(FIGDIR, exist_ok=True)

    ix = index_rows(stagea)
    cells = sorted({(int(r["n_colors"]), int(r["n_empty"]))
                    for r in stagea})
    heuristics = sorted({r["heuristic"] for r in stagea})

    out = ["# Stage A analysis (auto-generated by "
           "analysis/stageA_analysis.py)",
           f"rows: stageA={len(stagea)}, unsolv={len(unsolv)}"]
    ladder_table(out)
    coverage_table(ix, cells, heuristics, out)
    ratio_tables(ix, cells, heuristics, out)
    cost_consistency(ix, cells, heuristics, out)
    unsolv_table(unsolv, out)

    for h in heuristics:
        make_figure(ix, cells, h,
                    os.path.join(FIGDIR, f"stageA_{h}.png"))

    text = "\n".join(out)
    print(text)
    with open(os.path.join(RESULTS, "stageA_tables.md"), "w") as fh:
        fh.write(text + "\n")
    print("\n[analysis] wrote results/stageA_tables.md")


if __name__ == "__main__":
    main()
