# The evolving-graph model — the frontier of SchemaMem

> **Status: the current frontier, ahead of the submitted slot-model paper.** `core_model.md` and
> `full_paper_zh.md` describe the slot model as evaluated. This document captures the conceptual leap
> made after a memory dump on real data exposed the slot model's structural limits. It is where the
> method is going. Nothing here is frozen; if a better structure serves SOTA memory evolution, take it.

## The north star, stated plainly

The goal is **state-of-the-art memory evolution for long-running agents, inspired by the schema** —
not a data structure and not a fixed set of actions. A memory evolves *soundly* when, as evidence
arrives, it: strengthens what recurs, revises what genuinely changed, dismisses noise without
overwriting a belief, grows to hold genuinely new facts, and drops what it can already reconstruct.
The **schema** — an internal model of an entity issuing graded expectations about the next
observation — is the inspiration for *how*, and the **prediction residual** is the single signal it
all turns on. The structure is a means; do not confuse it for the end, and do not die-hard any
version of it.

## Why the slot model was silently narrow

The slot model held **one string-valued belief per attribute** and routed every observation by
residual magnitude × cross-episode recurrence. A dump on real data (FactConsolidation) exposed two
faults that are not tuning bugs — they are the structure being wrong.

### Fault 1 — memory evolution has two dynamics; the slot had one

Attributes fall into two kinds with **different evolution dynamics**:

| kind | example | a new value | has a single "current"? |
|---|---|---|---|
| **stateful / functional** | diet, location, job | **replaces** the old (supersession) | yes |
| **accumulative / plural** | products developed, hobbies, events | **coexists** with the old (growth) | no — it is a set |

The residual alone **cannot** tell these apart: a second value is high-residual in both cases. The
slot model, having only the replacement path, forced accumulation through it — so "Apple developed
iPod" was thrown to the exception store because the single `developed` slot already held QuickTime,
though **both are true**. The missing second axis is the **relation's cardinality** (functional vs
plural). Graded expectation ("the next observation should match the current value") is only
meaningful for functional relations; a plural relation has no single expected next value, so
prediction error there routes *consolidate-vs-grow*, not *consolidate-vs-update*. The signal stays
one signal; cardinality decides where it points.

### Fault 2 — an isolated conflict is not a dead exception; it is an incubating belief

The slot model's `finalize()` swept unpromoted candidates into a terminal `exceptions` store where
they **died**. But:

- an isolated conflict that **recurs** was a real change we were slow to accept → it should promote
  to an UPDATE;
- observations that **accumulate without matching any existing belief** are a *new belief forming*.

So the isolated conflict should stay **alive and promotable**, not be filed away as terminal. This is
exactly the **hippocampal→neocortical consolidation** the paper's own CLS/SLIMM grounding describes:
the hippocampus holds the one-off event; repeated replay consolidates it into a neocortical schema.
The slot model's dead-exception sweep *contradicted* its own cognitive grounding. The frontier fixes
this: a conflict **INCUBATES** as a pending edge and is promoted when evidence accrues.

## The frontier: an evolving knowledge graph

Memory is a graph whose **edges carry evolving belief**.

```
nodes  = entities (Apple, iPod, Caroline, Shanghai) + literals (150cm, Dec 11)
edges  = subject --relation--> object, each carrying:
           cardinality : FUNCTIONAL (one object at a time) | PLURAL (many coexist)
           support     : the distinct episodes backing it (consolidation strength)
           status      : BELIEF | SUPERSEDED | PENDING(incubating)
           t, residual, source_facts
```

One residual signal, routed by cardinality, yields **five destinations**:

| residual | cardinality / support | action | branch |
|---|---|---|---|
| ≈ 0 | — | **CONSOLIDATE** — add episode support; belief firms | consolidation |
| high | PLURAL | **GROW** — new coexisting object; nothing superseded | (accumulation) |
| high | FUNCTIONAL, ≥ k episodes | **UPDATE** — supersede belief, promote rival | updating |
| high | FUNCTIONAL, < k episodes | **INCUBATE** — held PENDING, alive, still accruing | (incubation) |
| reconstructable | — | **DISSOLVE** — release the raw form | forgetting |

This is implemented and unit-tested in `src/schemamem/graph_core.py` (deterministic, no LLM;
`tests/test_graph_core.py` proves all five dynamics plus multi-hop). It **generalises** `core.py`:
the residual, the k≥2 floor, episode-dedup, and accommodate-as-supersede all carry over onto edges;
what is added is the cardinality axis (GROW) and the incubation lifecycle (no dead exceptions).

### What objects-as-nodes buys: multi-hop

Because an object is a real node — the object of one edge is the subject of another — an answer can
be reached by **chaining relations** even when it is stored nowhere directly: "what sport does the
team Nick coaches play?" is `hop(Nick, [coaches, plays_sport])`. The slot model, with string-valued
slots, structurally could not do this. Multi-hop is now fair game (MAB-MH tiers, LongMemEval chained
questions). Retrieval becomes: resolve the query entity → k-hop neighbourhood → typed-weight ranking
(belief edges high, superseded lower, pending lowest — the "schema-typed weighted propagation"
`method_reflection.md` sketched as future work). **Top risk: entity resolution** — linking "Apple"
/ "Apple Inc." / "the company" to one node; a mislink corrupts traversal.

## The unifying lens: minimum description length

Prediction error is the *operational* signal; **MDL is the deeper justification**, and it *derives*
the cardinality distinction rather than hand-setting it. The schema is whatever internal model
encodes the observation stream in the fewest bits:

- **stateful** attribute: values are mutually exclusive over time, so "current value + change points"
  is shorter than listing every past value → MDL prefers **replacement** (supersession chain);
- **plural** attribute: values coexist and do not predict each other, so no encoding is shorter than
  listing them all → MDL prefers **accumulation** (keep every edge).

So "replace vs accumulate" is an MDL outcome, not a switch we flip. Honest caveat (as in the paper):
we do not compute description length; we approximate the residual with an LLM surprise score and
cardinality with an LLM judgment. MDL is the lens and the justification, not a claim of exact coding.

## What survives from the paper, unchanged

The frontier keeps the paper's spine:

- **one signal** (residual) drives all evolution;
- **graded expectation** still applies, exactly where it is valid — functional relations;
- the **three research branches** (consolidation / updating / forgetting) still map one-to-one, and
  are joined by the two operations the phenomenon also needs (accumulation, incubation);
- the **cognitive grounding** (schema, prediction error, CLS/SLIMM) is now honoured *better* —
  incubation is the CLS consolidation the slot model's dead-exception sweep contradicted.

## Staged build (protect the working baseline)

- **Phase A — promote structure to graph.** `graph_core.py` (done) → L2 emits triples with entity
  linking + cardinality → 1-hop graph retrieval + rendering. Single-hop reconnects to eval and
  validates the graph on real data without needing traversal. The slot model stays runnable as the
  fallback; its numbers (second across three axes at 1/6.6 context) are the floor.
- **Phase B — multi-hop retrieval.** Entity resolution + k-hop + typed-weight propagation. The
  multi-hop payoff (MAB-MH, chained questions).
- **Phase C — deeper (optional / next paper).** Richer traversal, cross-entity reasoning.

Do Phase A first: even if B runs out of runway, we have a coherent evolving graph with native
growth and incubation — strictly better than the slot model — not a half-finished rewrite.
