"""SchemaMem L3 core, the FRONTIER model: an evolving belief graph.

Where ``core.py`` holds a per-entity set of single-valued slots, this module makes
memory a graph of typed relations whose **edges carry evolving belief**. Each edge is
fully described by four things — the discrete "status" is a *reading* of them, never a
stored field:

    value      : (subject, relation, object)
    cardinality: FUNCTIONAL (one object at a time) | PLURAL (many coexist)
    evidence   : the distinct episodes backing it, each with a polarity (+ present / − absent)
    intervals  : the validity periods [from, to) it held; open = current, multiple = revived
    context    : the tag under which it holds ("default" is the fallback; specific tags override)

One signal drives everything — the **prediction residual**, i.e. how far a new observation
departs from what the relation currently expects. Here the residual is *structural*: a positive
observation whose object equals the current belief is residual≈0; a different object is a
conflict. (In the full system an LLM canonicalises objects and supplies polarity + cardinality;
this module is deterministic and LLM-free, like ``core.py``.) The residual is routed by two
structural properties — the relation's **cardinality** and the observation's **polarity** — and
gated by the **k≥2 identifiability floor**, producing the schema-evolution actions:

    SEED / ASSIMILATE ....... tuning: seed a first value, or firm an existing belief (residual≈0)
    ACCRETE ................. accretion: a new coexisting object of a PLURAL relation
    REVISE .................. accommodation: a FUNCTIONAL rival reaches k → supersede (old interval closes)
    RETRACT ................. accommodation: negative evidence reaches k → the belief goes absent (no successor)
    INCUBATE ................ a conflict below k, held alive and promotable (pre-restructuring)
    REVIVE .................. a past belief reopens (savings — no relearning from scratch)
    CONTESTED ............... a slot that oscillates past ``flip_max`` is suspended (unresolved, no forced winner)

Two invariants that make the memory *sound*, learned from running it on a broad dataset:

  * **Fresh evidence.** k counts episodes accrued *since the belief last changed*, not all-time.
    Otherwise any once-held value re-wins on a single mention (stale votes) and functional slots
    thrash. Counters ``fpos`` / ``fneg`` are the fresh sets; they reset on every state change.
  * **Never delete.** Superseded, retracted and absorbed beliefs keep their (closed) intervals —
    they are queryable history and can REVIVE. Extinction is not erasure.

Context is a fallback lattice: a specific-context edge only holds while it *differs* from the
default belief (an exception); when the default changes to match it, the exception is ABSORBED.
Queries fall back from a specific context to the default.

No LLM here. Deterministic and unit-tested, like ``core.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

DEFAULT = "default"


class Card(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"   # one object holds at a time (diet, city)
    PLURAL = "PLURAL"           # many objects coexist (hobby, developed)


class Action(str, Enum):
    SEED = "SEED"               # first value of a functional relation (nothing to protect)
    ASSIMILATE = "ASSIMILATE"   # restates an existing belief; support firms
    ACCRETE = "ACCRETE"         # a new coexisting object of a plural relation
    INCUBATE = "INCUBATE"       # a conflict below k; held pending, alive
    REVISE = "REVISE"           # a functional rival reached k; supersede the incumbent
    RETRACT = "RETRACT"         # negative evidence reached k; belief goes absent (no successor)
    REVIVE = "REVIVE"           # a past belief reopens (savings)
    CONTESTED = "CONTESTED"     # slot oscillated too much; suspended (unresolved)
    ASSERT_ABSENT = "ASSERT_ABSENT"  # negatives on a never-held object reached k (a firm "no")
    REDUNDANT = "REDUNDANT"     # a specific-context restatement of the default; not stored separately
    NOOP = "NOOP"               # weak signal below threshold; recorded, no state change


@dataclass
class Edge:
    """One (subject) --relation--> (object) belief, under a context, carrying evidence + timeline.

    ``pos`` / ``neg`` are the all-time distinct episodes (history); ``fpos`` / ``fneg`` are the
    FRESH episodes since the last state change (what the k-gate actually counts).
    """
    subject: str
    relation: str
    obj: str
    ctx: str = DEFAULT
    card: Card = Card.FUNCTIONAL
    pos: set = field(default_factory=set)
    neg: set = field(default_factory=set)
    fpos: set = field(default_factory=set)
    fneg: set = field(default_factory=set)
    intervals: list = field(default_factory=list)  # [[from, to]], to=None => open/current
    absorbed: bool = False

    def is_current(self) -> bool:
        return any(iv[1] is None for iv in self.intervals)

    def is_past(self) -> bool:
        return bool(self.intervals) and not self.is_current()

    def open_interval(self, t) -> None:
        if not self.is_current():
            self.intervals.append([t, None])

    def close_interval(self, t) -> None:
        for iv in self.intervals:
            if iv[1] is None:
                iv[1] = t

    @property
    def strength(self) -> int:
        """Confidence 0..5, read from the *current window* — historical negatives do not
        drag a revived belief down."""
        if self.is_current():
            return max(1, min(5, len(self.fpos) + 1))
        return min(5, len(self.pos))

    def status(self, contested: bool = False) -> str:
        if contested and (self.is_current() or self.fpos):
            return "CONTESTED"
        if self.absorbed and self.is_past():
            return "ABSORBED"
        if self.is_current():
            return "CURRENT"
        if self.is_past():
            return "PAST"
        if len(self.neg) >= 2 and not self.pos:
            return "ABSENT"
        if self.pos:
            return "PENDING"
        if self.neg:
            return "tentative-absent"
        return "EMPTY"


class EvolvingGraph:
    """The frontier belief graph and its per-relation arbitration engine.

    k        : distinct FRESH episodes needed to change a standing belief (identifiability floor).
    flip_max : after this many supersessions in one slot, a further overturn marks it CONTESTED.
    """

    def __init__(self, k: int = 2, flip_max: int = 2):
        self.k = k
        self.flip_max = flip_max
        self.edges: dict = {}          # (subject, relation, obj, ctx) -> Edge
        self.card_of: dict = {}        # relation -> declared cardinality
        self.flips: dict = {}          # (subject, relation, ctx) -> supersession count
        self.contested: set = set()    # {(subject, relation, ctx)}
        self._clock: int = 0           # monotonic tick; the fallback timestamp for intervals

    # -- structure -----------------------------------------------------------
    def edge(self, subject, relation, obj, ctx, card) -> Edge:
        key = (subject, relation, obj, ctx)
        if key not in self.edges:
            self.edges[key] = Edge(subject, relation, obj, ctx, card)
        return self.edges[key]

    def _slot(self, subject, relation, ctx) -> list:
        return [e for e in self.edges.values()
                if (e.subject, e.relation, e.ctx) == (subject, relation, ctx)
                and e.card is Card.FUNCTIONAL]

    def current_edge(self, subject, relation, ctx=DEFAULT) -> Optional[Edge]:
        return next((e for e in self._slot(subject, relation, ctx) if e.is_current()), None)

    def default_value(self, subject, relation) -> Optional[str]:
        e = self.current_edge(subject, relation, DEFAULT)
        return e.obj if e else None

    def _reset_fresh(self, subject, relation, ctx, keep) -> None:
        for e in self._slot(subject, relation, ctx):
            if e is not keep:
                e.fpos.clear()
                e.fneg.clear()

    def _absorb_exceptions(self, subject, relation, t) -> None:
        """After the default belief changes, a specific-context exception that now equals the
        default is absorbed (the exception dissolved)."""
        dv = self.default_value(subject, relation)
        for e in self.edges.values():
            if ((e.subject, e.relation) == (subject, relation) and e.ctx != DEFAULT
                    and e.card is Card.FUNCTIONAL and e.is_current() and e.obj == dv):
                e.close_interval(t)
                e.absorbed = True

    # -- ingest --------------------------------------------------------------
    def ingest(self, subject, relation, obj, *, polarity="+",
               cardinality: Card = Card.FUNCTIONAL, context: str = DEFAULT,
               episode_id: str, t=None) -> Action:
        """Route one observation and mutate the graph. Returns the Action taken.

        polarity  : "+" asserts the belief is PRESENT, "−"/"-" asserts it is ABSENT.
        The residual is structural — a positive object that differs from the current belief is a
        conflict; one that equals it is a restatement.
        """
        self._clock += 1
        if t is None:
            t = self._clock                 # a real timestamp so closed intervals actually close
        self.card_of.setdefault(relation, cardinality)
        e = self.edge(subject, relation, obj, context, cardinality)
        was_past = e.is_past()
        neg = polarity not in ("+", "pos", "present", True)
        (e.neg if neg else e.pos).add(episode_id)
        (e.fneg if neg else e.fpos).add(episode_id)

        if cardinality is Card.PLURAL:
            return self._ingest_plural(e, neg, t)
        return self._ingest_functional(subject, relation, obj, context, e, was_past, neg, t)

    def _ingest_plural(self, e: Edge, neg: bool, t) -> Action:
        if not neg:
            if e.is_current():
                return Action.ASSIMILATE
            was_past = e.is_past()
            e.open_interval(t)
            e.fneg.clear()
            return Action.REVIVE if was_past else Action.ACCRETE
        # negative on a plural member
        if e.is_current() and len(e.fneg) >= self.k:
            e.close_interval(t)
            e.fpos.clear()
            return Action.RETRACT
        if e.is_current():
            return Action.INCUBATE
        if len(e.neg) >= self.k:
            return Action.ASSERT_ABSENT
        return Action.NOOP

    def _ingest_functional(self, subject, relation, obj, ctx, e: Edge,
                           was_past: bool, neg: bool, t) -> Action:
        key = (subject, relation, ctx)
        cur = self.current_edge(subject, relation, ctx)
        if not neg:
            if ctx != DEFAULT and cur is None and obj == self.default_value(subject, relation):
                return Action.REDUNDANT            # a specific context that just restates the default
            if key in self.contested:
                return Action.CONTESTED
            if cur is None:
                e.open_interval(t)
                self._reset_fresh(subject, relation, ctx, e)
                if ctx == DEFAULT:
                    self._absorb_exceptions(subject, relation, t)
                return Action.REVIVE if was_past else Action.SEED
            if cur is e:
                return Action.ASSIMILATE
            if len(e.fpos) >= self.k:              # a rival with enough FRESH evidence
                if self.flips.get(key, 0) >= self.flip_max:
                    self.contested.add(key)
                    cur.close_interval(t)          # suspend both — no forced winner
                    e.close_interval(t)
                    return Action.CONTESTED
                cur.close_interval(t)
                e.open_interval(t)
                self._reset_fresh(subject, relation, ctx, e)
                self.flips[key] = self.flips.get(key, 0) + 1
                if ctx == DEFAULT:
                    self._absorb_exceptions(subject, relation, t)
                return Action.REVIVE if was_past else Action.REVISE
            return Action.INCUBATE
        # negative, functional
        if cur is e and len(e.fneg) >= self.k:
            e.close_interval(t)
            self._reset_fresh(subject, relation, ctx, None)
            return Action.RETRACT
        if cur is e:
            return Action.INCUBATE
        if len(e.neg) >= self.k:
            return Action.ASSERT_ABSENT
        return Action.NOOP

    # -- queries -------------------------------------------------------------
    def believe(self, subject, relation, context: str = DEFAULT):
        """Answer for (subject, relation) under a context: the current object(s), the default as
        a fallback, an ``UNRESOLVED``/``ABSENT`` marker, or ``None`` if unknown."""
        if (subject, relation, DEFAULT) in self.contested or (subject, relation, context) in self.contested:
            return "UNRESOLVED"
        card = self.card_of.get(relation)
        if card is Card.PLURAL:
            return sorted({e.obj for e in self.edges.values()
                           if (e.subject, e.relation) == (subject, relation)
                           and e.ctx in (context, DEFAULT) and e.is_current()})
        e = self.current_edge(subject, relation, context)
        if e:
            return e.obj
        if context != DEFAULT:
            d = self.current_edge(subject, relation, DEFAULT)
            if d:
                return d.obj
        absent = [x for x in self._slot(subject, relation, context) if x.status() == "ABSENT"]
        if absent:
            return "ABSENT"
        return None

    def hop(self, start, path):
        """Multi-hop traversal along current belief edges. ``path`` is a list of relations;
        returns the objects reachable from ``start`` by following them in order."""
        frontier = {start}
        for relation in path:
            frontier = {e.obj for e in self.edges.values()
                        if e.subject in frontier and e.relation == relation and e.is_current()}
            if not frontier:
                break
        return sorted(frontier)

    def beliefs(self, subject=None) -> list:
        """All current belief edges (optionally for one subject) — the live memory."""
        return [e for e in self.edges.values()
                if e.is_current() and (subject is None or e.subject == subject)]
