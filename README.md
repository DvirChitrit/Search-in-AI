# Ball Sort Puzzle — Heuristic Search Study

Final project for "Search Methods in Artificial Intelligence" (237-2-5513, BGU).
Dvir & Nevo. Design: see `ballsort_design_doc.md` in the project knowledge base.

## Layout
- `ballsort/domain.py`     — state encoding, pour moves, goal test (G_strict),
                             L0/L1 canonicalization, generation, solvability,
                             predecessors, validator
- `ballsort/heuristics.py` — h0..h5 with O(C)-incremental updates
- `ballsort/oracle.py`     — full-space enumeration + exact h* + verification
- `ballsort/algorithms/`   — (Milestone 2+) search algorithms
- `ballsort/runner.py`     — (Milestone 2) experiment runner, CSV, resume
- `scripts/run_verification.py` — Milestone 1 verification suite
- `tests/`                 — pytest unit tests

## Run
    python -m pytest tests/ -q
    python scripts/run_verification.py          # full oracle sweep
    python scripts/run_verification.py --fast   # quick smoke run

Hot-path code is stdlib-only and runs under PyPy.
