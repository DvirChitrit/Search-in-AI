# Milestone 2 — Calibration Pilot Report and THE DECISION

All numbers below are **measured on this machine**, not projected, unless a row
is explicitly marked *extrapolated*. Raw data: `results/pilot.csv` (500 runs:
208 pilot + 240 probe A/A2/B + 6 probe C/D partial + 52 L0 companion, minus
overlap), reproducible via the grid JSONs in `results/` and the resume-safe
runner (`python3 -m ballsort.runner <grid.json> results/pilot.csv`).

## 0. Environment (design doc 5.3 control #7)

* CPython 3.12.3, Linux x86-64, **1 CPU core**, single-threaded per run.
* **PyPy is not available in this environment.** The hot path is stdlib-only
  and PyPy-clean by construction (verified: no C extensions imported), so the
  usual 4–10× JIT speedup on pointer-chasing pure-Python search code remains
  available headroom on a machine that has PyPy — but **nothing below assumes
  it**; every budget is CPython-measured.
* Caps used throughout: 60 s wall, 5×10⁶ generated, 3 GB RSS (child-enforced
  via setrlimit + SIGALRM; never triggered — see §2).

## 1. Measured throughput

Sustained rates over all runs longer than 0.5 s wall (the long h0 probe runs;
short runs are excluded because per-run setup would flatter the numbers):

| metric | value |
|---|---|
| expansions/s (L1, sustained) | **≈ 30,000** |
| generated/s (L1, sustained) | **≈ 113,000** |
| generated/s (short-burst ceiling, L0≈L1) | 140–160k |
| canonicalization share of wall @ L1 | **9–11 %** |
| canonicalization share of wall @ L0 | 3–4 % |
| peak RSS, largest run | 40 MB (cap 3 GB — never approached) |

The design doc (7.1) estimated 70–125k generated/s on CPython; measurement
lands at the top of that band. The L1-vs-L0 per-node cost difference is real
(sorting T tube-bytes per key) but small; at h4-guided searches L0's *node
inflation* is also small (median expanded 12→12, 17→22 at N=4/5, C=4, E=2)
because the search is too narrow to generate many permutation twins — the
RQ1 contrast must therefore be measured with weaker heuristics and/or larger
N in Stage A, exactly as the doc anticipated.

**Canon-time measurement overhead.** Each `Domain.key()` call is wrapped in a
`perf_counter()` pair (design: exact accounting, no profiler). Measured A/B
(timing on/off, same workload): the difference is inside run-to-run noise
(±10 % on sub-second workloads); an upper bound from timer-call cost is
≈ 10–15 % *of the canon slice*, i.e. ≈ 1–1.5 % of total wall at L1. Verdict:
**keep exact timing on for all experiments** — no sampling machinery needed.

## 2. Pilot results (A*-EARLY, h4, L1, M1; 13 seeds/cell; 60 s / 5×10⁶ caps)

208 attempted instances, **152 solved, 56 unsolvable, 0 undecided, 0
timeouts, 0 memory kills, 0 errors**. Every solution replay-validated in the
child. Coverage on solvable instances: **100 % in every cell**.

| cell | unsolv. % | med expanded | max expanded | med C* | max wall |
|---|---|---|---|---|---|
| N3 C3 E1 | 0 % | 6 | 8 | 5 | 0.2 ms |
| N3 C3 E2 | 0 % | 6 | 8 | 5 | 0.3 ms |
| N3 C4 E1 | 31 % | 8 | 15 | 8 | 0.3 ms |
| N3 C4 E2 | 0 % | 8 | 15 | 8 | 0.5 ms |
| N4 C3 E1 | 31 % | 9 | 13 | 8 | 0.2 ms |
| N4 C3 E2 | 0 % | 9 | 10 | 8 | 0.4 ms |
| N4 C4 E1 | 62 % | 11 | 21 | 11 | 0.4 ms |
| N4 C4 E2 | 0 % | 12 | 21 | 11 | 1.0 ms |
| N5 C3 E1 | 62 % | 11 | 19 | 11 | 0.4 ms |
| N5 C3 E2 | 0 % | 11 | 18 | 11 | 0.7 ms |
| N5 C4 E1 | 85 % | 18 | 21 | 14 | 0.5 ms |
| N5 C4 E2 | 0 % | 17 | 81 | 14 | 2.6 ms |
| N6 C3 E1 | 69 % | 16 | 24 | 13 | 0.6 ms |
| N6 C3 E2 | 0 % | 13 | 17 | 13 | 1.0 ms |
| N6 C4 E1 | 92 % | 37 | 37 | 21 | 0.7 ms |
| N6 C4 E2 | 0 % | 19 | 44 | 18 | 1.8 ms |

