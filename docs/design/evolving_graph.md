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
one signal; cardinality decides where it points. (Plural members are not permanent, either — one can
be **retracted** by explicit negative evidence, "I stopped climbing"; this needs a second axis,
observation **polarity**, added in the frontier model below. Cardinality only governs whether a
positive rival *implies* the old value's negation — functional yes, plural no.)

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

Memory is a graph whose **edges carry evolving belief**. An edge is fully described by
*value + evidence + validity intervals + context*; the discrete "status" is a **reading** of these,
not a stored field.

```
nodes  = entities (Apple, iPod, Caroline, Shanghai) + literals (150cm, Dec 11) — shared, first-class
edges  = subject --relation--> object (a belief), fully described by:
           value      : (subject, relation, object)
           cardinality: FUNCTIONAL (one at a time) | PLURAL (many coexist) — a property of the relation
           evidence   : the distinct episodes backing it; each carries a timestamp and a
                        polarity (+ present / − absent)
           intervals  : the validity periods [from, to) it held; open = current, multiple = revived
           context    : the tag(s) under which it holds (weekday, at-work, ...)
STATUS IS DERIVED, not stored:
           current = has an open interval        pending = distinct-episode count < k
           past    = all intervals closed        (superseded vs retired = is there a successor? — a query)
strength (derived) = f(distinct episodes, recency, consistency) — sharpens the expectation and
                     raises the evidence needed to overturn it
```

One residual signal, routed by the relation's **cardinality** and the observation's **polarity**,
gated by the **k≥2** floor, drives every edge through one lifecycle. The named actions are that
lifecycle's projections (grouped by the three schema-evolution tiers below):

| observation | residual | condition | action | tier |
|---|---|---|---|---|
| ＋ present | ≈ 0 | restates the belief | **ASSIMILATE** — evidence++, belief firms | tuning |
| ＋ present | high | PLURAL, new object | **ACCRETE** — new coexisting belief | accretion |
| ＋ present | high | FUNCTIONAL, rival ≥ k | **REVISE** — close the old interval, open the new | accommodation |
| ＋ present | high | conflict < k | **INCUBATE** — held pending, alive, still accruing | pre-restructuring |
| − absent | high | this edge, ≥ k | **RETRACT** — close the interval, no successor | accommodation |
| new context | — | the conflict is context-bound | **RESTRUCTURE** — split into context-tagged beliefs | restructuring |
| ＋ present | — | matches a retired belief's context | **REVIVE** — reopen a closed interval (cheap; savings) | (revival) |
| reconstructable | — | belief regenerates the raw form | **FORGET** — drop the verbatim, keep the gist | (orthogonal) |

Note **REVISE = RETRACT(old) ⊕ ACCRETE(new)**, fused by functional exclusivity: on a functional
relation a positive rival *implies* the old value's negation, so eviction + install happen in one
step; on a plural relation there is no such implication, so a member only leaves via its own explicit
RETRACT. This is why **plural relations evolve too** — the slot model, lacking polarity, could only
ever grow them.

**Implemented today** in `src/schemamem/graph_core.py` (deterministic, no LLM;
`tests/test_graph_core.py`): ASSIMILATE / ACCRETE / REVISE / INCUBATE (under the older names
CONSOLIDATE / GROW / UPDATE / INCUBATE) plus multi-hop. It generalises `core.py`: the residual, the
k≥2 floor, and episode-dedup all carry onto edges. **Not yet implemented — the frontier's next
step:** polarity (RETRACT), the context tag (RESTRUCTURE + conditional beliefs), REVIVE, and
validity intervals replacing the status enum. The representation move is
*(cardinality, support, status)* → *(value, evidence±, intervals, context)*.

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

## The cognitive spine: schema evolution in three tiers (+ context)

The method's cognitive grounding is **schema evolution**, and it runs at two levels at once:

- each **edge** behaves like a memory **trace** — it strengthens, is updated, extinguishes, revives;
- the **graph** of edges **is the schema** — and schema evolution is the *aggregate* of edge-level
  dynamics.

Schema evolution is not one tidy modern theory; it is a lineage we synthesize (state it as such):
**Piaget** (assimilation / accommodation / equilibration), **Rumelhart & Norman 1978**
("Accretion, Tuning and Restructuring: Three Modes of Learning"; originally a 1976 technical
report), and modern schema-memory neuroscience (Tse 2007; Gilboa & Marlatte 2017; van Kesteren
2012; Sinclair 2019/2021). The trace-level neural findings are the *implementation* of the
schema-level modes, not a competing account.

**Top cut (Piaget), by residual.** residual ≈ 0 → the observation *fits* → **assimilation**;
residual high → the schema must change → **accommodation**. The residual is the boundary
(Ortiz-Tudela et al. 2024, *Phil Trans R Soc B*; predictive processing).

**Three tiers of change (Rumelhart & Norman), by what the residual implies:**

| tier | R&N definition | our mechanism | trace-level grounding |
|---|---|---|---|
| **Accretion** | add new knowledge (most common) | ACCRETE (new coexisting belief); seeding | new trace; congruent fast integration (Tse 2007) |
| **Tuning** | slow refinement through practice; expertise | ASSIMILATE (accumulate support, sharpen expectation); minor REVISE | consolidation strengthening; precision-weighting |
| **Restructuring** | form new conceptual structures (rare, effortful) | INCUBATE → new belief; contested → differentiate; exception accumulates → new schema | differentiation of mispredicted memories (Preston 2017); pattern separation |

The six actions are the residual routed into these tiers: ASSIMILATE = tuning; ACCRETE = accretion;
REVISE / RETRACT = accommodation (minor); **INCUBATE = pre-restructuring** (holding a conflict until
it forces reorganization); FORGET = an orthogonal gist-retention axis.

**The context dimension (the three gaps the single-valued slot mishandled).** A belief carries a
**context tag**, which closes three cases exactly as the brain does:

- **revival (回潮)**: a retired belief reopens under a matching context — extinction is *not* erasure
  but a new competing memory (Bouton 2004); reopening is cheap because storage strength persists
  ("savings"; Bjork & Bjork).
- **contested (拉锯)**: two recurring rivals are *differentiated* into distinct context-tagged
  traces rather than thrashing a single value (integration-vs-differentiation, Preston 2017) — this
  is **restructuring**.
- **conditional (看情况)**: "weekday veg / weekend meat" is two context-instantiated beliefs,
  disambiguated by context-gating (dentate-gyrus ensembles, 2024), not a contradiction.

**Never-delete principle.** Retired and superseded beliefs are retained (closed validity intervals),
never erased — grounded in extinction-is-not-erasure (Bouton) and persistent storage strength
(Bjork). Revival is *reopening a closed interval*, not relearning from scratch.

**What this changes for the build.** Accretion and tuning are already in `graph_core.py`
(GROW, CONSOLIDATE). **Restructuring and the context tag are the frontier's next step** — the belief
representation becomes *value + validity intervals + evidence + context*, and the discrete "status"
enum dissolves into readings of these. Restructuring is the schema-level name for what INCUBATE was
reaching toward: not just swapping a value, but reorganizing structure when conflict accumulates.

**Honest notes.** Rumelhart & Norman 1978 verified (three modes as above; originally a 1976 report).
"Schema evolution" is our synthesis of a real lineage, not a single modern theory. Trace-level
findings (Bouton, Preston, Bjork, context-gating) are grounding by analogy, not claims of neural
mechanism. Context and restructuring are design direction, not yet implemented in `graph_core.py`.
Citations here (Rumelhart-Norman, Bouton, Preston, Bjork, context-gating, Tse, Sinclair,
Ortiz-Tudela) must be re-verified in Zotero with exact venue/year before entering the paper.

## The generative core: coupled competition + endogenous prediction error (v2 math)

> **Status: the arbitration MATH, one step ahead of `graph_core.py`'s counting engine.** Prototyped
> in `docs/design/prototypes/schema_coupled.py` (with `schema_sprt.py`, `schema_proto.py` tracing the
> progression — see that folder's README), not yet in the runnable core. This is where "elegant, self-
> consistent, minimal-principle" lands: the dozen actions and the pile of thresholds (k, flip_max,
> k+1, contested-freeze, the strength hack) collapse into **readings of one generative model**.

**The model.** Each relation holds candidate values, each with a recency-decayed evidence mass `m_v`.
The schema's expectation that the next observation asserts `v` is a **divisively-normalised
competition**:

```
p(v) = e^{m_v} / ( M0 + e^{m_v} + β · Σ_{j≠v} e^{m_j} )
```

`M0` is a null/prior ("don't know"); `β` is the coupling. An observation of `v` updates its mass:

```
residual(v) = −log p(v)                         # ENDOGENOUS — read off the state, no external label
gain(v)     = g_min + g_amp · (2·p(v) − 1)²      # U-shaped in expectancy
m_v ← m_v ± gain(v)                              # + for present, − for absent
```

**Everything becomes a reading of `p` and `m`:**

| construct | is just |
|---|---|
| **prediction residual** | `−log p(v)`, from the mass — the "one signal" is now *literal*, not an LLM label |
| **cardinality** | the coupling `β`: `β=1` FUNCTIONAL (winner-take-all), `β=0` PLURAL (coexist), between = SOFT |
| **REVISE = RETRACT ⊕ ACCRETE** | asserting `v` raises `p(v)` and, via the shared denominator, lowers rivals' `p` — one step |
| **SEED / ASSIMILATE / ACCRETE / REVISE / RETRACT** | a mass crossing / leaving the belief threshold `P_on` |
| **INCUBATE / CONTESTED** | the region `p ≈ 0.5` — also the *bottom of the U*, where the gain is smallest |
| **RESOLVE** | one mass pulling clear → `p` rises → confidence (`p_top1 − p_top2`) grows |
| **U-shape** (Quent/Greve/Henson) & the old "0.5 no-op" | the shape of `gain(p)`: strong at the expected and surprising extremes, weak in the ambiguous middle |
| **forgetting** | inherent — a relation stores only the running mass (the *sufficient statistic*), never the raw episodes |
| **k≥2** | the one hard floor kept explicit (identifiability): a *change* needs ≥ 2 distinct fresh episodes |

**Context is backoff**, not pooling: a specific context answers from its own evidence if it has any,
else falls back to the default — the exception overrides only where it has spoken (weekday → default,
weekend → its own). Absorption is automatic (when the exception stops differing, its readout equals
the default's).

**Grounding that is real, not decorative.** The denominator is **divisive normalisation** — Carandini
& Heeger's "canonical cortical computation"; the gain is **predictive coding** (update ∝ prediction
error). A sturdier spine than the BOCPD/MDL lenses invoked earlier.

**Honest trade.** Structural elegance (one generative model) is bought with MORE tunables
(`M0, τ, g_min, g_amp, P_on, β`) than the counting engine's `{k}`. Here "elegant math" means *one
principle*, not *fewest constants*. And this is only the arbitration core — **entity/relation
resolution, retrieval, multi-hop, and temporal onsets are orthogonal** (relation canonicalisation and
event-time onsets are prototyped alongside; joint cross-edge inference is named and **deferred**, not
built).

**Identity sentence (the spine everything hangs off):**

> SchemaMem models long-horizon memory as a **bank of per-relation competitions over a shared entity
> graph — divisively normalised, driven by endogenous prediction error — that decides, with minimal
> principle, when to consolidate, change, grow, or forget a belief.**

## What survives from the paper, unchanged

The frontier keeps the paper's spine:

- **one signal** (residual) drives all evolution;
- **graded expectation** still applies, exactly where it is valid — functional relations;
- the **three research branches** (consolidation / updating / forgetting) still map on, now joined by
  the operations the phenomenon also needs — accretion, incubation, restructuring, revival — with
  **context** as the extra dimension that makes them sound;
- the **cognitive grounding** (schema, prediction error, CLS) is now honoured *better* — incubation is
  the CLS consolidation the slot model's dead-exception sweep contradicted, and the three tiers
  (accretion / tuning / restructuring) give the whole thing a named cognitive spine. SLIMM is cited as
  a *hypothesis* only (challenged by the 2025 "slim pickings for SLIMM" replication); the grounding
  leans on the sturdier pillars (Tse, Sinclair, Quent/Greve/Henson, Bouton).

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
