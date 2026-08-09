"""Milestone 2: the experiment runner (design doc 6.3-6.4).

This is the piece reused unchanged for every later stage.  One run = one
fully-specified config dict = one CSV row, appended and fsynced the
moment the child process returns, so a crash/kill at ANY point loses at
most the run in flight -- never a written row.

DESIGN
  * Grid expansion: a grid dict maps config fields to lists of values;
    the cross product (minus anything a `filter_fn` rejects) is the run
    list.  Fixed fields can be scalars.
  * run_key = SHA1 over the sorted (field, value) pairs of the config
    fields `n_colors` .. `dup_policy` (design doc 6.3) -- NOT over the
    environment fields (git commit etc.), so re-running after a commit
    does not duplicate work.
  * Resume-on-crash: on startup the CSV's run_keys are loaded and those
    runs are skipped.  Restart-after-kill therefore completes the grid
    with no duplicate rows (verified by scripts/smoke_runner.py).
  * Isolation: each run executes in a fresh child process
    (multiprocessing.Pool, maxtasksperchild=1).  The child arms
      - resource.setrlimit(RLIMIT_AS)  -> MemoryError => "memory" row
      - signal.alarm(ceil(wall)+grace) -> _WallAlarm  => "wall" row
    so OOM/timeout/crash become CSV rows, not a dead batch.  The
    in-search cooperative checks (Limits) normally fire first; the hard
    limits are the backstop.
  * Unsolvable instances: if the config says filter_solvable, the child
    first runs Domain.solvable (a cheap satisficing decision, capped);
    False  => row with timeout_reason="unsolvable_instance"
    None   => row with timeout_reason="solvable_undecided"
    and no search is charged.  The rows keep the per-cell unsolvable
    fraction in the CSV -- free RQ4 data.

Stdlib only.
"""

from __future__ import annotations

import csv
import hashlib
import math
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import multiprocessing as mp

from .domain import Domain
from . import heuristics as H
from .algorithms.base import Limits
from .algorithms.astar import AStarEarly

# ------------------------------------------------------------------ #
# Schema (design doc 6.3, exactly)                                   #
# ------------------------------------------------------------------ #

CONFIG_FIELDS = [
    "n_colors", "capacity", "n_empty", "n_tubes", "instance_seed",
    "operator_model", "cost_model", "canon_level", "algorithm",
    "algo_param", "heuristic", "tie_break", "goal_test", "dup_policy",
]

CSV_COLUMNS = [
    "run_key", "timestamp", "git_commit", "hostname", "python_impl",
    "python_version",
    "n_colors", "capacity", "n_empty", "n_tubes", "instance_seed",
    "instance_solvable",
    "operator_model", "cost_model", "canon_level", "algorithm",
    "algo_param", "heuristic", "tie_break", "goal_test", "dup_policy",
    "solved", "timeout_reason", "solution_cost", "solution_length_moves",
    "c_star", "subopt_ratio",
    "expanded", "generated", "duplicates_detected", "reopened",
    "dead_ends_detected", "h_evaluations", "canon_calls", "canon_time_s",
    "wall_time_s", "peak_rss_mb", "open_max_size", "closed_max_size",
    "iterations", "first_incumbent_time_s",
]

# Constant controls for this project (design doc 5.3), recorded per row.
DEFAULTS = {
    "operator_model": "pour",
    "tie_break": "f,-g,fifo",
    "dup_policy": "open_u_closed_reopen",
}


def run_key(cfg: dict) -> str:
    """SHA1 of the sorted config dict, config fields only (6.3)."""
    payload = ";".join(f"{k}={cfg[k]}" for k in sorted(CONFIG_FIELDS))
    return hashlib.sha1(payload.encode()).hexdigest()


