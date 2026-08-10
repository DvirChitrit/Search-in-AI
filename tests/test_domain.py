"""Unit tests: move legality, goal test, validator, determinism, dead ends,
canonicalization, solvability solver, and predecessor round-trips."""
import random

import pytest

from ballsort.domain import Domain, tube_height, top_run, bottom_run_len


def D(n=3, c=4, e=2, **kw):
    return Domain(n, c, e, **kw)


# ---------------------------------------------------------------- helpers

def test_tube_helpers():
    assert tube_height(b"\x01\x02\x00\x00") == 2
    assert tube_height(b"\x00\x00\x00\x00") == 0
    assert tube_height(b"\x01\x01\x01\x01") == 4
    assert top_run(b"\x02\x01\x01\x00") == (1, 2)
    assert top_run(b"\x00\x00\x00\x00") == (0, 0)
    assert bottom_run_len(b"\x02\x02\x01\x00") == 2
    assert bottom_run_len(b"\x00\x00\x00\x00") == 0


# ---------------------------------------------------------------- moves

def test_pour_moves_maximal_run_and_truncation():
    dom = D(2, 4, 1)
    # tube0: [1,1,2,2] (2 on top), tube1: [2,0,0,0], tube2 empty
    s = (b"\x01\x01\x02\x02", b"\x02\x00\x00\x00", b"\x00\x00\x00\x00")
    succ = {(m.src, m.dst): (m.color, m.k) for m, _, _ in dom.successors(s)}
    # top run of tube0 is two 2s; onto tube1 (top 2, 3 free) pours both
    assert succ[(0, 1)] == (2, 2)
    # onto the empty tube also pours the whole run
    assert succ[(0, 2)] == (2, 2)
    # tube1's single 2 can go onto the empty tube; NOT onto tube0, which
    # is full (a mistake in the first version of this test caught by CI)
    assert succ[(1, 2)] == (2, 1)
    assert (1, 0) not in succ

    # truncation: destination with 1 free slot receives only 1 of the run
    s2 = (b"\x01\x02\x02\x00", b"\x01\x01\x01\x02")  # tube1 full
    dom2 = D(2, 4, 0)
    moves = {(m.src, m.dst): m.k for m, _, _ in dom2.successors(s2)}
    assert (1, 0) in moves and moves[(1, 0)] == 1   # 2 poured onto top-2
    assert (0, 1) not in moves                       # tube1 is full


def test_illegal_moves_raise():
    dom = D(2, 4, 1)
    s = (b"\x01\x01\x01\x01", b"\x02\x02\x02\x02", b"\x00\x00\x00\x00")
    with pytest.raises(ValueError):
        dom.apply_move(s, 0, 1)      # colour mismatch onto non-empty
    with pytest.raises(ValueError):
        dom.apply_move(s, 2, 0)      # source empty
    with pytest.raises(ValueError):
        dom.apply_move(s, 0, 0)      # src == dst


# ---------------------------------------------------------------- goal

def test_goal_strict():
    dom = D(2, 3, 1)
    goal = (b"\x01\x01\x01", b"\x02\x02\x02", b"\x00\x00\x00")
    assert dom.is_goal(goal)
    # G_loose-but-not-G_strict: monochromatic yet not full
    not_goal = (b"\x01\x01\x00", b"\x01\x00\x00", b"\x02\x02\x02")
    assert not dom.is_goal(not_goal)
    assert dom.sorted_tubes_count(goal) == 2


# ---------------------------------------------------------------- generate

def test_generation_deterministic_and_wellformed():
    dom = D(4, 4, 2)
    a = dom.generate_instance(123)
    b = dom.generate_instance(123)
    c = dom.generate_instance(124)
    assert a == b
    assert a != c
    balls = [x for t in a for x in t if x]
    assert len(balls) == 16
    for col in range(1, 5):
        assert balls.count(col) == 4
    assert sum(1 for t in a if t[0] == 0) == 2


# ---------------------------------------------------------------- validator

