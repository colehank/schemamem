"""SchemaMem frontier PROTOTYPE v3 — full model, iterated to a clean memory.

Fixes over v2:
  (3) CONTEXT is a fallback lattice: `default` is the fallback; a specific context
      only holds an edge while it DIFFERS from the default (an exception). When the
      default changes to match, the exception is ABSORBED. Queries fall back to default.
  (4) CONTESTED suspends BOTH contenders (no forced current); query returns UNRESOLVED.
  (5) negatives are k-gated too: one "not X" is tentative; k make it an asserted-absent belief.
Carried from v2: k counts FRESH evidence since the last state change; strength reads the window.
Pure stdlib, no LLM; residual/cardinality/polarity are given.
"""
from dataclasses import dataclass, field
from collections import defaultdict

K = 2
FLIP_MAX = 2
DEFAULT = "default"


@dataclass
class Edge:
    subj: str; rel: str; obj: str; ctx: str; card: str
    pos: set = field(default_factory=set)
    neg: set = field(default_factory=set)
    fpos: set = field(default_factory=set)
    fneg: set = field(default_factory=set)
    intervals: list = field(default_factory=list)
    absorbed: bool = False

    def is_current(self): return any(iv[1] is None for iv in self.intervals)
    def is_past(self):    return bool(self.intervals) and not self.is_current()
    def open_iv(self, t):
        if not self.is_current(): self.intervals.append([t, None])
    def close_iv(self, t):
        for iv in self.intervals:
            if iv[1] is None: iv[1] = t
    def strength(self):
        if self.is_current(): return max(1, min(5, len(self.fpos) + 1))
        return min(5, len(self.pos))
    def status(self, contested=False):
        if contested and (self.is_current() or self.fpos): return "CONTESTED"
        if self.absorbed and self.is_past(): return "ABSORBED"
        if self.is_current(): return "CURRENT"
        if self.is_past():    return "PAST"
        if len(self.neg) >= K and not self.pos: return "ABSENT"      # firm negative belief
        if self.pos:          return "PENDING"
        if self.neg:          return "tentative-"
        return "EMPTY"