Two headline facts:

1. **A*+h4+L1 never breaks a sweat inside the design grid.** Median expanded
   ≈ C* + a handful: h4's informedness (h/h* ≈ 0.98 in the M1 oracle sweep)
   evidently persists at sizes the oracle cannot reach.
2. **Uniform-random E=1 instances become almost surely unsolvable as N
   grows** (0 % → 92 % unsolvable across the pilot; probes below reach
   8/8 unsolvable at N ≥ 7). This is simultaneously an RQ4 result and a
   *sampling problem* for every later stage's E=1 arm. E=2 was solvable in
   **all 260** sampled instances across the pilot and probes.

## 3. Ceiling probes (same protocol; 8 seeds/cell for h4, 4–5 for h0/h3)

h4 arm — includes cells **beyond the design doc's optimal-search grid**
(the doc's Stage B tops out at N=7, C=5; N ∈ {8,9,10} rows are measurements,
not extrapolations, but they are outside the planned grid and are flagged):

| cell (E=2) | med expanded | max expanded | med C* | max wall |
|---|---|---|---|---|
| h4 N7 C5 | 70 | 185 | 28 | 8 ms |
| h4 N8 C4 † | 30 | 71 | 24 | 3 ms |
| h4 N8 C5 † | 48 | 136 | 31 | 6 ms |
| h4 N9 C5 † | 50 | 1,146 | 37 | 46 ms |
| h4 N10 C4 † | 108 | 5,090 | 30 | 0.22 s |
| h4 N10 C5 † | 86 | 2,241 | 41 | 90 ms |

† beyond the design-doc grid. **All E=1 probe cells at N ≥ 7: 100 % of
sampled instances unsolvable** (7–8 of 8 already at N=7).

Weak-heuristic arm (bounds Stage B, whose cost is set by its *worst*
heuristic, not h4):

| cell (E=2) | heuristic | med expanded | max expanded | max wall |
|---|---|---|---|---|
| N7 C4 | h0 | 4,990 | 5,945 | 0.19 s |
| N8 C4 | h0 | 8,384 | 10,052 | 0.32 s |
| N10 C4 | h0 | 12,016 | 16,117 | 0.55 s |
| N6 C5 | h0 | 7,422 | 9,319 | 0.27 s |
| N7 C5 | h0 | 20,106 | 34,866 | **1.25 s** |
| N7 C5 | h3 | 3,692 | 28,342 | 1.03 s |

**Not a single timeout, node-cap hit, or memory event occurred in any of the
500 runs.** The hardest run in the whole calibration (h0, N=7, C=5) used
1.25 s of the 60 s budget and 35k of the 5M node budget.

## 4. THE DECISION

**(a) Revised parameter ceiling for optimal search.** The design doc's fear
that Python A* would struggle inside N ≤ 7 is refuted by measurement. The new
measured feasibility statement: *optimal A\* with h3/h4 at L1 under M1 is
sub-second per instance up to at least N=10, C=5, E=2; with h0 (blind UCS)
it is ≤ ~1.5 s up to N=7, C=5 and ≤ ~0.6 s up to N=10, C=4.* The binding
constraints are no longer search cost but: (i) **solvable-instance
generation at E=1** for N ≥ 7 (rejection sampling fails; needs targeted
generation, e.g. backward random walks from goals — proposed M3 backlog
item), and (ii) the still-unmeasured algorithms of Milestone 5 (IDA*
without duplicate detection on a graph this transposition-rich is exactly
where blowups live — that is RQ3's point, and the caps exist for it).

**(b) Revised stage grids with measured CPU-hour budgets** (1 core, CPython,
sequential; the runner supports `--procs` and resume, and PyPy is upside):

* **Stage A (RQ1, canon ablation)** — keep the doc's grid (L ∈ {L0,L1,L2,L3},
  N ∈ {3..6}, C=4, E ∈ {1,2,3}, 50 instances, h4) **and add an h1 arm at
  L0/L1** (2,400 extra runs): the pilot shows h4 is too informed to expose
  L0's node inflation, so the ablation needs a weaker heuristic to measure
  what canonicalization actually buys. Budget: measured ms-scale runs ⇒
  **≈ 10–25 CPU-minutes** including solvability screening, even with the h1
  arm. (L2/L3 are Milestone 3; the grid slot is reserved.)
