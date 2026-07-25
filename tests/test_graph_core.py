"""Deterministic tests for the evolving belief graph (no LLM).

Proves the full lifecycle on one structure: seed / assimilate / incubate (k-gate) /
revise / retract / accrete / revive, plus the soundness fixes — fresh-evidence
counting (no stale-vote revival), context fallback + absorption, contested
suspension, k-gated negatives — and multi-hop reachability.
"""
from schemamem.graph_core import EvolvingGraph, Action, Card, Resolver


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


def test_contested_resolves_with_decisive_evidence():
    """A contested slot is not a dead end: it can be settled by evidence clearing a raised bar
    (k+1) with no rival pushing back."""
    g = _g()
    for ep, o in [("c1", "Beijing"), ("c2", "Shanghai"), ("c3", "Shanghai"),
                  ("c4", "Beijing"), ("c5", "Beijing"), ("c6", "Shanghai"), ("c7", "Shanghai")]:
        g.ingest("user", "city", o, episode_id=ep)
    assert g.believe("user", "city") == "UNRESOLVED"
    # user decisively settles in Shanghai — the raised bar is k+1 = 3 fresh episodes
    assert g.ingest("user", "city", "Shanghai", episode_id="c8") is Action.CONTESTED   # 1
    assert g.ingest("user", "city", "Shanghai", episode_id="c9") is Action.CONTESTED   # 2, still short
    assert g.ingest("user", "city", "Shanghai", episode_id="c10") is Action.RESOLVE    # 3 -> settled
    assert g.believe("user", "city") == "Shanghai"


def test_asserted_absent_can_reopen():
    """ABSENT is not terminal: a positive assertion reopens the belief (I do have kids now)."""
    g = _g()
    g.ingest("user", "haskids", "children", polarity="-", episode_id="e1")
    g.ingest("user", "haskids", "children", polarity="-", episode_id="e2")
    assert g.believe("user", "haskids") == "ABSENT"
    assert g.ingest("user", "haskids", "children", episode_id="e3") is Action.SEED
    assert g.believe("user", "haskids") == "children"


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


def test_relation_canonicalisation():
    """Synonym relations must land in ONE slot and compete — else both stay 'current' (wrong)."""
    r = Resolver(aliases={"lives_in": "home_city", "resides_in": "home_city"})
    g = EvolvingGraph(resolver=r)
    g.ingest("user", "lives_in", "Beijing", episode_id="e1")
    g.ingest("user", "resides_in", "Shanghai", episode_id="e2")
    g.ingest("user", "resides_in", "Shanghai", episode_id="e3")     # supersedes via the shared slot
    assert g.believe("user", "home_city") == "Shanghai"
    assert g.believe("user", "lives_in") == "Shanghai"              # query via the alias resolves too


def test_entity_canonicalisation_enables_multihop():
    """'Apple' and 'Apple Inc.' must be one node or the chain (and multi-hop) breaks."""
    r = Resolver(aliases={"Apple Inc.": "Apple"})
    g = EvolvingGraph(resolver=r)
    g.ingest("Apple Inc.", "founded_by", "Jobs", episode_id="e1")
    g.ingest("Jobs", "born_in", "SF", episode_id="e2")
    assert g.hop("Apple", ["founded_by", "born_in"]) == ["SF"]
    assert g.believe("Apple Inc.", "founded_by") == "Jobs"


def test_fuzzy_resolver_merges_near_duplicates():
    """An injected similarity (stand-in for an embedding cosine) merges near-duplicate surface forms."""
    def norm(s):
        return s.lower().replace(".", "").replace(" ", "")

    def sim(a, b):
        return 1.0 if norm(a) == norm(b) else 0.0
    g = EvolvingGraph(resolver=Resolver(similarity=sim, threshold=0.9))
    g.ingest("Apple", "ceo", "Cook", episode_id="e1")
    g.ingest("apple.", "ceo", "Cook", episode_id="e2")              # near-dup subject -> merged
    ceo_edges = [e for e in g.beliefs() if e.relation == "ceo"]
    assert len(ceo_edges) == 1 and ceo_edges[0].subject == "Apple"


def test_event_time_onset():
    """Intervals stamp EVENT time (when it held), not ingestion order — needed for temporal QA."""
    g = EvolvingGraph()
    g.ingest("user", "home_city", "Beijing", episode_id="e1", t=2)  # "moved to Beijing in year 2"
    g.ingest("user", "employer", "Acme", episode_id="e2", t=7)      # "joined Acme in year 7"
    assert g.onset("user", "home_city", "Beijing") == 2
    assert g.onset("user", "employer", "Acme") == 7


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
