"""Tests for the generative core (coupled competition + endogenous residual), no LLM.

Checks that the same dynamics as the counting engine hold as *readings of masses* — seed /
consolidate / k-gated change / plural coexist+retract / functional replace via β / context
backoff / resolution / event-time — plus that the endogenous residual and U-shaped gain behave.
"""
from schemamem.coupled_core import CoupledMemory, MassRelation
from schemamem.graph_core import Resolver

F, P = 1.5, 0.0     # functional / plural β


def test_seed_consolidate_and_k_gate():
    m = CoupledMemory()
    m.ingest("user", "diet", "vegetarian", beta=F, t=1)
    m.ingest("user", "diet", "vegetarian", beta=F, t=2)
    assert m.believe("user", "diet") == "vegetarian"
    # one conflicting mention must NOT flip a standing belief (k≥2 floor)
    m.ingest("user", "diet", "pescatarian", beta=F, t=3)
    assert m.believe("user", "diet") == "vegetarian"


def test_functional_revise():
    m = CoupledMemory()
    for t, v in [(1, "vegetarian"), (2, "vegetarian"), (3, "pescatarian"), (4, "pescatarian")]:
        m.ingest("user", "diet", v, beta=F, t=t)
    assert m.believe("user", "diet") == "pescatarian"


def test_plural_coexist_and_retract():
    m = CoupledMemory()
    m.ingest("user", "hobby", "climbing", beta=P, t=1)
    m.ingest("user", "hobby", "chess", beta=P, t=2)
    assert m.believe("user", "hobby") == ["chess", "climbing"]          # coexist (β=0)
    m.ingest("user", "hobby", "climbing", polarity="-", beta=P, t=3)
    m.ingest("user", "hobby", "climbing", polarity="-", beta=P, t=4)
    assert m.believe("user", "hobby") == ["chess"]                      # climbing retracted, chess stays


def test_cardinality_is_one_knob_beta():
    """Same conflict (A×2 then B×2): β=0 keeps both, large β lets B replace A."""
    plural = CoupledMemory()
    functional = CoupledMemory()
    for t, v in [(1, "A"), (2, "A"), (3, "B"), (4, "B")]:
        plural.ingest("x", "r", v, beta=P, t=t)
        functional.ingest("x", "r", v, beta=2.0, t=t)
    assert plural.believe("x", "r") == ["A", "B"]
    assert functional.believe("x", "r") == "B"


def test_context_backoff():
    m = CoupledMemory()
    for t, v in [(1, "vegetarian"), (2, "vegetarian"), (3, "pescatarian"), (4, "pescatarian")]:
        m.ingest("user", "diet", v, beta=F, t=t)                       # default -> pescatarian
    m.ingest("user", "diet", "vegetarian", beta=F, context="weekend", t=5)
    assert m.believe("user", "diet", "weekday") == "pescatarian"       # falls back to default
    assert m.believe("user", "diet", "weekend") == "vegetarian"        # exception overrides


def test_relation_resolution_and_multihop():
    r = Resolver(aliases={"lives_in": "home_city", "resides_in": "home_city", "Apple Inc.": "Apple"})
    m = CoupledMemory(resolver=r)
    m.ingest("user", "lives_in", "Beijing", beta=F, t=1)
    m.ingest("user", "resides_in", "Shanghai", beta=F, t=2)
    m.ingest("user", "resides_in", "Shanghai", beta=F, t=3)
    assert m.believe("user", "home_city") == "Shanghai"                # synonyms compete in one slot
    m.ingest("Apple Inc.", "founded_by", "Jobs", beta=F, t=1)
    m.ingest("Jobs", "born_in", "SF", beta=F, t=2)
    assert m.hop("Apple", ["founded_by", "born_in"]) == ["SF"]


def test_event_time_onset():
    m = CoupledMemory()
    m.ingest("user", "home_city", "Beijing", beta=F, t=10, event_t=2)
    assert m.onset("user", "home_city", "Beijing") == 2                # event time, not report time


def test_endogenous_residual_and_u_shaped_gain():
    """Residual is read off the mass; gain is smallest at p≈0.5, larger toward both extremes."""
    r = MassRelation(beta=1.4)
    for t in (1, 2, 3):
        r.ingest("A", "+", t)                                            # A becomes expected
    s_expected, g_expected = r.ingest("A", "+", 4)                        # high p -> consolidate
    s_surprise, g_surprise = r.ingest("B", "+", 5)                        # low p -> surprise
    assert s_surprise > s_expected                                       # surprising has higher residual
    assert g_surprise > g_expected                                       # and a larger update gain


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