def expand_grid(grid: dict, filter_fn=None):
    """Cross product of the grid dict (scalars = fixed).  Deterministic
    order.  `n_tubes` is derived, never given."""
    keys = [k for k in CONFIG_FIELDS if k != "n_tubes"]
    lists = []
    for k in keys:
        v = grid.get(k, DEFAULTS.get(k))
        if v is None:
            raise ValueError(f"grid missing field {k}")
        lists.append(v if isinstance(v, (list, tuple)) else [v])
    out = []
    idx = [0] * len(keys)
    while True:
        cfg = {k: lists[i][idx[i]] for i, k in enumerate(keys)}
        cfg["n_tubes"] = cfg["n_colors"] + cfg["n_empty"]
        if filter_fn is None or filter_fn(cfg):
            out.append(cfg)
        # odometer
        for i in range(len(keys) - 1, -1, -1):
            idx[i] += 1
            if idx[i] < len(lists[i]):
                break
            idx[i] = 0
        else:
            return out


# ------------------------------------------------------------------ #
# The child                                                          #
# ------------------------------------------------------------------ #

class _WallAlarm(Exception):
    pass


def _on_alarm(_sig, _frm):
    raise _WallAlarm()


def _child_run(args):
    """Executed in a fresh process (maxtasksperchild=1).  Never raises:
    every outcome is a row dict."""
    cfg, limits_d, solvable_filter, solvable_cap = args
    row = {k: cfg.get(k) for k in CONFIG_FIELDS}
    row["run_key"] = run_key(cfg)
    row["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    row.update(_environment_fields())
    lim = Limits(**limits_d)

    # Hard backstops around the cooperative limits.
    if lim.max_rss_mb is not None:
        # RLIMIT_AS is virtual memory; give 512 MB headroom over the RSS
        # cap so the interpreter itself fits.
        cap = int((lim.max_rss_mb + 512) * 1024 * 1024)
        try:
            resource_mod = __import__("resource")
            resource_mod.setrlimit(resource_mod.RLIMIT_AS, (cap, cap))
        except (ValueError, OSError):
            pass
    if lim.wall_s is not None:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(int(math.ceil(lim.wall_s)) + 5)   # 5 s grace

    try:
        dom = Domain(cfg["n_colors"], cfg["capacity"], cfg["n_empty"],
                     canon_level=cfg["canon_level"],
                     cost_model=cfg["cost_model"])
        s0 = dom.generate_instance(cfg["instance_seed"])

        if solvable_filter:
            sv = dom.solvable(s0, node_cap=solvable_cap)
            row["instance_solvable"] = sv
            if sv is not True:
                row["solved"] = False
                row["timeout_reason"] = ("unsolvable_instance" if sv is False
                                         else "solvable_undecided")
                return row
        else:
            row["instance_solvable"] = None

        if cfg["algorithm"] not in ("astar_early", "astar_late"):
            raise ValueError(f"unknown algorithm {cfg['algorithm']}")
        alg = AStarEarly(goal_test=cfg["algorithm"].split("_")[1])
        heu = H.make(cfg["heuristic"])
        res = alg.solve(dom, s0, heu, lim)
        signal.alarm(0)

        row["solved"] = res.solved
        row["timeout_reason"] = res.timeout_reason
        row["solution_cost"] = res.cost
        row["solution_length_moves"] = (len(res.moves)
                                        if res.moves is not None else None)
        if res.solved:
            dom.validate_solution(s0, res.moves)      # gate 2, always on
        row["c_star"] = None          # filled by analysis when oracle-known
        row["subopt_ratio"] = None
        for f in ("expanded", "generated", "duplicates_detected", "reopened",
                  "dead_ends_detected", "h_evaluations", "canon_calls",
                  "canon_time_s", "wall_time_s", "peak_rss_mb",
                  "open_max_size", "closed_max_size", "iterations",
                  "first_incumbent_time_s"):
            row[f] = getattr(res.stats, f)
    except _WallAlarm:
        row["solved"] = False
        row["timeout_reason"] = "wall_hard"
    except MemoryError:
        row["solved"] = False
        row["timeout_reason"] = "memory_hard"
    except Exception as exc:                           # crash => row, not death
        row["solved"] = False
        row["timeout_reason"] = f"error:{type(exc).__name__}"
    finally:
        signal.alarm(0)
    return row


_ENV_CACHE = None


def _environment_fields():
    global _ENV_CACHE
    if _ENV_CACHE is None:
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ).stdout.strip() or "unknown"
        except Exception:
            commit = "unknown"
        _ENV_CACHE = {
            "git_commit": commit,
            "hostname": socket.gethostname(),
            "python_impl": platform.python_implementation(),
            "python_version": platform.python_version(),
        }
    return _ENV_CACHE