class Memory:
    def __init__(self):
        self.edges = {}
        self.card_of = {}
        self.log = []
        self.flips = {}
        self.contested = set()

    def edge(self, subj, rel, obj, ctx, card):
        k = (subj, rel, obj, ctx)
        if k not in self.edges:
            self.edges[k] = Edge(subj, rel, obj, ctx, card)
        return self.edges[k]

    def slot_edges(self, subj, rel, ctx):
        return [e for e in self.edges.values()
                if (e.subj, e.rel, e.ctx) == (subj, rel, ctx) and e.card == "F"]

    def current_edge(self, subj, rel, ctx):
        return next((e for e in self.slot_edges(subj, rel, ctx) if e.is_current()), None)

    def default_val(self, subj, rel):
        e = self.current_edge(subj, rel, DEFAULT)
        return e.obj if e else None

    def _reset_slot(self, subj, rel, ctx, keep):
        for e in self.slot_edges(subj, rel, ctx):
            if e is not keep:
                e.fpos.clear(); e.fneg.clear()

    def _absorb_exceptions(self, subj, rel, t):
        """After the default belief changes, any specific-context exception that now
        equals the default is ABSORBED (the exception dissolved)."""
        dv = self.default_val(subj, rel)
        for e in self.edges.values():
            if (e.subj, e.rel) == (subj, rel) and e.ctx != DEFAULT and e.card == "F" \
               and e.is_current() and e.obj == dv:
                e.close_iv(t); e.absorbed = True

    def ingest(self, subj, rel, obj, card, pol, ctx, ep, t):
        self.card_of.setdefault(rel, card)
        e = self.edge(subj, rel, obj, ctx, card)
        was_past = e.is_past()
        (e.pos if pol == "+" else e.neg).add(ep)
        (e.fpos if pol == "+" else e.fneg).add(ep)
        act = "?"

        if card == "P":
            if pol == "+":
                if e.is_current():           act = "ASSIMILATE"
                elif was_past:               e.open_iv(t); e.fneg.clear(); act = "REVIVE"
                else:                        e.open_iv(t); e.fneg.clear(); act = "ACCRETE"
            else:
                if e.is_current() and len(e.fneg) >= K: e.close_iv(t); e.fpos.clear(); act = "RETRACT"
                elif e.is_current():         act = "incubate(retire?)"
                elif len(e.neg) >= K:        act = "ABSENT(asserted)"
                else:                        act = "tentative-absent"
        else:
            key = (subj, rel, ctx)
            cur = self.current_edge(subj, rel, ctx)
            if pol == "+":
                # specific context that merely restates the default is redundant
                if ctx != DEFAULT and cur is None and obj == self.default_val(subj, rel):
                    act = "redundant(=default)"
                elif key in self.contested:  act = "CONTESTED(hold)"
                elif cur is None:
                    e.open_iv(t); self._reset_slot(subj, rel, ctx, e)
                    act = "REVIVE" if was_past else "seed"
                    if ctx == DEFAULT: self._absorb_exceptions(subj, rel, t)
                elif cur is e:               act = "ASSIMILATE"
                elif len(e.fpos) >= K:
                    if self.flips.get(key, 0) >= FLIP_MAX:
                        self.contested.add(key); cur.close_iv(t); e.close_iv(t) if e.is_current() else None
                        act = "CONTESTED(detected)"
                    else:
                        cur.close_iv(t); e.open_iv(t); self._reset_slot(subj, rel, ctx, e)
                        self.flips[key] = self.flips.get(key, 0) + 1
                        act = "REVISE" + ("/REVIVE" if was_past else "")
                        if ctx == DEFAULT: self._absorb_exceptions(subj, rel, t)
                else:                        act = "INCUBATE"
            else:
                if cur is e and len(e.fneg) >= K:
                    e.close_iv(t); self._reset_slot(subj, rel, ctx, None); act = "RETRACT(->none)"
                elif cur is e:               act = "incubate(retire?)"
                elif len(e.neg) >= K:        act = "ABSENT(asserted)"
                else:                        act = "tentative-absent"

        self.log.append((t, f"{subj} {rel}={obj} [{pol}] @{ctx}", act))
        return act

    # --- queries -----------------------------------------------------------
    def believe(self, subj, rel, ctx=DEFAULT):
        if (subj, rel, DEFAULT) in self.contested or (subj, rel, ctx) in self.contested:
            return "UNRESOLVED(contested)"
        card = self.card_of.get(rel)
        if card == "P":
            return sorted({e.obj for e in self.edges.values()
                           if (e.subj, e.rel) == (subj, rel) and e.ctx in (ctx, DEFAULT) and e.is_current()})
        e = self.current_edge(subj, rel, ctx)
        if e: return e.obj
        if ctx != DEFAULT:
            d = self.current_edge(subj, rel, DEFAULT)
            if d: return f"{d.obj} (via default)"
        absent = [x for x in self.slot_edges(subj, rel, ctx) if x.status() == "ABSENT"]
        if absent: return f"no · asserted-absent ({absent[0].obj})"
        return "unknown"

    def hop(self, start, path):
        frontier = {start}
        for rel in path:
            frontier = {e.obj for e in self.edges.values()
                        if e.subj in frontier and e.rel == rel and e.is_current()}
        return sorted(frontier)


