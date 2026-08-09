"""Fast unit tests for Milestone 2 (the heavyweight verification lives in
scripts/run_gates.py; these are the seconds-scale CI checks)."""

import pytest

from ballsort.domain import Domain
from ballsort import heuristics as H
from ballsort.oracle import enumerate_space, build_graph, h_star, INF
from ballsort.algorithms.base import Limits, Stats
from ballsort.algorithms.astar import AStarEarly
from ballsort.runner import run_key, expand_grid

FREE = Limits(wall_s=None, max_generated=None, max_rss_mb=None)


def test_mini_oracle_exact_optimality_m1():
    """Every state of N=3,C=3,E=2: A*-EARLY with h0 and h4 returns h*."""
    dom = Domain(3, 3, 2)
    states = enumerate_space(dom)
    _idx, fwd = build_graph(dom, states)
    hs, _ = h_star(dom, states, fwd, "M1")
    alg = AStarEarly(assert_no_reopen=True)
    for name in ("h0", "h4"):
        heu = H.make(name)
        for i, s in enumerate(states):
            if hs[i] == INF:
                continue
            r = alg.solve(dom, s, heu, FREE)
            assert r.solved and r.cost == hs[i]
            if r.cost:
                dom.validate_solution(s, r.moves)


def test_early_late_m2_regression():
    """The concrete counterexample found by the oracle gate: under M2 the
    EARLY goal test returns 7 where h*=6; LATE returns 6.  Pins both the
    behaviour and the reason we assert M2 optimality on LATE only."""
    s = (b"\x01\x02\x00", b"\x02\x01\x00", b"\x02\x01\x03", b"\x03\x03\x00")
    dom = Domain(3, 3, 1, cost_model="M2")
    h0 = H.make("h0")
    r_early = AStarEarly(goal_test="early").solve(dom, s, h0, FREE)
    r_late = AStarEarly(goal_test="late").solve(dom, s, h0, FREE)
    assert r_late.cost == 6
    assert r_early.cost == 7
    dom.validate_solution(s, r_early.moves)
    dom.validate_solution(s, r_late.moves)


def test_early_equals_late_m1():
    """Under M1 the two goal-test policies agree on cost (sampled)."""
    dom = Domain(4, 4, 2)
    for seed in range(8):
        s0 = dom.generate_instance(seed)
        c1 = AStarEarly(goal_test="early").solve(dom, s0, H.make("h4"), FREE).cost
        c2 = AStarEarly(goal_test="late").solve(dom, s0, H.make("h4"), FREE).cost
        assert c1 == c2


def test_generated_cap_produces_timeout_row():
    dom = Domain(6, 4, 2)
    s0 = dom.generate_instance(0)
    r = AStarEarly().solve(dom, s0, H.make("h0"),
                           Limits(wall_s=None, max_generated=500,
                                  max_rss_mb=None))
    assert not r.solved and r.timeout_reason == "generated"
    assert r.stats.generated >= 500 and r.moves is None


def test_unsolvable_exhausts_cleanly():
    """A provably unsolvable instance must exhaust OPEN and come back
    unsolved with NO timeout reason (that is the provable-unsolvable
    signature at the algorithm level)."""
    dom = Domain(3, 4, 1)
    for seed in range(60):
        s0 = dom.generate_instance(seed)
        if dom.solvable(s0) is False:
            r = AStarEarly().solve(dom, s0, H.make("h4"), FREE)
            assert not r.solved and r.timeout_reason is None
            return
    pytest.skip("no unsolvable seed found in range")


def test_determinism_and_stats_fields():
    dom = Domain(5, 4, 2)
    s0 = dom.generate_instance(1)
    r1 = AStarEarly().solve(dom, s0, H.make("h3"), FREE)
    r2 = AStarEarly().solve(dom, s0, H.make("h3"), FREE)
    assert r1.stats.deterministic_tuple() == r2.stats.deterministic_tuple()
    assert r1.moves == r2.moves
    # canon accounting present and sane
    assert r1.stats.canon_calls > 0
    assert 0.0 <= r1.stats.canon_time_s <= r1.stats.wall_time_s + 1e-9


def test_run_key_stability_and_grid():
    grid = {"n_colors": [3, 4], "capacity": 4, "n_empty": 2,
            "instance_seed": [0, 1, 2], "cost_model": "M1",
            "canon_level": "L1", "algorithm": "astar_early",
            "algo_param": "", "heuristic": "h4", "goal_test": "early"}
    cfgs = expand_grid(grid)
    assert len(cfgs) == 6
    keys = {run_key(c) for c in cfgs}
    assert len(keys) == 6
    # key depends only on config fields, and is order/insert stable
    c = dict(cfgs[0]); c2 = dict(reversed(list(c.items())))
    assert run_key(c) == run_key(c2)
