"""Deterministic tests for the evolving belief graph (no LLM).

Proves the full lifecycle on one structure: seed / assimilate / incubate (k-gate) /
revise / retract / accrete / revive, plus the soundness fixes — fresh-evidence
counting (no stale-vote revival), context fallback + absorption, contested
suspension, k-gated negatives — and multi-hop reachability.
"""
from schemamem.graph_core import EvolvingGraph, Action, Card


def _g():
    return EvolvingGraph(k=2, flip_max=2)


def test_seed_then_assimilate():
    g = _g()
    assert g.ingest("user", "diet", "vegetarian", episode_id="e1") is Action.SEED
    assert g.ingest("user", "diet", "vegetarian", episode_id="e2") is Action.ASSIMILATE
    assert g.believe("user", "diet") == "vegetarian"


def test_one_off_conflict_incubates_then_revises():
    """A single conflicting episode does not change the belief (k-gate); a second does."""
    g = _g()
    g.ingest("user", "diet", "vegetarian", episode_id="e1")
    g.ingest("user", "diet", "vegetarian", episode_id="e2")
    assert g.ingest("user", "diet", "pescatarian", episode_id="e3") is Action.INCUBATE
    assert g.believe("user", "diet") == "vegetarian"           # unchanged
    assert g.ingest("user", "diet", "pescatarian", episode_id="e4") is Action.REVISE
    assert g.believe("user", "diet") == "pescatarian"


def test_fresh_evidence_no_stale_vote_revival():
    """A once-held value needs k FRESH episodes to win back — its old votes have expired."""
    g = _g()
    g.ingest("user", "diet", "vegetarian", episode_id="e1")
    g.ingest("user", "diet", "vegetarian", episode_id="e2")     # veg has 2 all-time votes
    g.ingest("user", "diet", "pescatarian", episode_id="e3")
    g.ingest("user", "diet", "pescatarian", episode_id="e4")    # -> pescatarian
    # one fresh "vegetarian" must NOT flip it back despite e1,e2 in history
    assert g.ingest("user", "diet", "vegetarian", episode_id="e5") is Action.INCUBATE
    assert g.believe("user", "diet") == "pescatarian"
    # a second fresh episode reopens the old belief -> REVIVE
    assert g.ingest("user", "diet", "vegetarian", episode_id="e6") is Action.REVIVE
    assert g.believe("user", "diet") == "vegetarian"


def test_plural_accretes_and_coexists():
    g = _g()
    assert g.ingest("Apple", "developed", "iPod", cardinality=Card.PLURAL, episode_id="e1") is Action.ACCRETE
    assert g.ingest("Apple", "developed", "QuickTime", cardinality=Card.PLURAL, episode_id="e2") is Action.ACCRETE
    assert g.believe("Apple", "developed") == ["QuickTime", "iPod"]


def test_plural_member_retracts_and_revives():
    """Plural members are not permanent: explicit negative evidence (k) removes one; it can revive."""
    g = _g()
    g.ingest("user", "hobby", "climbing", cardinality=Card.PLURAL, episode_id="e1")
    g.ingest("user", "hobby", "chess", cardinality=Card.PLURAL, episode_id="e2")
    assert g.ingest("user", "hobby", "climbing", cardinality=Card.PLURAL, polarity="-", episode_id="e3") is Action.INCUBATE
    assert g.ingest("user", "hobby", "climbing", cardinality=Card.PLURAL, polarity="-", episode_id="e4") is Action.RETRACT
    assert g.believe("user", "hobby") == ["chess"]             # climbing gone, chess stays
    assert g.ingest("user", "hobby", "climbing", cardinality=Card.PLURAL, episode_id="e5") is Action.REVIVE
    assert g.believe("user", "hobby") == ["chess", "climbing"]


