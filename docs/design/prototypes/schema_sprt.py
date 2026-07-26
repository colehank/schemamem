"""SchemaMem PROTOTYPE — the SPRT / evidence-mass core.

Replaces the pile of counters+thresholds (k, flip_max, k+1, contested-freeze, the
strength hack) with ONE quantity and ONE decision:

    mass_i(t) = Σ_{e ⊢+ i} λ^(t−t_e)  −  Σ_{e ⊢− i} λ^(t−t_e)      (recency-weighted evidence)

Functional slot: the incumbent is sticky; a challenger b overturns iff
    (identifiability)  it has ≥ k distinct FRESH positive episodes since the last change, AND
    (dominance)        mass_b(t) > mass_incumbent(t).
No θ hysteresis needed — strength resists change through the incumbent's mass magnitude.

What EMERGES instead of being hand-coded:
  * k≥2  — a 1-episode challenger fails the identifiability test (kept) AND its mass rarely
           beats a live incumbent; the floor is the only hard constant.
  * CONTESTED / RESOLVE / flip_max / k+1  — GONE. Replaced by a continuous
    confidence = mass(top1) − mass(top2). Oscillation -> low confidence (masses stay close);
    settling -> confidence rises. The slot always has a best guess, flagged unstable when close.
  * "strength resists change" (Ortiz-Tudela) — automatic: a well-reinforced incumbent has high
    mass, so a challenger needs more recent evidence to exceed it.

Only two constants remain: λ (recency) and k (identifiability floor). Pure stdlib.
"""
import math

LAM = 0.85   # recency decay per tick
K = 2        # identifiability floor: distinct fresh episodes to declare a *change*


class Slot:
    """A functional (subj,rel,ctx) slot: competing candidate values by mass."""
    def __init__(self):
        self.pos = {}          # obj -> list[t]
        self.neg = {}          # obj -> list[t]
        self.incumbent = None
        self.last_change = -1
        self.last_t = -1       # most recent evidence in this slot (dormancy must NOT decay confidence)
        self.history = []      # (obj, t_from, t_to)

    def volatility(self, window=6):
        """How many times the winner changed in the recent window — the continuous stand-in for
        the old flip_max/contested machinery. High = unstable."""
        return sum(1 for h in self.history if h[1] > self.last_t - window) - 1

    def mass(self, obj, now):
        p = sum(LAM ** (now - t) for t in self.pos.get(obj, []))
        n = sum(LAM ** (now - t) for t in self.neg.get(obj, []))
        return p - n

    def fresh_pos(self, obj):
        return sum(1 for t in self.pos.get(obj, []) if t > self.last_change)

    def fresh_neg(self, obj):
        return sum(1 for t in self.neg.get(obj, []) if t > self.last_change)

    def confidence(self, now):
        masses = sorted((self.mass(o, now) for o in self.pos), reverse=True)
        if not masses:
            return 0.0
        top1 = masses[0]
        top2 = masses[1] if len(masses) > 1 else 0.0
        return round(top1 - top2, 2)

    def ingest(self, obj, pol, ep, t):
        (self.pos if pol == "+" else self.neg).setdefault(obj, []).append(t)
        self.last_t = t
        if pol == "+":
            if self.incumbent is None:
                self._set(obj, t)
                return "SEED"
            if obj == self.incumbent:
                return "ASSIMILATE"
            if self.fresh_pos(obj) >= K and self.mass(obj, t) > self.mass(self.incumbent, t):
                revive = any(h[0] == obj for h in self.history)
                self._close(t)
                self._set(obj, t)
                return "REVIVE" if revive else "REVISE"
            return "INCUBATE"
        # negative
        if obj == self.incumbent and self.fresh_neg(obj) >= K and self.mass(obj, t) < 0:
            self._close(t)
            self.incumbent = None
            self.last_change = t
            return "RETRACT"
        return "INCUBATE" if obj == self.incumbent else "NOOP"

    def _set(self, obj, t):
        self.incumbent = obj
        self.last_change = t
        self.history.append([obj, t, None])

    def _close(self, t):
        for h in self.history:
            if h[2] is None:
                h[2] = t


class PluralRel:
    """A plural (subj,rel) relation: each member is an independent present/absent SPRT."""
    def __init__(self):
        self.pos = {}
        self.neg = {}
        self.present = {}     # obj -> bool
        self.since = {}       # obj -> t of last transition

    def mass(self, obj, now):
        p = sum(LAM ** (now - t) for t in self.pos.get(obj, []))
        n = sum(LAM ** (now - t) for t in self.neg.get(obj, []))
        return p - n

    def fresh(self, store, obj):
        return sum(1 for t in store.get(obj, []) if t > self.since.get(obj, -1))

    def ingest(self, obj, pol, ep, t):
        (self.pos if pol == "+" else self.neg).setdefault(obj, []).append(t)
        cur = self.present.get(obj, False)
        if pol == "+":
            if cur:
                return "ASSIMILATE"
            revive = obj in self.since
            self.present[obj] = True
            self.since[obj] = t
            return "REVIVE" if revive else "ACCRETE"
        # negative
        if cur and self.fresh(self.neg, obj) >= K and self.mass(obj, t) < 0:
            self.present[obj] = False
            self.since[obj] = t
            return "RETRACT"
        return "INCUBATE" if cur else "NOOP"

    def members(self, now):
        return sorted(o for o, p in self.present.items() if p)


