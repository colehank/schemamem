"""SchemaMem L3, the GENERATIVE core (v2 math): coupled candidate competition + endogenous residual.

The counting engine in ``graph_core.py`` routes with a pile of thresholds (k, flip_max, k+1,
contested-freeze, a strength hack). This module is the elegant limit those thresholds were reaching
for: **one generative model whose readings are the actions.** Each relation holds candidate values,
each with a recency-decayed evidence mass ``m_v``; the schema's expectation that the next observation
asserts ``v`` is a divisively-normalised competition:

    p(v) = e^{m_v/τ} / ( M0 + e^{m_v/τ} + β · Σ_{j≠v} e^{m_j/τ} )

An observation updates the mass with a gain read off that expectation:

    residual(v) = −log p(v)                         # ENDOGENOUS — no external label
    gain(v)     = g_min + g_amp · (2·p(v) − 1)²      # U-shaped: strong when expected OR surprising, weak at p≈0.5
    m_v ← m_v ± gain(v)                              # + present, − absent

Everything is a reading of ``p`` and ``m``:
  * cardinality  = the coupling β (β large FUNCTIONAL winner-take-all, β=0 PLURAL coexist, between SOFT);
  * residual     = −log p(v);
  * REVISE = RETRACT⊕ACCRETE = asserting v raises p(v) and, via the shared denominator, lowers rivals';
  * contested / resolve = a continuous ``confidence`` = p_top1 − p_top2 (no frozen state);
  * forgetting   = inherent — only the running mass (the sufficient statistic) is stored, never episodes.
The one hard floor kept explicit is **k≥2**: a functional belief only *changes* once a challenger has
≥ k fresh positive episodes (identifiability). Context is backoff; entity/relation resolution and
event-time onsets reuse the same ``Resolver`` as ``graph_core``.

Deterministic, LLM-free (the caller supplies the tuple and, optionally, a similarity for the resolver).
"""
from __future__ import annotations

import math
from typing import Optional

from .graph_core import Resolver

DEFAULT = "default"


class MassRelation:
    """One relation's candidate competition. β sets the coupling (cardinality)."""

    def __init__(self, beta: float, *, lam=0.9, tau=1.0, m0=1.0,
                 g_min=0.30, g_amp=1.7, p_on=0.45, k=2):
        self.beta = beta
        self.lam, self.tau, self.m0 = lam, tau, m0
        self.g_min, self.g_amp, self.p_on, self.k = g_min, g_amp, p_on, k
        self.m: dict = {}          # value -> mass
        self.last_t = 0
        self.fresh: dict = {}      # value -> fresh positive episodes since the incumbent last changed
        self.incumbent: Optional[str] = None
        self.onsets: dict = {}     # value -> event-time it first became true

    def _decay(self, t):
        if t > self.last_t:
            f = self.lam ** (t - self.last_t)
            for v in self.m:
                self.m[v] *= f
        self.last_t = t

    def expect(self) -> dict:
        exps = {v: math.exp(mv / self.tau) for v, mv in self.m.items()}
        tot = sum(exps.values())
        return {v: e / (self.m0 + e + self.beta * (tot - e)) for v, e in exps.items()}

    def ingest(self, v, pol, t, event_t=None):
        self._decay(t)
        self.m.setdefault(v, 0.0)
        pv = self.expect().get(v, 1 / (self.m0 + 1))     # expectancy BEFORE update drives the gain
        gain = self.g_min + self.g_amp * (2 * pv - 1) ** 2
        self.m[v] += gain if pol == "+" else -gain
        if pol == "+":
            self.fresh[v] = self.fresh.get(v, 0) + 1
            self.onsets.setdefault(v, event_t if event_t is not None else t)
        self._settle()
        return round(-math.log(max(pv, 1e-9)), 2), round(gain, 2)

    def _settle(self):
        """Update the functional incumbent (plural has no incumbent). The incumbent is the argmax by
        MASS; a rival splitting the probability does not unseat it — only its own evidence going net
        negative (RETRACT) does, and a challenger must clear the k-fresh floor (identifiability)."""
        if self.beta == 0:
            return
        if not self.m:
            self.incumbent = None
            return
        if self.incumbent is not None and self.m.get(self.incumbent, 0.0) < 0:
            self.incumbent = None                        # RETRACT: net negative evidence
        top = max(self.m, key=self.m.get)
        if self.incumbent is None:                       # seed / revive: must clear P_on to be a belief
            if self.m[top] > 0 and self.expect().get(top, 0.0) > self.p_on:
                self.incumbent = top
                self.fresh = {top: self.fresh.get(top, 0)}
        elif top != self.incumbent and self.fresh.get(top, 0) >= self.k:
            self.incumbent = top                         # challenger overtakes in mass, k fresh -> REVISE
            self.fresh = {top: self.fresh.get(top, 0)}

    def confidence(self) -> float:
        ps = sorted(self.expect().values(), reverse=True)
        top1 = ps[0] if ps else 0.0
        top2 = ps[1] if len(ps) > 1 else 0.0
        return round(top1 - top2, 2)

    def present(self) -> list:
        p = self.expect()
        return sorted(v for v in self.m if p[v] > self.p_on)

    def belief(self):
        """Functional -> the current value (or None after RETRACT); plural -> the present set."""
        if self.beta == 0:
            return self.present()
        return self.incumbent


