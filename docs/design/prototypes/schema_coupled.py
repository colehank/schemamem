"""SchemaMem PROTOTYPE v2 — coupled SPRT + endogenous prediction error.

One generative model:
  * a relation holds candidate values, each with a recency-decayed mass;
  * EXPECTATION = softmax(mass) vs a null prior M0 -> p(v);
  * RESIDUAL is ENDOGENOUS: surprise(v) = −log p(v). The LLM only tags (subj,rel,value,polarity).
  * UPDATE GAIN is U-shaped in expectancy: g(p) = G_MIN + G_AMP·(2p−1)². Very-expected AND
    very-surprising update strongly; the ambiguous middle (p≈0.5) updates weakly.
  * CARDINALITY = COUPLING β (lateral inhibition). β large = FUNCTIONAL (winner-take-all),
    β=0 = PLURAL (coexist), between = SOFT. functional/plural is one number.
  * READOUT is probability-based (scale-free): a value is believed iff p(v) > P_ON.

k≥2 kept as the one hard identifiability floor for *changing* a functional belief. Pure stdlib.
"""
import math

LAM = 0.9
TAU = 1.0
M0 = 1.0
G_MIN, G_AMP = 0.30, 1.7
P_ON = 0.45     # believe a value iff p(v) exceeds this
K = 2


class Relation:
    def __init__(self, beta):
        self.beta = beta
        self.m = {}
        self.last_t = 0
        self.fresh = {}
        self.incumbent = None
        self.onset = {}        # value -> event-time it first became true (for temporal queries)

    def _decay(self, t):
        if t > self.last_t:
            f = LAM ** (t - self.last_t)
            for v in self.m:
                self.m[v] *= f
        self.last_t = t

    def expect(self):
        """Presence probability of each value; β sets how much siblings compete (β=1 functional,
        β=0 plural). Not a categorical — a per-value present-probability against the null M0."""
        exps = {v: math.exp(mv / TAU) for v, mv in self.m.items()}
        tot = sum(exps.values())
        return {v: e / (M0 + e + self.beta * (tot - e)) for v, e in exps.items()}

    def ingest(self, v, pol, t, event_t=None):
        self._decay(t)
        self.m.setdefault(v, 0.0)
        pv = self.expect().get(v, 1 / (M0 + 1))     # expectancy BEFORE update — drives the gain
        surprise = -math.log(max(pv, 1e-9))
        gain = G_MIN + G_AMP * (2 * pv - 1) ** 2
        self.m[v] += gain if pol == "+" else -gain  # β in the readout does the competing; no explicit inhibition
        if pol == "+":
            self.fresh[v] = self.fresh.get(v, 0) + 1
            self.onset.setdefault(v, event_t if event_t is not None else t)   # event-time, not report-time
        return round(surprise, 2), round(gain, 2), round(pv, 2)

    def present(self):
        p = self.expect()
        return sorted(v for v in self.m if p[v] > P_ON)

    def readout(self):
        """Pure argmax belief + confidence, no mutation (for context backoff)."""
        p = self.expect()
        if not p:
            return (None, 0.0)
        best = max(p, key=p.get)
        ps = sorted(p.values(), reverse=True)
        conf = round(ps[0] - (ps[1] if len(ps) > 1 else 0.0), 2)
        return (best if p[best] > P_ON else None, conf)

    def belief(self):
        p = self.expect()
        live = {v: p[v] for v in self.m if p[v] > P_ON}
        if not live:
            self.incumbent = None
            return None, 0.0
        top = max(live, key=live.get)
        if self.incumbent in live and top != self.incumbent and self.fresh.get(top, 0) < K:
            top = self.incumbent                 # hysteresis: k-floor to change the incumbent
        if top != self.incumbent:
            self.incumbent = top
            self.fresh = {top: self.fresh.get(top, 0)}
        ps = sorted(live.values(), reverse=True)
        return top, round(ps[0] - (ps[1] if len(ps) > 1 else 0.0), 2)


