# Milestone 1 — Oracle Verification Report

Full-space enumeration, exact h\* via multi-source backward BFS/Dijkstra,
and the seven-part verification suite. All checks ran with incremental-
heuristic assertion mode ON (every incremental update cross-checked against
a from-scratch evaluation).

**Totals: 618,861 canonical states, 3,335,331 edges, 0 admissibility violations, 0 consistency violations, 0 dominance violations, 0 predecessor mismatches.**

| N | C | E | states | edges | goal states | h\*=∞ % | b_eff(L1) | h1 h/h\* | h2 | h3 | h4 | h5 (M2) | h4>h3 strict | P1 subsumed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 3 | 1 | 1,500 | 3,036 | 1 | 28.4 | 1.78 | 0.760 | 0.841 | 0.927 | 0.977 | 0.705 | 44.4% | 100% |
| 3 | 3 | 2 | 2,424 | 12,528 | 1 | 0.0 | 3.53 | 0.667 | 0.859 | 0.921 | 0.982 | 0.660 | 34.7% | 100% |
| 3 | 3 | 3 | 2,742 | 25,092 | 1 | 0.0 | 4.31 | 0.636 | 0.871 | 0.929 | 0.984 | 0.633 | 31.5% | 100% |
| 3 | 4 | 1 | 52,161 | 112,482 | 1 | 34.7 | 2.04 | 0.819 | 0.763 | 0.946 | 0.986 | 0.669 | 46.0% | 100% |
| 3 | 4 | 2 | 105,342 | 554,604 | 1 | 0.0 | 4.33 | 0.737 | 0.800 | 0.940 | 0.986 | 0.715 | 34.8% | 100% |
| 3 | 4 | 3 | 133,968 | 1,240,389 | 1 | 0.0 | 5.72 | 0.701 | 0.821 | 0.949 | 0.988 | 0.693 | 30.1% | 100% |
| 4 | 3 | 1 | 113,616 | 235,728 | 1 | 48.3 | 1.92 | 0.806 | 0.854 | 0.925 | 0.982 | 0.707 | 63.8% | 100% |
| 4 | 3 | 2 | 207,108 | 1,151,472 | 1 | 0.1 | 4.28 | 0.721 | 0.859 | 0.911 | 0.983 | 0.705 | 53.0% | 100% |

## Verdicts
- **h1, h2, h3, h4: admissible and consistent under M1 and M2** — zero violations, exhaustively.
- **h5: admissible and consistent under M2; inadmissible under M1** as designed (violations found, as expected).
- **Dominance h4 ≥ h3 ≥ max(h1,h2): holds on every state**; h4 > h3 strictly on 30–64% of states, h3 > max(h1,h2) on 25–68% — the chain is strict often enough to matter.
- **Predecessor generation exactly inverts the forward edge relation** (as a set of (parent, k)); quotient edge *multiplicity* is direction-dependent when a parent has identical tubes — documented in oracle.py.
- **L1 subsumes pruning rule P1 completely** (every mono-tube→empty move is an L1 self-loop, 100% in every config) and **P3 up to one representative** (~50% of to-empty moves with ≥2 empties are duplicates of a sibling: exactly one survivor per empty-tube class).
- **Dead-state structure (preview of RQ4):** the fraction of states that cannot reach any goal is 28–48% at E=1 and ~0% at E≥2 — a sharp threshold already visible at the state level.
- **A single canonical goal state exists under L1 alone** (tube sorting orders the mono tubes by colour); the design doc expected this to require L3.
- **Effective branching factor is 1.8–5.7**, below the design doc's 8–15 estimate — good news for feasibility.
