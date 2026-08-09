# Ball Sort Puzzle — Heuristic Search Study

Final project for "Search Methods in Artificial Intelligence" (237-2-5513, BGU).
Dvir & Nevo. Design: see `ballsort_design_doc.md` in the project knowledge base.

## Layout
- `ballsort/domain.py`     — state encoding, pour moves, goal test (G_strict),
                             L0/L1 canonicalization, generation, solvability,
                             predecessors, validator                    (M1)
- `ballsort/heuristics.py` — h0..h5 with O(C)-incremental updates       (M1)
- `ballsort/oracle.py`     — full-space enumeration + exact h*          (M1)
- `ballsort/algorithms/`
  - `base.py`              — SearchAlgorithm protocol, Stats/Limits/Result (M2)
  - `astar.py`             — A*-EARLY / A*-LATE, the reference OPEN discipline (M2)
- `ballsort/runner.py`     — grid runner: run_key resume, subprocess isolation,
                             hard caps, crash-safe CSV append           (M2)
- `scripts/run_verification.py` — Milestone 1 oracle verification suite
- `scripts/run_gates.py`   — Milestone 2 correctness gates (oracle gate etc.)
- `scripts/smoke_runner.py`— kill -9 + resume smoke test of the runner
- `tests/`                 — pytest unit tests (fast; the heavyweight checks
                             are the two scripts above)

## Run
    python3 -m pytest tests/ -q
    python3 scripts/run_verification.py --fast     # M1 gate, smoke
    python3 scripts/run_gates.py --fast            # M2 gates, smoke
    python3 scripts/run_gates.py                   # full M2 gates (~1 min)
    python3 scripts/smoke_runner.py                # runner kill/resume test
    python3 -m ballsort.runner GRID.json OUT.csv [--dry-run] [--procs K]

Grid JSON format: `{"grid": {...}, "limits": {...}, "solvable_filter": bool}` —
see `results/pilot_grid.json` for a working example.

Hot-path code is stdlib-only and runs under PyPy.

## Milestone 2 result headlines
- All correctness gates passed: 13,760 A* runs against the exact h* oracle
  (M1 EARLY == h*, M2 LATE == h*, all solutions replay-validated, 0 reopenings).
- Found + pinned as a regression test: the EARLY goal test is provably and
  empirically suboptimal under cost model M2 (gap ≤ 2 observed, on 60–84% of
  sampled state×heuristic pairs) — exactly the RQ5 phenomenon.
- Calibration pilot: see `results/calibration_report.md`.