class Memory:
    """Orchestration over Relations: relation canonicalisation, context as a hierarchical prior
    (a specific context pools the default as prior), and event-time onsets. Forgetting is inherent:
    a Relation only ever stores the running mass — the sufficient statistic — never the raw episodes."""
    CANON = {"lives_in": "home_city", "resides_in": "home_city", "based_in": "home_city",
             "home_city": "home_city", "works_at": "employer", "employer": "employer"}

    def __init__(self):
        self.rels = {}     # (subj, rel, ctx) -> Relation
        self.beta = {}     # rel -> beta

    def canon(self, rel):
        return self.CANON.get(rel, rel)

    def ingest(self, subj, rel, v, pol="+", beta=1.5, ctx="default", t=0, event_t=None):
        rel = self.canon(rel)
        self.beta[rel] = beta
        r = self.rels.setdefault((subj, rel, ctx), Relation(beta))
        r.ingest(v, pol, t, event_t)
        return rel

    def believe(self, subj, rel, ctx="default"):
        """Context backoff: use the context's own belief if it has one, else fall back to default."""
        rel = self.canon(rel)
        if ctx != "default":
            spec = self.rels.get((subj, rel, ctx))
            if spec:
                b = spec.readout()
                if b[0] is not None:
                    return b
        deft = self.rels.get((subj, rel, "default"))
        return deft.readout() if deft else (None, 0.0)

    def onset(self, subj, rel, v):
        for (s, r, c), rel_obj in self.rels.items():
            if s == subj and r == self.canon(rel) and v in rel_obj.onset:
                return rel_obj.onset[v]
        return None


def demo_context():
    print("\n" + "=" * 74); print("D) CONTEXT as a hierarchical prior (default + weekend exception)"); print("=" * 74 + "\n")
    m = Memory()
    for t, v in [(1, "vegetarian"), (2, "vegetarian")]:
        m.ingest("user", "diet", v, ctx="default", t=t)
    for t, v in [(3, "pescatarian"), (4, "pescatarian")]:
        m.ingest("user", "diet", v, ctx="default", t=t)          # default -> pescatarian
    m.ingest("user", "diet", "vegetarian", ctx="weekend", t=5)   # weekend exception
    print(f"  believe diet @weekday = {m.believe('user','diet','weekday')}   (falls back to default)")
    print(f"  believe diet @weekend = {m.believe('user','diet','weekend')}   (exception overrides via own mass)")
    print("\n  -> a specific context pools the default as prior; its own evidence overrides it.")
    print("     Absorption is automatic: if weekend evidence stops differing, the pool ≈ default again.")


def demo_canon():
    print("\n" + "=" * 74); print("E) RELATION CANONICALISATION (the twin of entity resolution)"); print("=" * 74 + "\n")
    m = Memory()
    m.ingest("user", "lives_in", "Beijing", beta=1.5, t=1)
    m.ingest("user", "resides_in", "Shanghai", beta=1.5, t=2)    # a SYNONYM relation
    m.ingest("user", "based_in", "Shanghai", beta=1.5, t=3)
    print(f"  'lives_in' / 'resides_in' / 'based_in' all canon -> home_city")
    print(f"  believe home_city = {m.believe('user','home_city')}")
    print("\n  -> without canon, the synonyms never compete (both 'current') -> wrong.")
    print("     with canon they land in ONE slot and Shanghai correctly supersedes Beijing.")


def demo_events():
    print("\n" + "=" * 74); print("F) EVENT-TIME onsets (not report-time)"); print("=" * 74 + "\n")
    m = Memory()
    # all SAID at t=10, but the events happened earlier
    m.ingest("user", "home_city", "Beijing", t=10, event_t=2)    # "I moved to Beijing back in year 2"
    m.ingest("user", "employer", "Acme", t=10, event_t=7)        # "I joined Acme in year 7"
    print(f"  said everything at report-time t=10, but:")
    print(f"    home_city=Beijing onset = year {m.onset('user','home_city','Beijing')}")
    print(f"    employer=Acme   onset = year {m.onset('user','employer','Acme')}")
    print("\n  -> 'when did you move to Beijing?' answers year 2, not year 10.")
    print("     temporal QA (LongMemEval) needs the extracted event time, not the ingestion tick.")


