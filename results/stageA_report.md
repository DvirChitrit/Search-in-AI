# Milestone 3b — Stage A: the full RQ1 canonicalization ablation

Every number and figure below regenerates from committed artifacts:

```
python scripts/stageA_seeds.py          # results/stageA_seeds.json (deterministic)
python scripts/make_stageA_grids.py     # grids/stageA_*.json
python -m ballsort.runner grids/stageA_N{3..6}E{1..3}.json results/stageA.csv --procs 4
python -m ballsort.runner grids/stageA_unsolv_N{4,5}E1.json results/stageA_unsolv.csv --procs 4
python analysis/stageA_analysis.py      # figures + every table (results/stageA_tables.md)
```

Environment: CPython 3.12, Linux sandbox, single core, `--procs 4–8`
(time-sliced; see the caveat in §6). Absolute times rescale on the
target Windows machine; every conclusion is stated in within-cell
ratios, which the M3a pilot showed transfer. On Windows use
`--procs 2` (the hard rlimit/SIGALRM backstops are Unix-only; the
cooperative in-search caps fire first — verified again here: all 10
timeouts in this grid were cooperative `"wall"` rows, no hard-cap rows).

## 1. What ran

| workload | grids | runs | outcome |
|---|---|---:|---|
| Solvable core (h4) + h1 arm | `grids/stageA_N{3..6}E{1..3}.json` | 4,800 | 4,790 solved, 10 wall-timeouts |
| Unsolvable exhaustion (pred. iv) | `grids/stageA_unsolv_N{4,5}E1.json` | 400 | 400 exhausted, 0 caps hit |

Grid: N ∈ {3,4,5,6}, C = 4, E ∈ {1,2,3}, 50 instances/cell,
canon ∈ {L0,L1,L2,L3}, h ∈ {h1,h4}, A\*-EARLY, M1, runner-default
tie-break/dup-policy, caps 60 s / 5e6 generated / 3072 MB. Total search
wall ≈ 53 min, 9.29 M expansions in the solvable grid; the exhaustion
grid took 1.5 s of search in total (that is a finding — §4, iv).

**Seeds (mechanism (b) of the session prompt, as agreed):**
`scripts/stageA_seeds.py` enumerated seeds 0,1,2,… per cell with
`Domain.solvable` and committed the first 50 solvable per cell
(`results/stageA_seeds.json`), so every cell has exactly 50 solvable
instances; `solvable_filter` stays on in the solvable grids so
`instance_solvable=True` is recorded per row. Observed unsolvable
fractions on the way at E=1: 20.6 % (N=3), 42.5 % (N=4), 73.1 % (N=5),
84.6 % (N=6); 0 % at E∈{2,3} in the first 50 seeds. M2's pilot window
measured 62/76/91 % at N=4/5/6 on a *different, smaller seed window* —
both are committed; the discrepancy is sampling window, not a
contradiction, and Stage B can measure the fraction properly if RQ4
needs it.

**Coverage** (full table in `results/stageA_tables.md`): 50/50 at every
level in every cell except **L0, h1, N=6, E=3: 40/50** — ten 60 s wall
timeouts, exactly the predicted L0 blow-up at the largest cell, reported
as a result per the design doc §5.1 convention. Paired ratios below use
solved-everywhere instances only (n=40 in that one cell, n=50
elsewhere), with coverage reported separately so the timeouts are not
hidden inside an average.

**Soundness regression (free spot-check):** solution cost per
(cell, seed) is identical across all canon levels on all **1,200**
checked groups — zero mismatches. The M3a soundness verdict survives
contact with the full grid.

## 2. The RQ1 verdict — space vs. search, quantified

RQ1 splits into a state-space half (M3a's exact ladder,
`results/canon_ladder.csv`, reused not recomputed) and a search half
(this grid). The two halves **diverge**, and that divergence is the
headline result:

| symmetry | state-space factor (exact, enumerable cells) | realized search factor (this grid) |
|---|---|---|
| Colour (L1→L3) | 5.96× at N=3 C=4; 23.5× at N=4 C=3 (≈ the N! bound) | **1.00–1.14× in nodes; loses 3–20× in wall-clock** |
| Tube (L0→L1) | 22–453× on enumerable cells | **1.0–7.7× in nodes (h1, E-driven); ≈1.0–1.5× under h4** |

