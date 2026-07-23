"""SchemaMem L3 core, graph generalization: an entity-centric knowledge graph
whose edges carry evolving belief, arbitrated by one prediction-residual signal.

This is the graph promotion of ``core.py``. Where ``core.py`` held a per-entity
set of single-valued slots, here memory is a graph of typed relations between
entity nodes, and each *relation* on a subject arbitrates its objects. The same
signal — the residual of a new observation against what the relation currently
expects — routes every observation, but a second axis, the relation's
CARDINALITY, decides which of five destinations it reaches:

    CONSOLIDATE  - residual ~ 0: the observation restates an existing edge;
                   add its episode to that edge's support (belief gets firmer).
    GROW         - residual high, relation is PLURAL: a genuinely new object of a
                   multi-valued relation (Apple -developed-> iPod AND QuickTime).
                   Add a new belief edge; nothing is superseded.
    UPDATE       - residual high, relation is FUNCTIONAL, and a competing object
                   has reached k distinct episodes: the belief edge is superseded
                   and the competitor promoted.  (== core.py ACCOMMODATE)
    INCUBATE     - residual high, FUNCTIONAL, competitor below k: kept as a
                   PENDING edge — alive, still accruing support, NOT a dead
                   'exception'. Enough support later promotes it (UPDATE) or, if
                   it concerns a relation the subject had no belief for, seeds a
                   new belief.  (This is the hippocampal→neocortical incubation
                   the CLS grounding describes; core.py swept these to a terminal
                   exception store, which this module deliberately does not.)
    DISSOLVE     - reconstruction-gated forgetting; handled by the caller via a
                   tolerance, mirrored from core.py. Not emitted here yet.

FUNCTIONAL vs PLURAL is a property of the relation (lives_in is functional — one
place at a time; developed is plural — many products). The caller supplies it
(an LLM in the full system, an explicit arg in tests); this file only decides,
given (subject, relation, object, residual, episode, cardinality), what happens.

No LLM here. Deterministic and unit-tested, like core.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(str, Enum):
    CONSOLIDATE = "CONSOLIDATE"
    GROW = "GROW"
    UPDATE = "UPDATE"
    INCUBATE = "INCUBATE"
    DISSOLVE = "DISSOLVE"


class Card(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"   # one object holds at a time (lives_in, diet)
    PLURAL = "PLURAL"           # many objects coexist (developed, hobby)


class Status(str, Enum):
    BELIEF = "BELIEF"           # currently held
    SUPERSEDED = "SUPERSEDED"   # a functional object that was replaced
    PENDING = "PENDING"         # incubating: below the promotion threshold


@dataclass
class Edge:
    """One (subject) --relation--> (object) assertion carrying belief state.

    `support` counts DISTINCT episodes, mirroring the episode-dedup that makes
    the k>=2 floor meaningful: two turns of one conversation are not two votes.
    """
    subject: str
    relation: str
    obj: str
    status: Status = Status.PENDING
    support: set = field(default_factory=set)      # distinct episode_ids
    t: Optional[str] = None                        # timestamp of latest support
    source_facts: list = field(default_factory=list)

    @property
    def votes(self) -> int:
        return len(self.support)


@dataclass
class Node:
    """An entity (or literal) and its outgoing relations.

    edges[relation] is the list of edges for that relation. A FUNCTIONAL relation
    has at most one BELIEF edge at a time (others SUPERSEDED or PENDING); a PLURAL
    relation may have many BELIEF edges at once.
    """
    name: str
    edges: dict = field(default_factory=dict)      # relation -> list[Edge]

    def rel(self, relation: str) -> list:
        return self.edges.setdefault(relation, [])

    def belief_objects(self, relation: str) -> list:
        return [e.obj for e in self.edges.get(relation, []) if e.status is Status.BELIEF]


class SchemaGraph:
    """The evolving knowledge graph + its per-relation arbitration engine.

    k: distinct independent episodes a competing object needs before a FUNCTIONAL
    relation's belief is revised. Below k, the competitor incubates as PENDING —
    it is never discarded, so accumulation can still promote it later.
    """

    def __init__(self, k: int = 2):
        self.k = k
        self.nodes: dict = {}                       # name -> Node
        self._episode_order: dict = {}              # episode_id -> monotonic idx

    # -- nodes ---------------------------------------------------------------
    def node(self, name: str) -> Node:
        if name not in self.nodes:
            self.nodes[name] = Node(name=name)
        return self.nodes[name]

    def _episode_idx(self, episode_id: str) -> int:
        if episode_id not in self._episode_order:
            self._episode_order[episode_id] = len(self._episode_order)
        return self._episode_order[episode_id]

    # -- ingest --------------------------------------------------------------
    def ingest(self, subject: str, relation: str, obj: str, *,
               residual: float, episode_id: str, t: Optional[str] = None,
               cardinality: Card = Card.FUNCTIONAL,
               source_fact: str = "") -> Action:
        """Route one (subject, relation, object) observation and mutate the graph.

        residual: 0.0 == restates the current belief; 1.0 == conflicts with it.
                  For a PLURAL relation a "conflict" simply means "a new object",
                  which grows rather than competes.
        """
        self.node(subject)
        self.node(obj)                              # objects are first-class nodes
        self._episode_idx(episode_id)
        edges = self.node(subject).rel(relation)

        def find(o):
            return next((e for e in edges if e.obj == o), None)

        existing = find(obj)

        # (1) restatement of an object we already have -> consolidate that edge.
        if existing is not None:
            existing.support.add(episode_id)
            existing.t = t or existing.t
            if source_fact:
                existing.source_facts.append(source_fact)
            # a PENDING edge that reaches k gets promoted (see _promote).
            promoted = self._maybe_promote(subject, relation, existing, cardinality)
            return Action.UPDATE if promoted else Action.CONSOLIDATE

        # (2) a NEW object for this relation.
        edge = Edge(subject=subject, relation=relation, obj=obj,
                    support={episode_id}, t=t,
                    source_facts=[source_fact] if source_fact else [])
        edges.append(edge)

        has_belief = any(e.status is Status.BELIEF for e in edges if e is not edge)

        # PLURAL: coexists with whatever is already believed -> GROW.
        if cardinality is Card.PLURAL:
            edge.status = Status.BELIEF
            return Action.GROW

        # FUNCTIONAL, no belief yet: this seeds the belief (first observation).
        if not has_belief:
            edge.status = Status.BELIEF
            return Action.CONSOLIDATE

        # FUNCTIONAL, congruent with the belief (residual low) but a different
        # surface object: treat as reinforcement of the belief line, not a rival.
        if residual < 0.5:
            edge.status = Status.BELIEF        # co-belief (paraphrase-ish)
            return Action.CONSOLIDATE

        # FUNCTIONAL conflict: incubate. Promote immediately if it already has k.
        if self._maybe_promote(subject, relation, edge, cardinality):
            return Action.UPDATE
        return Action.INCUBATE

    def _maybe_promote(self, subject: str, relation: str, edge: Edge,
                       cardinality: Card) -> bool:
        """A PENDING functional edge with >= k distinct episodes wins: the current
        belief is superseded and this edge becomes the belief. Returns True on
        promotion. PLURAL edges never supersede, so they never promote this way."""
        if cardinality is not Card.FUNCTIONAL:
            return False
        if edge.status is Status.BELIEF or edge.votes < self.k:
            return False
        for e in self.node(subject).rel(relation):
            if e is not edge and e.status is Status.BELIEF:
                e.status = Status.SUPERSEDED
        edge.status = Status.BELIEF
        return True

    # -- queries -------------------------------------------------------------
    def objects(self, subject: str, relation: str,
                status: Status = Status.BELIEF) -> list:
        node = self.nodes.get(subject)
        if not node:
            return []
        return [e.obj for e in node.rel(relation) if e.status is status]

    def hop(self, start: str, path: list) -> list:
        """Multi-hop traversal along BELIEF edges. `path` is a list of relation
        names; returns the set of nodes reachable from `start` by following them
        in order. This is what having real edges (rather than string-valued slots)
        buys: an answer that is not stored directly but is reachable by chaining.
        """
        frontier = {start}
        for relation in path:
            nxt = set()
            for n in frontier:
                nxt.update(self.objects(n, relation))
            frontier = nxt
            if not frontier:
                break
        return sorted(frontier)

    def pending(self) -> list:
        """All incubating edges — alive, not discarded. The nursery for beliefs
        that have not yet earned promotion."""
        return [e for node in self.nodes.values()
                for edges in node.edges.values()
                for e in edges if e.status is Status.PENDING]
