"""Heuristic tests: definitional equivalences, goal-zero, incremental ==
from-scratch along random walks, and the h5/M1 inadmissibility example."""
import random

from ballsort.domain import Domain, runs_in_tube
from ballsort import heuristics as H


def all_h():
    return [H.make(n) for n in ("h0", "h1", "h2", "h3", "h4", "h5")]


def test_equivalent_definitions():
    """The per-tube forms implemented must equal the per-colour forms in
    the design doc, on random states."""
    dom = Domain(4, 4, 2)
    h1, h2, h3, h4 = (H.make(n) for n in ("h1", "h2", "h3", "h4"))
    for seed in range(40):
        s = dom.generate_instance(seed)
        # per-colour recomputation
        N = dom.N
        runs_c = {c: 0 for c in range(1, N + 1)}
        tubes_c = {c: 0 for c in range(1, N + 1)}
        bottom_c = {c: 0 for c in range(1, N + 1)}
        R = 0
        n_ne = 0
        for t in s:
            if t[0]:
                n_ne += 1
                bottom_c[t[0]] = 1
            prev = 0
            present = set()
            for b in t:
                if b == 0:
                    break
                present.add(b)
                if b != prev:
                    runs_c[b] += 1
                    R += 1
                    prev = b
            for c in present:
                tubes_c[c] += 1
        assert h1.h(s) == R - n_ne
        assert h2.h(s) == sum(v - 1 for v in tubes_c.values())
        assert h3.h(s) == sum(v - 1 for v in runs_c.values()) == R - N
        assert h4.h(s) == sum(runs_c[c] - bottom_c[c] for c in runs_c)


def test_zero_at_goal():
    dom = Domain(3, 3, 2)
    g = (b"\x01\x01\x01", b"\x02\x02\x02", b"\x03\x03\x03",
         b"\x00\x00\x00", b"\x00\x00\x00")
    for h in all_h():
        assert h.h(g) == 0, h.name


def test_incremental_matches_scratch_on_walks():
    H.CHECK_INCREMENTAL = True     # asserts inside every incremental call
    try:
        dom = Domain(4, 4, 2)
        rng = random.Random(42)
        for seed in range(15):
            s = dom.generate_instance(seed)
            hs = {h.name: h.h(s) for h in all_h()}
            heus = {h.name: h for h in all_h()}
            for _ in range(30):
                succ = list(dom.successors(s))
                if not succ:
                    break
                mv, child, _cost = rng.choice(succ)
                for name, h in heus.items():
                    hs[name] = h.h_incremental(hs[name], s, mv, child)
                    assert hs[name] == h.h(child)
                s = child
    finally:
        H.CHECK_INCREMENTAL = False


def test_h5_inadmissible_under_M1_by_example():
    """One pour of k=3 balls reduces h5 by 3 while costing 1 under M1 --
    the concrete inadmissibility witness from design doc 3.5."""
    dom = Domain(2, 4, 1)
    h5 = H.make("h5")
    # Well-formed N=2, C=4 instance (four balls of each colour):
    # t0 = [2,1,1,1], t1 = [2,2,2,_], t2 = [1,_,_,_]
    s = (b"\x02\x01\x01\x01", b"\x02\x02\x02\x00", b"\x01\x00\x00\x00")
    # One pour moves the three 1s onto t2's matching top:
    mv, child, cost = dom.apply_move(s, 0, 2)
    assert mv.k == 3
    assert h5.h(s) - h5.h(child) == 3      # h5 dropped by 3, M1 cost 1
    # Optimal M1 solution has cost 2: (0->2) then (0->1).
    final = dom.validate_solution(s, [(0, 2), (0, 1)])
    assert dom.is_goal(final)
    # h5(s) = 3 > C* = 2: a concrete M1-inadmissibility witness.
    assert h5.h(s) == 3