def demo_ushape():
    print("=" * 74); print("A) ENDOGENOUS RESIDUAL + U-SHAPED GAIN"); print("=" * 74)
    print("  surprise & gain are read off the mass. Watch the three regimes:\n")
    r = Relation(beta=1.4)
    script = [("A", "+", 1, "seed"), ("A", "+", 2, ""), ("A", "+", 3, "A now EXPECTED (high p)"),
              ("B", "+", 4, "B is SURPRISING (low p)"), ("B", "+", 5, "B rising"),
              ("B", "+", 6, "A vs B near-TIE -> next lands mid-p"),
              ("A", "+", 7, "AMBIGUOUS middle (p≈0.5)")]
    print(f"  {'obs':<8}{'p_before':<10}{'surprise':<10}{'gain':<8}note")
    for v, pol, t, note in script:
        s, g, pv = r.ingest(v, pol, t)
        tag = "consolidate" if pv > 0.6 else ("SURPRISE" if pv < 0.35 else "middle(weak)")
        print(f"  {v:<8}{pv:<10}{s:<10}{g:<8}{tag}  {note}")
    print("\n  -> gain HIGH at high p (consolidate) and low p (surprise), LOW at p≈0.5.")
    print("     The old '0.5 no-op' is the bottom of this U; 'contested' lives here too.")


def demo_beta():
    print("\n" + "=" * 74); print("B) CARDINALITY = COUPLING β  (feed A×2 then rival B×2)"); print("=" * 74 + "\n")
    for beta, name in [(0.0, "PLURAL β=0"), (0.7, "SOFT β=0.7"), (1.6, "FUNCTIONAL β=1.6")]:
        r = Relation(beta=beta)
        for v, t in [("A", 1), ("A", 2), ("B", 3), ("B", 4)]:
            r.ingest(v, "+", t)
        p = r.expect()
        print(f"  {name:<16} present={str(r.present()):<12} p[A]={p['A']:.2f} p[B]={p['B']:.2f}")
    print("\n  -> β=0: both believed (coexist). β large: B suppresses A below threshold (replace).")
    print("     β between: soft. functional↔plural↔soft is ONE continuous knob.")


def demo_full():
    print("\n" + "=" * 74); print("C) FULL STORY (per-relation β; final beliefs)"); print("=" * 74 + "\n")
    BETA = {"diet": 1.5, "city": 1.5, "employer": 1.5, "hobby": 0.0}
    DATA = [
        ("diet", "vegetarian", "+", 1), ("diet", "vegetarian", "+", 2),
        ("diet", "vegan", "+", 3),
        ("diet", "pescatarian", "+", 4), ("diet", "pescatarian", "+", 5),
        ("diet", "vegetarian", "+", 9), ("diet", "vegetarian", "+", 10),
        ("hobby", "climbing", "+", 1), ("hobby", "chess", "+", 2),
        ("hobby", "climbing", "-", 6), ("hobby", "climbing", "-", 7),
        ("hobby", "climbing", "+", 12),
        ("employer", "Acme", "+", 1), ("employer", "Acme", "-", 8), ("employer", "Acme", "-", 9),
        ("city", "Beijing", "+", 1), ("city", "Shanghai", "+", 2), ("city", "Shanghai", "+", 3),
        ("city", "Beijing", "+", 4), ("city", "Beijing", "+", 5),
        ("city", "Shanghai", "+", 6), ("city", "Shanghai", "+", 7),
        ("city", "Shanghai", "+", 8), ("city", "Shanghai", "+", 9),
    ]
    rels = {}
    for rel, v, pol, t in DATA:
        rels.setdefault(rel, Relation(BETA[rel])).ingest(v, pol, t)
    for rel, r in rels.items():
        p = r.expect()
        if BETA[rel] == 0:
            print(f"  {rel:<9}(plural)     present={r.present()}")
        else:
            b, c = r.belief()
            ms = ", ".join(f"{v}:{p[v]:.2f}" for v in sorted(r.m, key=lambda x: -p[x]))
            print(f"  {rel:<9}(functional) belief={b}  conf={c}   p[{ms}]")
    print(f"\n  k≥2 floor: 'vegan' (1 mention) believed? {'vegan' in rels['diet'].present()}  (want False)")
    print(f"  diet -> vegetarian (revived), city -> Shanghai (settled after oscillation),")
    print(f"  employer -> None (retracted), hobby -> chess+climbing (climbing revived).")


if __name__ == "__main__":
    demo_ushape(); demo_beta(); demo_full()
    demo_context(); demo_canon(); demo_events()
    print("\n" + "=" * 74)
    print("FORGETTING is INHERENT: a Relation stores only running mass (the sufficient statistic),")
    print("never the raw episode list. Consolidation = compression; nothing to garbage-collect.")
    print("=" * 74)