# ------------------------------------------------------------------ #
# The parent loop                                                    #
# ------------------------------------------------------------------ #

def load_done_keys(csv_path: str) -> set:
    done = set()
    if os.path.exists(csv_path):
        with open(csv_path, newline="") as fh:
            for r in csv.DictReader(fh):
                done.add(r["run_key"])
    return done


def run_grid(grid: dict, csv_path: str, limits: Limits = None,
             filter_fn=None, dry_run=False, solvable_filter=False,
             solvable_cap=2_000_000, procs=1, log=print,
             interleave=True) -> int:
    """Expand, resume, execute, append.  Returns number of rows written.

    `interleave=True` orders runs so the grid's cells are visited round-
    robin rather than cell-by-cell; a partially completed (or killed)
    batch then covers the whole grid thinly instead of one corner
    densely, which is what you want for a calibration pilot."""
    limits = limits or Limits()
    cfgs = expand_grid(grid, filter_fn)
    all_keys = [run_key(c) for c in cfgs]
    if len(set(all_keys)) != len(all_keys):
        raise ValueError("grid produced duplicate run_keys")
    done = load_done_keys(csv_path)
    todo = [c for c, k in zip(cfgs, all_keys) if k not in done]
    if interleave:
        # Sort by instance_seed first => one instance per cell, then the
        # second instance per cell, ...
        todo.sort(key=lambda c: (c["instance_seed"],
                                 c["n_colors"], c["capacity"], c["n_empty"]))
    n_done_here = sum(1 for k in all_keys if k in done)
    log(f"[runner] grid={len(cfgs)} done={n_done_here} todo={len(todo)}")
    if dry_run:
        return 0

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    new_file = not os.path.exists(csv_path)
    fh = open(csv_path, "a", newline="")
    writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
    if new_file:
        writer.writeheader()
        fh.flush(); os.fsync(fh.fileno())

    limits_d = {"wall_s": limits.wall_s, "max_generated": limits.max_generated,
                "max_rss_mb": limits.max_rss_mb,
                "check_every": limits.check_every}
    jobs = [(c, limits_d, solvable_filter, solvable_cap) for c in todo]
    written = 0
    t0 = time.time()
    ctx = mp.get_context("fork")
    with ctx.Pool(processes=procs, maxtasksperchild=1) as pool:
        for row in pool.imap(_child_run, jobs, chunksize=1):
            writer.writerow({k: row.get(k) for k in CSV_COLUMNS})
            fh.flush(); os.fsync(fh.fileno())          # crash-safe append
            written += 1
            if written % 10 == 0 or written == len(jobs):
                log(f"[runner] {written}/{len(jobs)} rows "
                    f"({time.time()-t0:.0f}s)")
    fh.close()
    return written


# ------------------------------------------------------------------ #
# CLI                                                                #
# ------------------------------------------------------------------ #

def main(argv=None):
    import argparse, json
    ap = argparse.ArgumentParser(description="ballsort experiment runner")
    ap.add_argument("gridfile", help="JSON file: {'grid': {...}, "
                    "'limits': {...}, 'solvable_filter': bool}")
    ap.add_argument("csv", help="output CSV (append+resume)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--procs", type=int, default=1)
    args = ap.parse_args(argv)
    spec = json.load(open(args.gridfile))
    lim = Limits(**spec.get("limits", {}))
    n = run_grid(spec["grid"], args.csv, lim,
                 dry_run=args.dry_run,
                 solvable_filter=spec.get("solvable_filter", False),
                 procs=args.procs)
    print(f"[runner] wrote {n} rows -> {args.csv}")


if __name__ == "__main__":
    main()
