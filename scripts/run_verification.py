#!/usr/bin/env python3
"""Milestone 1 verification: run the h* oracle suite over every (N, C, E)
small enough to enumerate, and write a markdown report.

Usage:  python scripts/run_verification.py [--fast]
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ballsort.oracle import verify_config          # noqa: E402
from ballsort import heuristics as H               # noqa: E402

# Cross-check every incremental update against from-scratch inside the
# verification run -- design doc: assertion mode ON for tests.
H.CHECK_INCREMENTAL = True

# (4,4,1) is excluded: ~3.7e7 canonical states, beyond pure-Python full
# enumeration (measured during Milestone 1) -- itself a feasibility datum.
FULL = [
    (3, 3, 1), (3, 3, 2), (3, 3, 3),
    (3, 4, 1), (3, 4, 2), (3, 4, 3),
    (4, 3, 1), (4, 3, 2),
]
FAST = [(3, 3, 1), (3, 3, 2), (3, 4, 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--out", default="results/verification_report.md")
    args = ap.parse_args()

    configs = FAST if args.fast else FULL
    lines = ["# Milestone 1 — Oracle Verification Report", ""]

    def rep(msg):
        print(msg)
        lines.append(msg if msg.startswith(" ") or msg.startswith("=")
                     else msg)

    results = []
    for (n, c, e) in configs:
        try:
            results.append(verify_config(n, c, e, report=rep))
        except MemoryError:
            rep(f"(N={n},C={c},E={e}) skipped: too large to enumerate here")

    # Summary table
    lines.append("\n## Summary\n")
    hdr = ("| N | C | E | states | edges | goals | h*=inf % | b_eff | "
           "adm fails | cons fails | dom fails | pred fails |")
    lines.append(hdr)
    lines.append("|" + "---|" * 12)
    for r in results:
        adm = sum(v for k, v in r.items()
                  if k.startswith("adm_") and not k.endswith("_M1")
                  and "h5" in k) if False else sum(
            r[f"adm_{h}_{cm}"] for h in ("h1", "h2", "h3", "h4")
            for cm in ("M1", "M2")) + r["adm_h5_M2"]
        cons = sum(r[f"cons_{h}_M1"] for h in ("h1", "h2", "h3", "h4")) \
            + r["cons_h5_M2"]
        lines.append(
            f"| {r['N']} | {r['C']} | {r['E']} | {r['canonical_states']} "
            f"| {r['edges']} | {r['goal_states']} "
            f"| {100*r['frac_hstar_inf']:.1f} | {r['b_eff_L1']:.2f} "
            f"| {adm} | {cons} | {r['dominance_violations']} "
            f"| {r['predecessor_mismatches']} |")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nreport written to {args.out}")


if __name__ == "__main__":
    main()
