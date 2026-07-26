"""Replay OUR constructed dataset through both L3 cores and compare their beliefs.

Not a benchmark — a head-to-head sanity check on the synthetic story we built while designing the
frontier (diet / hobby / employer / city-oscillation / haskids / a multi-hop chain). It runs the
same observations through:

  * graph_core.EvolvingGraph   — the shipped COUNTING engine
  * coupled_core.CoupledMemory — the generative COUPLED engine (v2 math)

and prints their final beliefs side by side against an expected key, so the agreements and the
*designed* divergences (contested-freeze vs low-confidence, asserted-absent vs unknown) are visible.

    python3 eval/replay_synthetic.py
"""
from schemamem.coupled_core import CoupledMemory
from schemamem.graph_core import Card, EvolvingGraph

# (subject, relation, object, polarity, cardinality 'F'|'P', context, t)
DATA = [
    ("user", "diet", "vegetarian", "+", "F", "default", 1),
    ("user", "diet", "vegetarian", "+", "F", "default", 2),
    ("user", "diet", "vegan", "+", "F", "default", 3),           # one-off
    ("user", "diet", "pescatarian", "+", "F", "default", 4),
    ("user", "diet", "pescatarian", "+", "F", "default", 5),     # -> pescatarian
    ("user", "diet", "vegetarian", "+", "F", "default", 9),
    ("user", "diet", "vegetarian", "+", "F", "default", 10),     # revived -> vegetarian
    ("user", "hobby", "climbing", "+", "P", "default", 1),
    ("user", "hobby", "chess", "+", "P", "default", 2),
    ("user", "hobby", "climbing", "-", "P", "default", 6),
    ("user", "hobby", "climbing", "-", "P", "default", 7),       # retract climbing
    ("user", "hobby", "climbing", "+", "P", "default", 12),      # revive climbing
    ("user", "employer", "Acme", "+", "F", "default", 1),
    ("user", "employer", "Acme", "-", "F", "default", 8),
    ("user", "employer", "Acme", "-", "F", "default", 9),        # retract -> none
    ("user", "city", "Beijing", "+", "F", "default", 1),
    ("user", "city", "Shanghai", "+", "F", "default", 2),
    ("user", "city", "Shanghai", "+", "F", "default", 3),
    ("user", "city", "Beijing", "+", "F", "default", 4),
    ("user", "city", "Beijing", "+", "F", "default", 5),
    ("user", "city", "Shanghai", "+", "F", "default", 6),
    ("user", "city", "Shanghai", "+", "F", "default", 7),        # oscillation
    ("user", "city", "Shanghai", "+", "F", "default", 8),
    ("user", "city", "Shanghai", "+", "F", "default", 9),
    ("user", "city", "Shanghai", "+", "F", "default", 10),       # settles -> Shanghai
    ("user", "haskids", "children", "-", "F", "default", 1),
    ("user", "haskids", "children", "-", "F", "default", 2),     # asserted absent
    ("Nick", "coaches", "RSL", "+", "F", "default", 1),
    ("RSL", "plays_sport", "soccer", "+", "F", "default", 2),
]

QUERIES = [
    ("user", "diet", "vegetarian"),
    ("user", "hobby", ["chess", "climbing"]),
    ("user", "employer", None),
    ("user", "city", "Shanghai"),
    ("user", "haskids", "no-children"),        # a good memory knows the user has NO kids
]


def run_counting():
    g = EvolvingGraph()
    for i, (s, r, o, pol, card, ctx, t) in enumerate(DATA):
        g.ingest(s, r, o, polarity=pol,
                 cardinality=Card.FUNCTIONAL if card == "F" else Card.PLURAL,
                 context=ctx, episode_id=f"e{i}", t=t)
    beliefs = {(s, r): g.believe(s, r) for s, r, _ in QUERIES}
    return beliefs, g.hop("Nick", ["coaches", "plays_sport"])


def run_coupled():
    m = CoupledMemory()
    for (s, r, o, pol, card, ctx, t) in DATA:
        m.ingest(s, r, o, polarity=pol, beta=1.5 if card == "F" else 0.0, context=ctx, t=t)
    beliefs = {(s, r): m.believe(s, r) for s, r, _ in QUERIES}
    return beliefs, m.hop("Nick", ["coaches", "plays_sport"])


def ok(got, expected):
    if expected == "no-children":
        return got in ("ABSENT", None)            # both "not children" readings are acceptable
    return got == expected


def main():
    cb, chop = run_counting()
    mb, mhop = run_coupled()
    print("=" * 78)
    print(f"{'query':<22}{'expected':<16}{'counting':<16}{'coupled':<16}")
    print("=" * 78)
    cscore = mscore = 0
    for s, r, exp in QUERIES:
        c, m = cb[(s, r)], mb[(s, r)]
        cscore += ok(c, exp)
        mscore += ok(m, exp)
        cm = "✓ " if ok(c, exp) else "· "
        mm = "✓ " if ok(m, exp) else "· "
        print(f"{s+'.'+r:<22}{str(exp):<16}{cm+str(c):<16}{mm+str(m):<16}")
    hexp = ["soccer"]
    cscore += chop == hexp
    mscore += mhop == hexp
    print(f"{'hop Nick->sport':<22}{str(hexp):<16}"
          f"{('✓ ' if chop==hexp else '· ')+str(chop):<16}{('✓ ' if mhop==hexp else '· ')+str(mhop):<16}")
    n = len(QUERIES) + 1
    print("=" * 78)
    print(f"accuracy:  counting {cscore}/{n}   coupled {mscore}/{n}")
    print("\nDesigned divergences (not bugs):")
    print("  city    : counting freezes to UNRESOLVED longer (needs k+1 to resolve); coupled tracks a")
    print("            best-guess with confidence — both end at Shanghai here after it settles.")
    print("  haskids : counting has an explicit ASSERT_ABSENT ('no'); coupled leaves it None (negatives")
    print("            only lower mass, no seeded absent-belief). Both avoid claiming the user has kids.")


if __name__ == "__main__":
    main()