class CoupledMemory:
    """Orchestration: entity/relation resolution, per-relation coupling β, context backoff,
    multi-hop, and event-time onsets — all over :class:`MassRelation`."""

    def __init__(self, resolver: Optional[Resolver] = None, **params):
        self.rels: dict = {}       # (subject, relation, ctx) -> MassRelation
        self.beta: dict = {}       # relation -> β (cardinality)
        self.resolver = resolver
        self.params = params
        self._ents: set = set()
        self._rels: set = set()

    def _cent(self, name, learn=True):
        return self.resolver.canon(name, self._ents, learn) if self.resolver else name

    def _crel(self, rel, learn=True):
        return self.resolver.canon(rel, self._rels, learn) if self.resolver else rel

    def ingest(self, subject, relation, obj, *, polarity="+", beta=1.5,
               context=DEFAULT, t=0, event_t=None):
        subject, obj, relation = self._cent(subject), self._cent(obj), self._crel(relation)
        self.beta[relation] = beta
        r = self.rels.get((subject, relation, context))
        if r is None:
            r = MassRelation(beta, **self.params)
            self.rels[(subject, relation, context)] = r
        return r.ingest(obj, polarity, t, event_t)

    def believe(self, subject, relation, context=DEFAULT):
        subject, relation = self._cent(subject, False), self._crel(relation, False)
        beta = self.beta.get(relation, 1.5)
        if beta == 0:                                    # plural: union of context + default
            out: set = set()
            for c in {context, DEFAULT}:
                r = self.rels.get((subject, relation, c))
                if r:
                    out |= set(r.present())
            return sorted(out)
        if context != DEFAULT:                           # functional: context backoff
            r = self.rels.get((subject, relation, context))
            if r and r.belief() is not None:
                return r.belief()
        r = self.rels.get((subject, relation, DEFAULT))
        return r.belief() if r else None

    def confidence(self, subject, relation, context=DEFAULT):
        subject, relation = self._cent(subject, False), self._crel(relation, False)
        r = self.rels.get((subject, relation, context)) or self.rels.get((subject, relation, DEFAULT))
        return r.confidence() if r else 0.0

    def hop(self, start, path):
        frontier = {self._cent(start, False)}
        for relation in path:
            relation = self._crel(relation, False)
            nxt: set = set()
            for n in frontier:
                b = self.believe(n, relation)
                if isinstance(b, list):
                    nxt |= set(b)
                elif b is not None:
                    nxt.add(b)
            frontier = nxt
            if not frontier:
                break
        return sorted(frontier)

    def onset(self, subject, relation, obj, context=DEFAULT):
        subject, obj = self._cent(subject, False), self._cent(obj, False)
        relation = self._crel(relation, False)
        r = self.rels.get((subject, relation, context))
        return r.onsets.get(obj) if r else None
