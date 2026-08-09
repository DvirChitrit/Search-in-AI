"""Milestone 2: SearchAlgorithm protocol and the shared Stats / Limits /
Result objects (design doc 6.1, 5.4, 6.3).

Every algorithm added in Milestone 5 (IDA*, DFBnB, WA*, GBFS, beam) must
implement the same `solve(domain, s0, heuristic, limits) -> Result`
signature and fill the same Stats object, so the runner and the analysis
code never change.  Fields an algorithm does not use stay at their
defaults (0/None), which the CSV writer serialises as-is.

Stdlib only (PyPy compatibility).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple


@dataclass
class Limits:
    """Per-run resource caps (design doc 5.2).

    The algorithm checks these *cooperatively* (cheaply, every
    `check_every` expansions); the runner additionally enforces them
    *preemptively* in the child process via SIGALRM + setrlimit, so a run
    that ignores its limits still becomes a CSV row, not a hung batch.
    """

    wall_s: Optional[float] = 60.0            # wall-clock seconds
    max_generated: Optional[int] = 5_000_000  # generated-node cap
    max_rss_mb: Optional[float] = 4096.0      # memory cap (soft, via getrusage)
    check_every: int = 1024                   # expansions between limit checks


@dataclass
class Stats:
    """Every per-run metric in the CSV schema (design doc 6.3 / 5.4).

    Unused-by-this-algorithm fields default to 0/None -- e.g. `iterations`
    is only meaningful for IDA*/DFBnB, `first_incumbent_time_s` for
    anytime algorithms (for A*-EARLY it equals wall_time_s when solved).
    """

    expanded: int = 0
    generated: int = 0
    duplicates_detected: int = 0
    reopened: int = 0
    dead_ends_detected: int = 0
    h_evaluations: int = 0
    canon_calls: int = 0
    canon_time_s: float = 0.0
    wall_time_s: float = 0.0
    peak_rss_mb: float = 0.0
    open_max_size: int = 0
    closed_max_size: int = 0
    iterations: int = 0
    first_incumbent_time_s: Optional[float] = None

    # The fields that must be bit-identical across two runs of the same
    # config (gate 5).  Times and RSS are excluded -- they measure the
    # machine, not the search.
    DETERMINISTIC_FIELDS = (
        "expanded", "generated", "duplicates_detected", "reopened",
        "dead_ends_detected", "h_evaluations", "canon_calls",
        "open_max_size", "closed_max_size", "iterations",
    )

    def deterministic_tuple(self) -> tuple:
        return tuple(getattr(self, f) for f in self.DETERMINISTIC_FIELDS)


@dataclass
class Result:
    """What `solve` returns.  `moves` is a list of (src, dst) pairs legal
    from the *concrete* s0 (Domain.validate_solution must accept it)."""

    solved: bool
    timeout_reason: Optional[str]           # None|"wall"|"generated"|"memory"
    cost: Optional[int]                     # cost under domain.cost_model
    moves: Optional[List[Tuple[int, int]]]  # (src,dst) pairs replayable from s0
    stats: Stats = field(default_factory=Stats)


class SearchAlgorithm(Protocol):
    """Design doc 6.1.  `s0` is passed to solve() rather than baked into
    the Domain because one Domain instance serves many instances."""

    name: str

    def solve(self, domain, s0, heuristic, limits: Limits) -> Result: ...
