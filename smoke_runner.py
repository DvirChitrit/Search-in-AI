"""Runner smoke test (M2 Deliverable 4, last bullet).

1. Launch the runner on a 10-run grid in a subprocess.
2. SIGKILL it after the CSV has a few rows (kill -9: no cleanup allowed).
3. Restart the same command.
4. Assert: all 10 runs present, zero duplicate run_keys, all rows parse.
"""

import csv
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CSV = os.path.join(REPO, "results", "smoke.csv")
GRID = os.path.join(REPO, "results", "smoke_grid.json")

spec = {
    "grid": {
        "n_colors": 4, "capacity": 4, "n_empty": 2,
        "instance_seed": list(range(10)),
        "cost_model": "M1", "canon_level": "L1",
        "algorithm": "astar_early", "algo_param": "",
        "heuristic": "h4", "goal_test": "early",
    },
    "limits": {"wall_s": 30, "max_generated": 1000000, "max_rss_mb": 2048},
    "solvable_filter": True,
}

os.makedirs(os.path.join(REPO, "results"), exist_ok=True)
for p in (CSV, GRID):
    if os.path.exists(p):
        os.remove(p)
json.dump(spec, open(GRID, "w"))

cmd = [sys.executable, "-m", "ballsort.runner", GRID, CSV]

# -- phase 1: start and kill mid-way ---------------------------------
p = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
deadline = time.time() + 60
rows_seen = 0
while time.time() < deadline:
    if os.path.exists(CSV):
        with open(CSV) as fh:
            rows_seen = max(0, sum(1 for _ in fh) - 1)
        if rows_seen >= 3:
            break
    time.sleep(0.05)
assert rows_seen >= 3, f"never saw 3 rows before deadline (saw {rows_seen})"
os.killpg(os.getpgid(p.pid), signal.SIGKILL)          # kill runner + child
p.wait()
print(f"[smoke] killed runner (SIGKILL) after {rows_seen} rows")

# -- phase 2: restart, must resume and complete ----------------------
out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                     timeout=120)
print(out.stdout.strip())
assert out.returncode == 0

# -- phase 3: verify --------------------------------------------------
with open(CSV, newline="") as fh:
    rows = list(csv.DictReader(fh))
keys = [r["run_key"] for r in rows]
assert len(rows) == 10, f"expected 10 rows, got {len(rows)}"
assert len(set(keys)) == 10, "DUPLICATE run_keys after resume!"
assert all(r["solved"] in ("True", "False") for r in rows)
solved = sum(r["solved"] == "True" for r in rows)
unsolvable = sum(r["timeout_reason"] == "unsolvable_instance" for r in rows)
print(f"[smoke] OK: 10 unique rows after kill+resume "
      f"({solved} solved, {unsolvable} unsolvable, "
      f"resume added {10 - rows_seen})")