Colour symmetry is nearly fully present in the reachable space (M3a:
almost no state has a non-trivial colour stabilizer) yet guided A\*
almost never generates two colour-equivalent states in the same run:
the geomean L1/L3 node ratio never exceeds 1.14 anywhere in the grid,
while L2/L3's 30–100× per-key cost makes L1→L3 a wall-clock **loss of
3–20×** (t L1/L3 = 0.05–0.31 across all 24 (N,E,h) arms). Tube
symmetry is the mirror image: a symmetry A\* actually collides with
(duplicate siblings), so its node reduction is real — but it is driven
by E (and rises with N), reaching 7.7× at E=3 under h1, and is nearly
erased (1.0–1.5×) by a strong heuristic. **A strong heuristic is itself
a symmetry killer:** under h4 every canonicalization node effect in the
grid collapses to ≈1.

## 3. THE figure

`results/figures/stageA_h1.png` and `stageA_h4.png` (script-generated
by `analysis/stageA_analysis.py`): geomean expanded (top row) and
geomean wall time (bottom row) vs. N, one column per E, one line per
canon level. The visual story: in nodes, L1/L2/L3 collapse onto a
single line while L0 inflates at E≥2 (h1) or barely separates (h4); in
wall time, L1 is lowest everywhere at E≥2 and L2/L3 sit a constant
factor above it with no crossover through N=6.

## 4. Pilot predictions (canon_report.md §4) — confirmed or refuted

**(i) L0→L1 is E!-driven, visible only under h1 — CONFIRMED, upper
range delivered.** Geomean expanded L0/L1 with h1: 1.00–1.03 at E=1,
1.60–2.39 at E=2, **3.98–7.72 at E=3** (rising with N within each E:
multiplicity of identical tubes grows with N). Wall-clock follows nodes
at E≥2 (t L0/L1 = 1.76–7.94). Under h4 the effect is 1.00–1.49 —
the h1 arm was the only way to see this, as the calibration report
argued. One honest refinement: at E=1 (nothing to win, E!=1) L1's canon
overhead makes it *slightly lose* wall-clock in some cells (t L0/L1
down to 0.69 at N=5 E=1 h1), so the pilot's "never loses at E=1"
becomes "≈break-even at E=1, up to ~30 % loss in the worst cell."

**(ii) L1→L3 loses wall-clock, monotone in N, no crossover —
CONFIRMED.** t L1/L3 = 0.05–0.31 over all 24 arms; the loss widens
with N (h4 at E=2: 0.17 → 0.09 → 0.07 → 0.06 for N=3..6) and is worst
where searches are shortest (h4), exactly the pilot's per-node-cost
mechanism. No crossover anywhere in the grid.

**(iii) L2 nodes == L3 nodes — CONFIRMED as a geomean, refined in the
exact sense.** Geomean exp L2/L3 = 1.00 in every arm. But at scale the
pilot's *exact* identity (240/240) breaks: **58 of 1,200 paired runs
differ** — all under h1 at E≥2, N≥4, always L3 ≤ L2, largest gap
0.35 % (29,540 vs 29,506). So L3's completeness does fire on reachable
search states, but it buys < 0.4 % of nodes on < 5 % of runs while
costing 12–52 % extra wall time (t L2/L3 = 0.48–1.18, usually < 1).
L2 captures ≥ 99.6 % of the realized colour-symmetry search benefit —
which itself is ≤ 14 % of nodes. This is the pilot's story, now with
the residual measured instead of assumed zero.

**(iv) The unsolvable E=1 cell gives L2/L3 a node win — REFUTED, with
the mechanism.** Median exhaustion at N=4/5, C=4, E=1: **19–24
expansions, max 122**, finishing in ≈0.5–3 ms at every level; total
search time for all 400 runs was 1.5 s. Uniformly sampled unsolvable
E=1 instances are unsolvable because they **lock almost immediately**
(nearly no legal pours from the start region), not because a large
space must be swept. A\* therefore exhausts a tiny reachable component,
the colour quotient never comes into play, and no level separates from
any other. The prediction's premise — "proving unsolvability exhausts
the reachable *quotient*" — is empirically false for this instance
distribution. (A workload where exhaustion is genuinely large — e.g.
near-solvable handcrafted instances or full-space sweeps — would be a
different experiment; noted for the final report's future-work section,
not pursued here.)