def test_functional_retract_to_none():
    """Negative evidence can remove a functional belief with no successor (unemployed)."""
    g = _g()
    g.ingest("user", "employer", "Acme", episode_id="e1")
    g.ingest("user", "employer", "Acme", polarity="-", episode_id="e2")   # incubate-retire
    assert g.ingest("user", "employer", "Acme", polarity="-", episode_id="e3") is Action.RETRACT
    assert g.believe("user", "employer") is None
    # the retracted belief is kept as history, not deleted
    acme = g.edges[("user", "employer", "Acme", "default")]
    assert acme.is_past() and acme.pos == {"e1"}


def test_context_exception_then_absorbed():
    """A weekend exception holds only while it differs from the default; when the default
    catches up to it, the exception is absorbed."""
    g = _g()
    g.ingest("user", "diet", "vegetarian", episode_id="e1")
    g.ingest("user", "diet", "vegetarian", episode_id="e2")
    g.ingest("user", "diet", "pescatarian", episode_id="e3")
    g.ingest("user", "diet", "pescatarian", episode_id="e4")               # default = pescatarian
    assert g.ingest("user", "diet", "vegetarian", context="weekend", episode_id="e5") is Action.SEED
    assert g.believe("user", "diet", "weekend") == "vegetarian"            # exception active
    assert g.believe("user", "diet", "weekday") == "pescatarian"           # fallback to default
    # default reverts to vegetarian -> the weekend exception is absorbed
    g.ingest("user", "diet", "vegetarian", episode_id="e6")
    g.ingest("user", "diet", "vegetarian", episode_id="e7")
    weekend = g.edges[("user", "diet", "vegetarian", "weekend")]
    assert weekend.absorbed and not weekend.is_current()
    assert g.believe("user", "diet", "weekend") == "vegetarian"            # now via default


def test_conditional_belief_survives():
    """Two contexts with no default coexist as a stable conditional (weekday office / weekend home)."""
    g = _g()
    assert g.ingest("user", "workmode", "office", context="weekday", episode_id="e1") is Action.SEED
    assert g.ingest("user", "workmode", "home", context="weekend", episode_id="e2") is Action.SEED
    assert g.believe("user", "workmode", "weekday") == "office"
    assert g.believe("user", "workmode", "weekend") == "home"


def test_oscillation_becomes_contested():
    """A slot that genuinely oscillates past flip_max is suspended — no forced winner."""
    g = _g()
    g.ingest("user", "city", "Beijing", episode_id="c1")
    g.ingest("user", "city", "Shanghai", episode_id="c2")
    assert g.ingest("user", "city", "Shanghai", episode_id="c3") is Action.REVISE   # flip 1
    g.ingest("user", "city", "Beijing", episode_id="c4")
    assert g.ingest("user", "city", "Beijing", episode_id="c5") is Action.REVIVE    # flip 2 (Beijing returns)
    g.ingest("user", "city", "Shanghai", episode_id="c6")
    assert g.ingest("user", "city", "Shanghai", episode_id="c7") is Action.CONTESTED
    assert g.believe("user", "city") == "UNRESOLVED"


def test_asserted_absent_is_k_gated():
    """One 'not X' about a never-held belief is tentative; two make a firm negative belief."""
    g = _g()
    assert g.ingest("user", "haskids", "children", polarity="-", episode_id="e1") is Action.NOOP
    assert g.ingest("user", "haskids", "children", polarity="-", episode_id="e2") is Action.ASSERT_ABSENT
    assert g.believe("user", "haskids") == "ABSENT"


def test_multi_hop_over_belief_edges():
    """An answer reachable by chaining relations, stored nowhere directly."""
    g = _g()
    g.ingest("Nick", "coaches", "RSL", episode_id="m1")
    g.ingest("RSL", "plays_sport", "soccer", episode_id="m2")
    assert g.hop("Nick", ["coaches", "plays_sport"]) == ["soccer"]
    assert g.hop("Nick", ["coaches"]) == ["RSL"]


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for tfn in tests:
        try:
            tfn()
            print(f"PASS {tfn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {tfn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
