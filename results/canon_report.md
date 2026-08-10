# Milestone 3a — L2/L3 canonicalization: soundness verdict and go/no-go for Stage A

All numbers below are real and regenerate from committed artifacts:

```
python3 scripts/run_canon_gates.py --sample 100     # gates + results/canon_ladder.csv
python3 scripts/measure_canon.py  --seeds 5         # results/canon_pilot.csv
python3 analysis/canon_summary.py                   # every table in this file
```

Environment for the measurements in this report: CPython 3.12, single
core, Linux sandbox. Absolute times will rescale on the target Windows
machine; every conclusion below is stated in ratios, which are driven by
per-node canonicalization cost relative to search cost and transfer.

## 1. Soundness verdict — GO

**L2 and L3 are SAFE, and L3 is COMPLETE**, verified exhaustively against
the full S_T × S_N orbit relation (min-over-orbit L1 key as ground
truth, all N! colour permutations applied per state) on every
oracle-enumerable config (N=3, C∈{3,4}, E∈{1,2,3}; N=4, C=3, E∈{1,2}):

- **(a) SAFE:** zero orbit-merging keys at L2 or L3, over all 619,000
  enumerated states across the eight configs. (Safety also holds by
  construction: both levels return `L1(π(s))` for some colour
  permutation π, so equal keys force orbit equivalence — see the
  argument in `domain.py`'s module docstring. The gate checks it anyway.)
- **(b) COMPLETE:** `|distinct L3 keys| == |orbits|` on every config
  (e.g. 8,806 == 8,806 at N=4 C=3 E=2).
- **(c) MONOTONE LADDER:** L0 ≥ L1 ≥ L2 ≥ L3 == orbits everywhere
  (table below).
- **(d)/(e) INVARIANCE:** `h(s) == h(canonical_L3(s))` for h0..h4 and
  `h*(s) == h*(canonical_L3(s))` under M1, exhaustive over all states —
  zero violations. (The §2.8 one-line proof that h is label- and
  position-free is now also an empirical fact.)
- **(f) OPTIMALITY + PATHS:** 8,000 A\*-EARLY runs (100 finite-h\*
  starts × h0..h4 × L2/L3 × 8 configs) all returned cost == h\*
  **exactly** under M1, zero reopenings, and every move list replayed
  from the **concrete** s0 through `Domain.validate_solution` — the
  §2.8 canonical-keys/concrete-states rule survives L2/L3 intact.

Additional cross-checks from the pilot (Section 3): on all 240 real A\*
runs, solution cost per instance is identical across L0/L1/L2/L3, and
reopenings are 0 everywhere.

Implementation note (flagged per the prompt's "say so" rule, not a
substitution): the doc's §2.9 signature is implemented faithfully —
per-colour multiset of (run length, run-bottom height, tube ball count,
at-bottom flag), refined by neighbours' cell ids to a fixed point. The
only interpretive addition is *where safety comes from*: it does not
depend on the signature at all (any per-state colour permutation
composed with L1 is safe); the signature's equivariance is what makes L3
complete. This is written up as the oral-defense argument in the
docstrings of `_refine_colors` and `_l3_key_state`.

## 2. State-space half of RQ1 — the ladder (exact, exhaustive)

| N | C | E | L0 (raw) | L1 | L2 | L3 = orbits | L0/L1 | L1/L3 |
|---|---|---|---------:|---:|---:|---:|---:|---:|
| 3 | 3 | 1 | 33,600 | 1,500 | 261 | 257 | 22.4× | 5.84× |
| 3 | 3 | 2 | 226,800 | 2,424 | 423 | 419 | 93.6× | 5.79× |
| 3 | 3 | 3 | 974,400 | 2,742 | 479 | 474 | 355.4× | 5.78× |
| 3 | 4 | 1 | 1,212,750 | 52,161 | 8,772 | 8,759 | 23.3× | 5.96× |
| 3 | 4 | 2 | 11,088,000 | 105,342 | 17,661 | 17,648 | 105.3× | 5.97× |
| 3 | 4 | 3 | 60,672,150 | 133,968 | 22,490 | 22,471 | 452.9× | 5.96× |
| 4 | 3 | 1 | 12,936,000 | 113,616 | 4,968 | 4,818 | 113.9× | 23.58× |
| 4 | 3 | 2 | 124,185,600 | 207,108 | 9,020 | 8,806 | 599.6× | 23.52× |

(L0 is the exact raw count — per-state T!/∏(mult!) over identical
tubes, i.e. the stabilizer-corrected number, not the /T! approximation.)

Two facts for the report:

1. **Colour symmetry is nearly fully realized in the state space:**
   L1/L3 ≈ 5.8–6.0 at N=3 (bound N! = 6) and ≈ 23.5 at N=4 (bound 24).
   Almost no reachable-space state has a non-trivial colour stabilizer.
2. **L2 is nearly complete:** the refinement alone gets within 0.1–1.6%
   of the orbit count at N=3 and within ~3.1/2.4% at N=4 (4,968 vs
   4,818; 9,020 vs 8,806). The residual is real (L2 is measurably
   incomplete) but small.

## 3. Search half of RQ1 — cost and benefit on real A\* runs

Pilot: N∈{4,5,6}, C=4, E∈{1,2}, 5 solvable instances per cell (seed
oversampling at E=1: 62/76/91% of uniform seeds unsolvable at N=4/5/6 —
consistent with M2's finding), h∈{h1, h4}, all four levels, A\*-EARLY,
M1, caps 60s/5e6/3072MB. **Coverage: 240/240 solved within caps; no
timeouts at any level.** All searches at these sizes finish in
milliseconds to ~0.5 s, so wall-clock ratios here are dominated by
per-node cost — exactly the quantity that transfers to Stage A.

**Per-node canonicalization cost** (µs/`key()` call, mean; share of
wall time in parentheses, h1 rows):

| N | E | L0 | L1 | L2 | L3 |
|---|---|---:|---:|---:|---:|
| 4 | 1 | 0.4 (3%) | 0.7 (7%) | 23.2 (66%) | 27.4 (69%) |
| 4 | 2 | 0.6 (7%) | 0.7 (10%) | 22.2 (73%) | 26.1 (75%) |
| 5 | 1 | 0.4 (3%) | 0.7 (7%) | 26.8 (69%) | 32.7 (72%) |
| 5 | 2 | 0.4 (5%) | 0.8 (10%) | 28.1 (74%) | 32.3 (77%) |
| 6 | 1 | 0.4 (3%) | 0.9 (8%) | 32.3 (70%) | 55.7 (79%) |
| 6 | 2 | 0.5 (5%) | 0.9 (10%) | 31.6 (75%) | 41.4 (80%) |

L1's ~7–10% canon share reproduces M2's ~9–11% measurement. **L2/L3
multiply per-node key cost by ~30–100× over L1** and immediately
dominate wall time (65–89%). L3's premium over L2 grows with N (18% at
N=4 → 30–140% at N=6, worst with h4 whose short searches hit
proportionally more refinement-heavy states).

**Node-count reduction and wall-clock, paired geomean ratios** (>1 =
left level costs more; t = wall time):

| N | E | h | exp L0/L1 | gen L0/L1 | dup L0/L1 | t L0/L1 | exp L1/L3 | t L1/t L3 | exp L2/L3 | t L2/t L3 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 1 | h1 | 1.00 | 1.00 | 1.00 | 0.98 | 1.00 | 0.29 | 1.00 | 0.89 |
| 4 | 2 | h1 | **2.01** | 2.00 | 1.63 | **2.08** | 1.07 | 0.23 | 1.00 | 0.88 |
| 5 | 1 | h1 | 1.01 | 1.01 | 0.96 | 1.07 | 1.01 | 0.23 | 1.00 | 0.85 |
| 5 | 2 | h1 | **2.57** | 2.54 | 2.00 | **2.55** | 1.05 | 0.20 | 1.00 | 0.91 |
| 6 | 1 | h1 | 1.00 | 1.00 | 0.85 | 0.99 | 1.01 | 0.18 | 1.00 | 0.67 |
| 6 | 2 | h1 | **2.45** | 2.42 | 2.09 | **2.51** | 1.05 | 0.18 | 1.00 | 0.81 |
| 4 | 2 | h4 | 1.05 | 1.05 | 0.12 | 1.23 | 1.00 | 0.21 | 1.00 | 0.89 |
| 5 | 2 | h4 | 1.32 | 1.33 | 0.35 | 1.43 | 1.00 | 0.17 | 1.00 | 0.74 |
| 6 | 2 | h4 | 1.07 | 1.08 | 0.13 | 1.20 | 1.00 | 0.09 | 1.00 | 0.47 |

(h4 rows at E=1 omitted for brevity — all ≈1.0; full table via
`analysis/canon_summary.py`.)

## 4. Prediction vs. H1 — the verdict

**H1, L0→L1 ("2×–50× in nodes, grows like E!·multiplicity, always wins
wall-clock; nearly invisible under h4"): direction CONFIRMED, with the
E-dependence sharper than stated.** With h1 at E=2 the reduction is
2.0–2.6× in expansions and the wall-clock win matches it (2.1–2.6×,
since L1's extra per-node cost is negligible). At **E=1 the reduction is
≈1.0×** — exactly what H1's own growth law predicts (E! = 1, and
uniform full-tube instances rarely contain identical non-empty tubes),
but it means the "always wins wall-clock" clause degrades to "never
loses" at E=1. Stage A's E=3 cells (E! = 6) are where the upper range
should appear. The h4 contrast is confirmed decisively: h4 shrinks the
L0→L1 effect to 1.0–1.3× — the calibration report's h1 arm is
vindicated as the only way to see this effect.

**H1, L1→L3 ("<2× in nodes, loses wall-clock for N≥5"): node direction
CONFIRMED, wall-clock verdict is stronger than predicted.** Node
reduction is 1.00–1.07× — not just under 2× but nearly flat. Wall-clock:
L3 **loses everywhere already at N=4**, by 3.5–5× with h1 and up to 11×
with h4 (t L1/t L3 = 0.09–0.29). There is **no crossover in sight**: the
per-node L3 cost grows with N (27→56 µs) while the node saving stays
flat, so the gap *widens* with N. The pilot's expected Stage-A picture
is a monotone L3 wall-clock loss across the whole grid — the
"boring-but-clean" outcome for the search half, which contrasts sharply
with the nearly-full N! reduction in the state-space half.

**The headline RQ1 result is exactly the predicted divergence, now
measured:** colour symmetry shrinks the *space* by ≈ N! (5.8× at N=3,
23.5× at N=4, Section 2) but shrinks the *search* by only 1.0–1.07×
(Section 3). Guided A\* almost never generates two colour-equivalent
states on the same run at these sizes; the symmetry is real but A\*
doesn't pay for it. Tube symmetry is the opposite: a smaller state-space
factor per se, but one A\* actually collides with (duplicate twins among
siblings), hence real wall-clock wins.

**L2 vs L3:** identical node counts on every one of the 240 runs
(exp L2/L3 = 1.00 in all 12 arms) — on *reachable search states*, the
residual equal-signature cells that L3's backtracking resolves
essentially never occur along the search frontier, even though they
exist in the full space (Section 2's L2 > L3 counts). L2 is 12–53%
faster per run. So L2 already captures 100% of the realized search
benefit of colour canonicalization at these sizes; L3's completeness is
a state-space/theory property, not a search win.

**Recommendation for Stage A (M3b):** run all four levels as the design
doc's grid says — RQ1 needs the full ablation and a null result is a
result; the L2==L3-nodes finding in particular is only credible if Stage
A shows it at scale. Predictions to test: (i) L0→L1 ≈ E!-driven — ~1×
at E=1, 2–3× at E=2, larger at E=3, h1 arm only; (ii) L1→L3 wall-clock
loss monotone in N, no crossover anywhere in N≤6; (iii) L2 nodes == L3
nodes throughout; (iv) unsolvable E=1 instances (space-exhaustion
workload) are the best chance for L2/L3 to show a real node win —
exhausting the quotient touches the whole reachable space, where the
colour quotient is a true N!-factor smaller.

## 5. Inheritances for M3b (next session)

- `runner.py` is REUSED UNCHANGED for Stage A (read-only this session;
  confirmed untouched). L2/L3 reach it through `canon_level` in the grid
  JSON — `Domain` now accepts all four levels.
- Stage A grid = design doc §5.1: N∈{3,4,5,6}, C=4, E∈{1,2,3}, 50
  instances/cell, A\*, M1, fixed tie-break, canon ∈ {L0,L1,L2,L3} —
  PLUS the calibration report's h1 arm at L0/L1 (this pilot suggests
  running h1 at all four levels is cheap and completes the picture).
- E=1 cells need seed oversampling to 50 solvable instances; measured
  unsolvable fractions at C=4: 62% (N=4), 76% (N=5), 91% (N=6) — so
  budget ~130/210/550 seeds/cell; `Domain.solvable` decided every pilot
  seed quickly. The runner already records unsolvable rows.
- Keep a separate unsolvable-only E=1 cell: proving unsolvability
  exhausts the reachable quotient — the most complete test of
  canonicalization payoff, and per Section 4(iv) the likeliest place L3
  beats L1 in nodes.
- M3b produces the first real figure (L0/L1/L2/L3 nodes-and-time),
  script-generated into `analysis/` from `stageA.csv`. The seed of that
  layer exists now: `analysis/canon_summary.py` reads only committed
  CSVs; extend it rather than starting over.
- Caps: nothing in the pilot came near 60s/5e6/3072MB at N≤6 with
  h1/h4; the binding budget at Stage A will be instance *count*, not
  per-run limits — with the caveat that h0-like arms are not in Stage A
  and unsolvable-cell runs exhaust the space (budget those cells by
  measurement, not assumption).

## 6. Conflicts with the design doc

None found. Two clarifications recorded (not conflicts): (1) safety of
L2/L3 holds by construction independent of the signature; the signature
buys completeness (Section 1); (2) §2.9's "L3 backtracking cost —
usually 1–2 residual colours" is confirmed: the all-singleton fast path
dominates on reachable states, which is precisely why L2 == L3 in nodes
on every pilot run.