## 5. The recommendation Stage B/C/D/E inherit

**Pin canon_level = L1 for all subsequent stages.** The full grid
confirms the pilot with no surprises in direction: L1 wins up to 7.9×
wall-clock over L0 where symmetry matters (E≥2, weak h), costs at most
~30 % in the one regime with nothing to win (E=1), and beats L2/L3 by
3–20× wall-clock everywhere with a node sacrifice of at most 14 % (and
≤ 1 % vs L2's realized benefit). No crossover exists anywhere in
N ≤ 6, and the per-node-cost mechanism says it widens with N. L2/L3
remain what M3a called them: a state-space/theory result (the ~N!
quotient is real and exactly measured) that guided search does not pay
for. RQ1 is answered; later stages cite this file and
`stageA_tables.md` rather than re-running the ablation.

## 6. Caveats, honestly

1. **Wall-time contention.** The sandbox exposes one core and the run
   used `--procs 4–8`, so per-run wall times include multiprocessing
   time-slicing. Node counts (the primary RQ1 metric) are exact and
   deterministic. Wall-time *ratios* are within-cell (all levels of a
   seed run interleaved under the same procs setting) and reproduce the
   M3a pilot's *sequential* measurements — e.g. t L1/L3 at N=4 E=2 h1:
   0.19 here vs 0.23 pilot; t L2/L3: 0.90 vs 0.88 — so the wall-clock
   conclusions stand. Absolute times in the CSV should not be quoted as
   machine throughput; M2's sequential throughput numbers remain the
   reference.
2. **Survivor bias in the one incomplete cell.** N=6 E=3 h1 L0 medians
   are over the 40 solved runs; the 10 timeouts mean L0's true cost
   there is *understated*. Coverage is reported separately (per the
   session mandate) precisely so this cannot hide.
3. **Run log.** The run was executed in resume-safe chunks (sandbox
   execution-time limits kill long foreground processes; the runner's
   crash-safe append + run_key resume handled it exactly as designed —
   an incidental live test of the M2 contract). `results/stageA_run.log`
   holds the first chunk; the final chunk's real tail:
   `[runner] 64/64 rows (89s)` / `[runner] wrote 64 rows ->
   results/stageA.csv`, and the two exhaustion grids each ended
   `[runner] wrote 200 rows -> results/stageA_unsolv.csv`.

## 7. Conflicts / deliberate divergences (flagged per the rules)

1. **h1 arm at all four levels** (design doc §5.1 says h1 at L0/L1
   only; the calibration report added the arm without fixing its
   scope). Chosen deliberately and confirmed with Dvir: prediction
   (iii) is only checkable under a weak heuristic if h1 runs at L2/L3,
   and the cost was ~minutes. The refinement in §4(iii) — the 58
   non-identical runs — was only observable because of this choice.
2. **The exhaustion grids run with `solvable_filter: false`.** The
   runner (correctly, per its M2 contract) short-circuits unsolvable
   seeds into `unsolvable_instance` rows *without searching* when the
   filter is on — fatal for a workload whose whole point is running A\*
   to exhaustion. First execution of that grid hit exactly this; the
   committed generator (`scripts/make_stageA_grids.py`) now sets the
   flag off for the unsolvable grids and documents why. No runner
   change was needed or made; the seeds' unsolvability is documented in
   `stageA_seeds.json` and re-proven by every row ending
   `solved=False` with no cap triggered.
3. No other conflicts with the design doc found.

## 8. Handoff to M4+

- **Pin L1** (§5). Stage B/C/D/E grids copy the structure of
  `grids/stageA_*.json` with `canon_level: "L1"` fixed.
- **The analysis pattern is the template:** committed CSVs →
  `analysis/<stage>_analysis.py` → figures + a tables.md, nothing
  chat-only. `analysis/stageA_analysis.py` is the reference
  implementation (paired solved-everywhere ratios, separate coverage,
  geomean/median split).
- matplotlib is now a declared analysis-layer dependency
  (`requirements.txt`); the hot path stays stdlib-only.
- Committed for reproduction: 14 grid JSONs, `stageA_seeds.json`,
  `stageA.csv` (1.3 MB), `stageA_unsolv.csv`, `stageA_tables.md`, both
  figures, this report.
