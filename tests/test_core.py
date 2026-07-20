"""Unit tests for the L3 changepoint arbitration core (no LLM)."""
from schemamem.core import SchemaGraph, Observation, Action


def _obs(value, pe, ep, t, cand):
    return Observation("user", "diet", value, pe, ep, t, candidate_id=cand)


def _run(stream, k=2, rewriter=None, seed_belief=None):
    g = SchemaGraph(k=k, rewriter=rewriter) if rewriter else SchemaGraph(k=k)
    if seed_belief:
        g.get_schema("user").get_slot("diet").belief = seed_belief
    actions = [g.ingest(o) for o in stream]
    g.finalize()
    return g, actions


def test_drift_vs_exception():
    """The canonical case: one-off steak -> exception; sustained fish -> accommodate."""
    rw = lambda old, c: "pescatarian" if c.candidate_id == "fish" else c.observations[-1].value
    stream = [
        _obs("strict-vegetarian", 0.0, "ep1", "t1", None),
        _obs("steak",             1.0, "ep2", "t2", "meat"),
        _obs("started fish",      1.0, "ep3", "t3", "fish"),
        _obs("salmon",            1.0, "ep4", "t4", "fish"),
        _obs("pescatarian",       0.2, "ep5", "t5", "fish"),
    ]
    g, acts = _run(stream, rewriter=rw, seed_belief="strict-vegetarian")
    assert acts == [Action.ASSIMILATE, Action.ACCUMULATE, Action.ACCUMULATE,
                    Action.ACCOMMODATE, Action.ASSIMILATE], acts
    s = g.get_schema("user").get_slot("diet")
    assert s.belief == "pescatarian"
    assert s.superseded == [("strict-vegetarian", "t4")]
    assert [o.value for o in s.exceptions] == ["steak"]  # only the one-off


def test_pure_exception_never_accommodates():
    """A violation seen in exactly one episode must stay an exception, never flip belief."""
    stream = [
        _obs("vegan",  0.0, "ep1", "t1", None),
        _obs("cheese", 1.0, "ep2", "t2", "dairy"),   # single isolated violation
        _obs("vegan",  0.0, "ep3", "t3", None),
    ]
    g, acts = _run(stream, seed_belief="vegan")
    assert acts == [Action.ASSIMILATE, Action.ACCUMULATE, Action.ASSIMILATE], acts
    s = g.get_schema("user").get_slot("diet")
    assert s.belief == "vegan"
    assert s.superseded == []
    assert [o.value for o in s.exceptions] == ["cheese"]


def test_episode_dedup_no_double_count():
    """Same candidate repeated within ONE episode counts once (no spurious accommodate)."""
    stream = [
        _obs("vegan",  0.0, "ep1", "t1", None),
        _obs("fish",   1.0, "ep2", "t2", "fish"),
        _obs("fish",   1.0, "ep2", "t2", "fish"),   # same episode -> still 1 vote
    ]
    g, acts = _run(stream, k=2, seed_belief="vegan")
    # second mention in same episode does not reach k=2
    assert acts[-1] == Action.ACCUMULATE, acts
    assert g.get_schema("user").get_slot("diet").belief == "vegan"


def test_no_conflict_stream_all_assimilate():
    stream = [
        _obs("Shanghai", 0.0, "ep1", "t1", None),
        _obs("Shanghai", 0.0, "ep2", "t2", None),
    ]
    g, acts = _run(stream, seed_belief="Shanghai")
    assert acts == [Action.ASSIMILATE, Action.ASSIMILATE]
    assert g.get_schema("user").get_slot("diet").exceptions == []


def test_k3_needs_three_episodes():
    rw = lambda old, c: "pescatarian"
    stream = [
        _obs("vegan", 0.0, "ep1", "t1", None),
        _obs("fish",  1.0, "ep2", "t2", "fish"),
        _obs("fish",  1.0, "ep3", "t3", "fish"),   # 2 votes, k=3 -> still accumulate
        _obs("fish",  1.0, "ep4", "t4", "fish"),   # 3 votes -> accommodate
    ]
    g, acts = _run(stream, k=3, rewriter=rw, seed_belief="vegan")
    assert acts == [Action.ASSIMILATE, Action.ACCUMULATE, Action.ACCUMULATE,
                    Action.ACCOMMODATE], acts


def test_online_decay_flushes_exception_before_finalize():
    """A stalled candidate ages into an exception ONLINE after decay_window episodes."""
    rw = lambda old, c: "pescatarian"
    g = SchemaGraph(k=2, online_decay=True, decay_window=2, rewriter=rw)
    stream = [
        _obs("strict-veg", 0.0, "ep1", "t1", None),
        _obs("steak",      1.0, "ep2", "t2", "meat"),   # isolated
        _obs("fish",       1.0, "ep3", "t3", "fish"),
        _obs("fish",       1.0, "ep4", "t4", "fish"),   # fish accommodates
        _obs("pescatarian",0.0, "ep5", "t5", None),
    ]
    for o in stream:
        g.ingest(o)
    s = g.get_schema("user").get_slot("diet")
    # steak decayed to exception WITHOUT needing finalize()
    assert "meat" not in s.candidates
    assert [o.value for o in s.exceptions] == ["steak"]


def test_online_decay_short_stream_still_caught_by_finalize():
    """If the stream ends before decay_window passes, finalize() still catches it."""
    g = SchemaGraph(k=2, online_decay=True, decay_window=5)
    for o in [_obs("vegan", 0.0, "ep1", "t1", None),
              _obs("steak", 1.0, "ep2", "t2", "meat")]:
        g.ingest(o)
    s = g.get_schema("user").get_slot("diet")
    assert s.exceptions == []          # not yet decayed (window not elapsed)
    g.finalize()
    assert [o.value for o in s.exceptions] == ["steak"]   # finalize backstop


def test_epsilon_dissolve_releases_redundant_but_not_seed():
    g = SchemaGraph(k=2, epsilon=0.1)
    acts = [g.ingest(o) for o in [
        _obs("vegan", 0.0, "ep1", "t1", None),   # seed -> ASSIMILATE (kept)
        _obs("vegan", 0.0, "ep2", "t2", None),   # redundant -> DISSOLVE
    ]]
    assert acts == [Action.ASSIMILATE, Action.DISSOLVE], acts
    s = g.get_schema("user").get_slot("diet")
    assert s.forgotten == 1
    assert s.belief == "vegan"
    assert s.ledger[0].forgettable is False and s.ledger[1].forgettable is True


def test_epsilon_none_never_dissolves():
    g = SchemaGraph(k=2, epsilon=None)   # forgetting disabled
    acts = [g.ingest(o) for o in [
        _obs("vegan", 0.0, "ep1", "t1", None),
        _obs("vegan", 0.0, "ep2", "t2", None),
    ]]
    assert Action.DISSOLVE not in acts
    assert g.get_schema("user").get_slot("diet").forgotten == 0


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}"); passed += 1
        except Exception:
            print(f"FAIL {t.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