DATA = [
    # diet: seed, assimilate, one-off incubate, revise, context exception, revive, exception ABSORBED
    ("user", "diet", "vegetarian",  "F", "+", "default", "d1"),
    ("user", "diet", "vegetarian",  "F", "+", "default", "d2"),
    ("user", "diet", "vegan",       "F", "+", "default", "dX"),
    ("user", "diet", "pescatarian", "F", "+", "default", "d3"),
    ("user", "diet", "pescatarian", "F", "+", "default", "d4"),   # REVISE -> pescatarian
    ("user", "diet", "vegetarian",  "F", "+", "weekend", "d5"),   # exception: weekend veg (differs from pesc)
    ("user", "diet", "vegetarian",  "F", "+", "default", "d6"),   # 1 fresh -> INCUBATE
    ("user", "diet", "vegetarian",  "F", "+", "default", "d7"),   # 2 fresh -> REVISE/REVIVE; weekend ABSORBED

    # workmode: a conditional that SURVIVES (two contexts, no default) -> stays split
    ("user", "workmode", "office", "F", "+", "weekday", "w1"),
    ("user", "workmode", "home",   "F", "+", "weekend", "w2"),

    # hobby (plural): accrete, coexist, retract, revive
    ("user", "hobby", "climbing", "P", "+", "default", "h1"),
    ("user", "hobby", "chess",    "P", "+", "default", "h2"),
    ("user", "hobby", "climbing", "P", "-", "default", "h3"),
    ("user", "hobby", "climbing", "P", "-", "default", "h4"),     # RETRACT
    ("user", "hobby", "climbing", "P", "+", "default", "h5"),     # REVIVE

    # employer: retract to none
    ("user", "employer", "Acme", "F", "+", "default", "j1"),
    ("user", "employer", "Acme", "F", "-", "default", "j2"),
    ("user", "employer", "Acme", "F", "-", "default", "j3"),      # RETRACT -> none

    # city: sustained oscillation -> CONTESTED (both suspended)
    ("user", "city", "Beijing",  "F", "+", "default", "c1"),
    ("user", "city", "Shanghai", "F", "+", "default", "c2"),
    ("user", "city", "Shanghai", "F", "+", "default", "c3"),      # flip1 -> SH
    ("user", "city", "Beijing",  "F", "+", "default", "c4"),
    ("user", "city", "Beijing",  "F", "+", "default", "c5"),      # flip2 -> BJ
    ("user", "city", "Shanghai", "F", "+", "default", "c6"),
    ("user", "city", "Shanghai", "F", "+", "default", "c7"),      # flip3 -> CONTESTED

    # asserted-absent (k-gated): two "no kids" -> firm negative belief
    ("user", "haskids", "children", "F", "-", "default", "n1"),
    ("user", "haskids", "children", "F", "-", "default", "n2"),

    # multi-hop
    ("Nick", "coaches", "RSL", "F", "+", "default", "m1"),
    ("RSL", "plays_sport", "soccer", "F", "+", "default", "m2"),
]


def run():
    m = Memory()
    print("=" * 78)
    print("RUN LOG   (step | observation | action)")
    print("=" * 78)
    for t, (subj, rel, obj, card, pol, ctx, ep) in enumerate(DATA, 1):
        act = m.ingest(subj, rel, obj, card, pol, ctx, ep, t)
        print(f"{t:>2} | {subj:<5} {rel}={obj:<11} [{pol}] @{ctx:<7} | -> {act}")

    print("\n" + "=" * 78)
    print("FINAL MEMORY")
    print("=" * 78)
    grp = defaultdict(lambda: defaultdict(list))
    for e in m.edges.values():
        grp[e.subj][e.rel].append(e)
    for subj in sorted(grp):
        print(f"\n[{subj}]")
        for rel in sorted(grp[subj]):
            card = m.card_of[rel]
            print(f"  {rel}  ({'functional' if card=='F' else 'plural'})")
            for e in sorted(grp[subj][rel], key=lambda x: (x.status() not in ("CURRENT",), x.ctx, x.obj)):
                cont = (e.subj, e.rel, e.ctx) in m.contested
                iv = ", ".join(f"[{a}->{b if b is not None else 'now'}]" for a, b in e.intervals) or "—"
                print(f"      {e.status(cont):<10} {e.obj:<12} @{e.ctx:<8} "
                      f"str={e.strength()} +{len(e.pos)}/-{len(e.neg)} {iv}")

    print("\n" + "=" * 78)
    print("QUERIES  (what would we answer now)")
    print("=" * 78)
    q = [("user","diet","weekday"),("user","diet","weekend"),
         ("user","workmode","weekday"),("user","workmode","weekend"),
         ("user","hobby","default"),("user","employer","default"),
         ("user","city","default"),("user","haskids","default")]
    for s,r,c in q:
        print(f"  believe({s}, {r}, @{c}) = {m.believe(s,r,c)}")
    print(f"  hop(Nick,[coaches,plays_sport]) = {m.hop('Nick',['coaches','plays_sport'])}")

    print("\n" + "=" * 78)
    print("DIAGNOSTICS")
    print("=" * 78)
    print(f"  contested slots : {sorted(m.contested) or 'none'}")
    print(f"  flips per slot  : { {k[0]+'.'+k[1]+'@'+k[2]: v for k,v in m.flips.items()} }")
    ctxs = defaultdict(set)
    for e in m.edges.values():
        if e.is_current(): ctxs[(e.subj, e.rel)].add(e.ctx)
    overlap = [(s,r,sorted(cs)) for (s,r),cs in ctxs.items() if DEFAULT in cs and len(cs) > 1]
    print(f"  ctx overlaps    : {overlap or 'none (default/exception cleanly separated)'}")


if __name__ == "__main__":
    run()