* **Stage B (RQ2, heuristics)** — keep the doc's grid (h0..h4, N ∈ {3..7},
  C ∈ {3,4,5}, E ∈ {1,2}, 50 instances = 7,500 runs), with the E=1 arm
  restricted to N ≤ 6 (see (c)). Cost is h0-dominated; summing measured
  per-cell medians: **≈ 20–40 CPU-minutes**. Optional extension now known to
  be affordable: an **N=8 annex** for all five heuristics at C ∈ {4,5}, E=2
  (+500 runs, ≈ +15 min).
* **Stage C (RQ3, algorithms)** — grid as designed (14 configs, N ∈ {3..7},
  C=4, E ∈ {1,2}, 50 instances = 7,000 runs), E=1 arm at N ≤ 6. This is the
  one stage whose cost cannot be measured yet (the algorithms do not exist
  until M5). Bounding with the 60 s cap: cost ≈ 7,000 × (0.1 s + t·60 s)
  where t = timeout fraction ⇒ t=5 % → **≈ 6 CPU-hours**; t=20 % →
  **≈ 24 CPU-hours**. Both fit one overnight run; if the first pass shows
  t > 20 %, cut to N ≤ 6 first (doc's own fallback, −60 % cost) and treat
  the timeouts as the coverage result they are.
* **Stage D (RQ4, solvability)** — as designed (96,000 satisficing checks).
  Measured check cost at pilot sizes: ≪ 0.1 s ⇒ **≈ 1–3 CPU-hours**
  (conservative for the large-N tail where the DFS cap may bite; `None`
  verdicts are recorded, not retried).
* **Stage E (RQ5, cost model / goal test)** — as designed (800 runs),
  **measured minutes**; and it is now guaranteed non-vacuous: the M2 gate
  already measured EARLY suboptimal on **71.5 %** of state×heuristic pairs
  (2,060/2,880; max gap 2) where LATE is exactly optimal — see §5.

Grand total with the worst Stage C assumption: **≈ 30 CPU-hours ≈ one day on
this single core**, with 4–10× PyPy headroom untouched. The design doc's
"feasible, but only just" is revised to **comfortably feasible**.

**(c) E=1 sampling policy (binding for A/B/C).** Measured solvable rates
under uniform sampling: 69 % (N3 C4) → 38 % (N4 C4) → 15 % (N5 C4) → 8 %
(N6 C4) → ~0 % (N ≥ 7). Policy: for N ≤ 6, oversample seeds by rejection
until 50 solvable instances per cell (screening cost is negligible and every
screened seed is a free Stage-D data point — the runner already writes
`unsolvable_instance` rows); for N ≥ 7, E=1 optimal-search cells are
**dropped from A/B/C** and the E=1 story at large N is told by Stage D plus
the targeted-generation backlog item.

## 5. Finding of record: EARLY goal test is suboptimal under M2

Caught by the oracle gate on its first full run (state, both solutions, and
the theory are pinned in `tests/test_astar.py::test_early_late_m2_regression`):
with cost = balls-moved, returning at *generation* can commit to a goal
reached by an expensive k-ball pour while a cheaper path waits in OPEN.
A*-LATE (goal test at expansion — design doc 5.3 control #2, added to
`astar.py` as a flag, not a new algorithm) is exactly optimal in all 2,880
M2 gate runs; A*-EARLY overshoots on 71.5 % of them, gap ≤ 2 = C−1 in every
observed case. Under M1, EARLY was **exactly optimal in all 8,000 gate
runs** — the theoretical +1 tie-breaking risk with zero-h plateaus (h0–h3)
never materialized. Consequence for the gates: the M2 optimality assertion
is placed on LATE (implementation correctness), and EARLY's M2 gap is
recorded as data — it *is* the RQ5 experiment, and Stage E will now measure
it on real instances rather than oracle states.

## 6. Deviations and open flags (for the oral defense)

1. `solve(domain, s0, heuristic, limits)` — the design doc 6.1 protocol has
   no `s0` because it assumed `Domain.initial()`; M1's Domain is
   instance-free (`generate_instance(seed)`), so `s0` is an explicit
   argument. One-line doc amendment, flagged.
2. The M2 oracle-gate assertion moved from EARLY to LATE, per §5.
3. Probe cells used 8 (h4) / 4–5 (h0/h3) seeds, not the pilot's 13 — they
   size budgets, not confidence intervals.
4. N ∈ {8,9,10} rows are measurements outside the design-doc grid,
   marked †; nothing in the stage plan depends on them.
5. Rates in §1 are one machine, one core; treat as this-hardware constants.