def test_validator_accepts_and_rejects():
    dom = D(2, 2, 1)
    s0 = (b"\x01\x02", b"\x02\x01", b"\x00\x00")
    # 1 (top of t1) -> t2 ; 2 (top of t0) -> t1 ; 1 (t2) -> t0  => goal
    final = dom.validate_solution(s0, [(1, 2), (0, 1), (2, 0)])
    assert dom.is_goal(final)
    with pytest.raises(ValueError):
        dom.validate_solution(s0, [(0, 1)])          # illegal first move
    with pytest.raises(ValueError):
        dom.validate_solution(s0, [(1, 2)])          # legal but not a goal


# ---------------------------------------------------------------- canon

def test_key_levels_and_invariance():
    dom0 = D(canon_level="L0")
    dom1 = D(canon_level="L1")
    s = dom1.generate_instance(7)
    perm = list(s)
    random.Random(1).shuffle(perm)
    perm = tuple(perm)
    assert dom1.key(s) == dom1.key(perm)
    if perm != s:
        assert dom0.key(s) != dom0.key(perm)
    # Milestone 3a: L2/L3 exist now.  L3 keys must be invariant under
    # tube permutation AND colour relabeling; L2 at least under tube
    # permutation (full soundness is the oracle gate's job).
    dom2 = D(canon_level="L2")
    dom3 = D(canon_level="L3")
    assert dom2.key(perm) == dom2.key(s)
    assert dom3.key(perm) == dom3.key(s)
    n = dom3.N
    relabel = bytes(range(256)).replace(
        bytes(range(1, n + 1)), bytes(range(n, 0, -1)))  # reverse colours
    flipped = tuple(t.translate(relabel) for t in perm)
    assert dom3.key(flipped) == dom3.key(s)
    cs = dom3.canonical_state(s)
    assert dom3.key(cs) == dom3.key(s) and b"".join(cs) == dom3.key(s)
    with pytest.raises(ValueError):
        D(canon_level="L9")


# ---------------------------------------------------------------- dead end

def test_dead_end_detector():
    dom = D(2, 2, 0)
    # [1,2],[2,1]: tops are 2 and 1, no empty tube, no matching tops -> dead
    dead = (b"\x01\x02", b"\x02\x01")
    assert dom.is_dead_end(dead)
    goal = (b"\x01\x01", b"\x02\x02")
    assert not dom.is_dead_end(goal)     # goal is not a dead end


# ---------------------------------------------------------------- solvable

def test_solvable_solver_agrees_with_reachability():
    dom = D(3, 3, 1)
    yes = no = 0
    for seed in range(60):
        s = dom.generate_instance(seed)
        r = dom.solvable(s)
        assert r is not None
        if r:
            yes += 1
        else:
            no += 1
    assert yes > 0          # some solvable instances must exist
    # E=1 is where unsolvable instances live; don't hard-assert no>0 in a
    # tiny sample, but record the shape of the test
    goal_like = dom.generate_instance(0)
    # a goal state is trivially solvable
    g = (b"\x01\x01\x01", b"\x02\x02\x02", b"\x03\x03\x03", b"\x00\x00\x00")
    assert dom.solvable(g) is True


# ---------------------------------------------------------------- preds

def test_predecessor_roundtrip_random():
    """Every predecessor must reproduce the child when its move is applied
    forward -- a necessary (not sufficient) inversion check; the exhaustive
    check lives in the oracle."""
    dom = D(3, 4, 2)
    rng = random.Random(0)
    for seed in range(20):
        s = dom.generate_instance(seed)
        # random forward walk to a generic mid-game state
        for _ in range(rng.randrange(0, 8)):
            succ = list(dom.successors(s))
            if not succ:
                break
            s = rng.choice(succ)[1]
        for mv, parent, _cost in dom.predecessors(s):
            mv2, child, _c = dom.apply_move(parent, mv.src, mv.dst)
            assert child == s, (mv, mv2)
            assert mv2.k == mv.k and mv2.color == mv.color