class Memory:
    def __init__(self):
        self.fslots = {}     # (subj,rel,ctx) -> Slot
        self.prels = {}      # (subj,rel) -> PluralRel
        self.card = {}
        self.log = []

    def ingest(self, subj, rel, obj, pol="+", card="F", ctx="default", ep=None, t=0):
        self.card.setdefault(rel, card)
        if card == "P":
            pr = self.prels.setdefault((subj, rel), PluralRel())
            act = pr.ingest(obj, pol, ep, t)
        else:
            sl = self.fslots.setdefault((subj, rel, ctx), Slot())
            act = sl.ingest(obj, pol, ep, t)
        self.log.append((t, f"{subj} {rel}={obj}[{pol}]@{ctx}", act))
        return act

    def believe(self, subj, rel, ctx="default", now=999):
        if self.card.get(rel) == "P":
            pr = self.prels.get((subj, rel))
            return pr.members(now) if pr else []
        sl = self.fslots.get((subj, rel, ctx))
        if not sl or sl.incumbent is None:
            return None
        return (sl.incumbent, sl.confidence(now))


DATA = [
    ("user","diet","vegetarian","+","F","default","d1",1),
    ("user","diet","vegetarian","+","F","default","d2",2),
    ("user","diet","vegan","+","F","default","dX",3),        # one-off -> incubate
    ("user","diet","pescatarian","+","F","default","d3",4),
    ("user","diet","pescatarian","+","F","default","d4",5),  # -> revise
    ("user","diet","vegetarian","+","F","default","d6",9),   # 1 fresh -> incubate
    ("user","diet","vegetarian","+","F","default","d7",10),  # 2 fresh -> revive
    ("user","hobby","climbing","+","P","default","h1",1),
    ("user","hobby","chess","+","P","default","h2",2),
    ("user","hobby","climbing","-","P","default","h3",6),
    ("user","hobby","climbing","-","P","default","h4",7),    # retract
    ("user","hobby","climbing","+","P","default","h5",12),   # revive
    ("user","employer","Acme","+","F","default","j1",1),
    ("user","employer","Acme","-","F","default","j2",8),
    ("user","employer","Acme","-","F","default","j3",9),     # retract to none
    # city: oscillation then settling — watch CONFIDENCE, not a frozen state
    ("user","city","Beijing","+","F","default","c1",1),
    ("user","city","Shanghai","+","F","default","c2",2),
    ("user","city","Shanghai","+","F","default","c3",3),     # -> SH
    ("user","city","Beijing","+","F","default","c4",4),
    ("user","city","Beijing","+","F","default","c5",5),      # -> BJ
    ("user","city","Shanghai","+","F","default","c6",6),
    ("user","city","Shanghai","+","F","default","c7",7),     # -> SH (low confidence!)
    ("user","city","Shanghai","+","F","default","c8",8),
    ("user","city","Shanghai","+","F","default","c9",9),     # settles: confidence rises
    ("Nick","coaches","RSL","+","F","default","m1",1),
    ("RSL","plays_sport","soccer","+","F","default","m2",2),
]


def run():
    m = Memory()
    print("="*72); print("RUN LOG"); print("="*72)
    city_traj = []
    for (subj, rel, obj, pol, card, ctx, ep, t) in DATA:
        act = m.ingest(subj, rel, obj, pol, card, ctx, ep, t)
        print(f"t{t:>2} | {subj:<5} {rel}={obj:<11}[{pol}] | -> {act}")
        if rel == "city":
            sl = m.fslots[("user","city","default")]
            city_traj.append((t, sl.incumbent, sl.confidence(t)))

    print("\n"+"="*72); print("FINAL BELIEFS  (functional: value + confidence @ last evidence)"); print("="*72)
    for (subj, rel, ctx), sl in m.fslots.items():
        now = sl.last_t                       # evaluate at last evidence — dormancy doesn't decay conf
        cands = ", ".join(f"{o}:{sl.mass(o,now):+.2f}" for o in sl.pos)
        inc = sl.incumbent if sl.incumbent else "—(none)"
        conf = sl.confidence(now); vol = sl.volatility()
        flag = "  ⚠ UNSTABLE" if (sl.incumbent and vol >= 2) else ""
        print(f"  {subj}.{rel}@{ctx}: {inc}  conf={conf}  volatility={vol}{flag}")
        print(f"      masses: {cands}")
    for (subj, rel), pr in m.prels.items():
        print(f"  {subj}.{rel} (plural): {pr.members(999)}")

    print("\n"+"="*72); print("CITY TRAJECTORY  (confidence replaces contested/resolve)"); print("="*72)
    for t, inc, conf in city_traj:
        bar = "█" * int(max(0, conf) * 6)
        print(f"  t{t:>2}: best={inc:<9} conf={conf:>5}  {bar}")

    print("\n"+"="*72); print("EMERGENCE CHECKS"); print("="*72)
    diet = m.fslots[("user","diet","default")]
    print(f"  k≥2 floor holds?  vegan(1 ep) stayed non-belief: {'vegan' not in [h[0] for h in diet.history]}")
    print(f"  diet ends at:     {diet.incumbent}  (veg -> pesc -> veg revived)")
    print(f"  contested state?  NONE — city is just low-confidence, still answerable")
    print(f"  parameters used:  λ={LAM}, k={K}   (flip_max / k+1 / contested-freeze all GONE)")


if __name__ == "__main__":
    run()
