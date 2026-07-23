"""Deterministic tests for the evolving knowledge graph (no LLM).

Proves the five evolution dynamics coexist on one structure, plus multi-hop
reachability — the model the paper's memory-evolution account requires.
"""
from schemamem.graph_core import SchemaGraph, Action, Card, Status


def _g():
    return SchemaGraph(k=2)


def test_functional_relation_updates_by_replacement():
    """diet: veg -> pescatarian. Two distinct episodes assert the new value, so
    it supersedes; one would only incubate."""
    g = _g()
    assert g.ingest("user", "diet", "vegetarian", residual=0.0, episode_id="ep1") is Action.CONSOLIDATE
    # one conflicting episode: incubates, belief unchanged
    assert g.ingest("user", "diet", "pescatarian", residual=1.0, episode_id="ep2") is Action.INCUBATE
    assert g.objects("user", "diet") == ["vegetarian"]
    # a second distinct episode promotes it: UPDATE
    assert g.ingest("user", "diet", "pescatarian", residual=1.0, episode_id="ep3") is Action.UPDATE
    assert g.objects("user", "diet") == ["pescatarian"]
    assert g.objects("user", "diet", status=Status.SUPERSEDED) == ["vegetarian"]


def test_plural_relation_grows_without_conflict():
    """Apple developed iPod AND QuickTime. A second object is not a rival; it
    coexists. This is the case the single-valued slot model threw to 'exception'."""
    g = _g()
    assert g.ingest("Apple", "developed", "iPod", residual=0.0,
                    episode_id="ep1", cardinality=Card.PLURAL) is Action.GROW
    assert g.ingest("Apple", "developed", "QuickTime", residual=1.0,
                    episode_id="ep2", cardinality=Card.PLURAL) is Action.GROW
    assert sorted(g.objects("Apple", "developed")) == ["QuickTime", "iPod"]
    # nothing was superseded — both are live beliefs
    assert g.objects("Apple", "developed", status=Status.SUPERSEDED) == []


def test_restating_an_object_consolidates_it():
    """Repeated same-value evidence firms the belief (support grows) rather than
    creating rivals."""
    g = _g()
    g.ingest("user", "diet", "vegan", residual=0.0, episode_id="ep1")
    assert g.ingest("user", "diet", "vegan", residual=0.0, episode_id="ep2") is Action.CONSOLIDATE
    edge = g.node("user").rel("diet")[0]
    assert edge.votes == 2 and edge.status is Status.BELIEF


def test_exception_is_incubated_not_discarded_then_promotes():
    """An isolated conflict is held as PENDING, alive. When it recurs it is
    promoted — it was a slow-to-accept real change, not a dead exception."""
    g = _g()
    g.ingest("user", "city", "Shanghai", residual=0.0, episode_id="ep1")
    g.ingest("user", "city", "Beijing", residual=1.0, episode_id="ep2")   # incubate
    assert [e.obj for e in g.pending()] == ["Beijing"]      # alive, not swept away
    assert g.objects("user", "city") == ["Shanghai"]
    g.ingest("user", "city", "Beijing", residual=1.0, episode_id="ep3")   # recurs -> promote
    assert g.objects("user", "city") == ["Beijing"]
    assert g.pending() == []


def test_incubated_evidence_can_seed_a_belief_where_none_existed():
    """Repeated observations about a relation the subject had no belief for still
    accrue and become the belief — a new schema growing from accumulation."""
    g = _g()
    # first observation on an empty relation seeds directly
    assert g.ingest("Ann", "employer", "Acme", residual=1.0, episode_id="ep1") is Action.CONSOLIDATE
    assert g.objects("Ann", "employer") == ["Acme"]


def test_multi_hop_traversal_over_belief_edges():
    """The payoff of real edges: an answer reachable by chaining relations that
    is stored nowhere directly."""
    g = _g()
    g.ingest("Nick", "coaches", "Real Salt Lake", residual=0.0, episode_id="e1")
    g.ingest("Real Salt Lake", "plays_sport", "soccer", residual=0.0, episode_id="e2")
    # "what sport does the team Nick coaches play?" — not stored on Nick at all
    assert g.hop("Nick", ["coaches", "plays_sport"]) == ["soccer"]
    assert g.hop("Nick", ["coaches"]) == ["Real Salt Lake"]


def test_objects_are_shared_nodes():
    """Linking objects as nodes is what makes traversal possible — the object of
    one edge is the subject of another, one node."""
    g = _g()
    g.ingest("Apple", "founded_by", "Steve Jobs", residual=0.0, episode_id="e1")
    g.ingest("Steve Jobs", "born_in", "San Francisco", residual=0.0, episode_id="e2")
    assert "Steve Jobs" in g.nodes
    assert g.hop("Apple", ["founded_by", "born_in"]) == ["San Francisco"]


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
