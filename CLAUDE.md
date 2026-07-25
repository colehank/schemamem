# CLAUDE.md — SchemaMem

Project memory for Claude Code. Read this first; it tells you what the project is, where things
live, how we work, and — importantly — **which things are stable and which are still moving**.

## What this is

**The north star: SOTA memory evolution for long-running LLM agents, inspired by the schema.**
Not a particular data structure, not a particular set of actions — those are means. The end is a
memory that evolves *soundly* as evidence arrives: it strengthens what recurs, revises what
genuinely changed, dismisses noise, and drops what it can reconstruct. The schema — an internal
model of an entity that issues graded expectations about the next observation — is the *inspiration*
for how to do that, and the **prediction residual** (how far an observation departs from what the
schema expects) is the single signal the whole thing turns on. Everything below is one way to
realise that goal, and is **explicitly not the goal itself**. Do not die-hard on any current
version; if a better structure serves SOTA memory evolution, take it.

**Two realizations exist in this repo, on purpose:**

- **The slot model (`src/schemamem/core.py`) — the current *baseline*, with real numbers.** A
  per-entity schema of named single-valued slots; the residual routes each observation among
  assimilate / accumulate / accommodate / (protect) / forget. This is what every eval number so far
  was produced with, and it is the **fallback** — it stays runnable and correct.
- **The evolving graph (`src/schemamem/graph_core.py`) — the *frontier*.** A knowledge graph whose
  edges carry evolving belief. It generalises the slot model and fixes two things the slot model got
  wrong (see the Direction section). It is the direction of travel, being built up beside the
  baseline so neither blocks the other.

## ⚠️ What is STABLE vs what is MOVING

This file and the code describe **mechanism and structure**, which are relatively stable. The
**scientific framing — method emphasis, motivation, novelty story, and the paper abstract — is NOT
frozen and changes in real time.** Do not treat any prose description of "the motivation" or "the
contribution" as settled, and do not hardcode abstract/claim wording into code, comments, or docs.

The living sources of truth for the science are, in order:

- `docs/design/core_model.md` — the core mental model (field gap → human-memory grounding →
  motivation → the model). **This is the canonical conceptual document** — start here for the
  four-part conceptual arc (field gap → human memory → motivation → model).
- `docs/design/method_reflection.md` — the algorithm design reasoning (one-signal/two-axis
  convergence, the k≥2 identifiability + MDL argument, data-structure unification, open forks,
  and per-item landing status against `core.py`).
- `docs/design/full_paper_zh.md` — **the paper's full Chinese draft, actively maintained**.
  This is the long-form expansion of `core_model.md`: everything from Introduction to Method,
  Experiments, and Conclusion, in Chinese, kept in sync with each science decision. It is
  **not** an archived draft — it evolves with the method. Use it as the source of truth for
  the paper's structure, section ordering, and current framing; the English submission (via
  AuthorKit27) will be translated from this file. When you land a science change, update this
  file alongside `core_model.md`.
- `docs/design/abstract.md` — historical abstract drafting notes (the registered submission
  is authored by the user directly; this file is preserved as the drafting history).

When the science and this file disagree, **the design docs win** — and when you make a framing
decision with the user, update the relevant `docs/design/*.md`, not this file. Keep CLAUDE.md about
structure and process.

- `docs/design/evolving_graph.md` — **the current frontier model**: the evolving knowledge graph,
  the two evolution dynamics (replacement vs accumulation), exception-as-incubation, the KG-with-
  evolution position, and the MDL lens that unifies them. Read this to understand where the method
  is going; `core_model.md` / `full_paper_zh.md` still describe the slot-model paper as submitted.

## Direction: don't die-hard the slot model (read before proposing "the fix")

The slot model reached second place across three evolution axes at a sixth of the context — good,
but a memory dump on real data exposed a structural limit, and chasing it inside the slot model is
the wrong instinct. Two things the slot model gets wrong, and how the frontier answers them (full
reasoning in `docs/design/evolving_graph.md`):

1. **Memory evolution has two dynamics, and the slot model only had one.** Some attributes
   **replace** (a person lives in one place at a time — a new value supersedes the old). Others
   **accumulate** (a company develops many products — a new value coexists). The single-valued slot
   forced accumulation through the replacement path, so a real value ("Apple developed iPod") got
   thrown to the exception store because the slot was already taken. The residual alone cannot tell
   these apart — both are high-residual. The **relation's cardinality** (functional vs plural) is
   the second axis that does. In the graph, plural relations grow natively.
2. **An isolated conflict is not a dead exception — it is an incubating belief.** The slot model's
   `finalize()` swept unpromoted candidates into a terminal `exceptions` store where they died. But
   an isolated conflict that *recurs* was a real change we were slow to accept, and one that
   *accumulates without matching any existing belief* is a new belief forming. Exceptions should
   stay **alive and promotable** — which is exactly the hippocampal→neocortical consolidation the
   CLS grounding already describes. In the graph, a conflict INCUBATES as a pending edge and is
   promoted (to UPDATE, or to a new belief) when evidence accrues.

**The frontier keeps the paper's spine and extends it.** One residual signal still drives
everything; graded expectation still applies where it is valid (functional relations); and the
actions (SEED / ASSIMILATE / ACCRETE / REVISE / RETRACT / REVIVE / CONTESTED / RESOLVE) are the
residual routed by cardinality **and observation polarity**. The living detail — including the
generative "v2 math" core where every action becomes a *reading* of one competition model
(divisively-normalised candidate competition, endogenous residual, cardinality as a coupling β) — is
in `docs/design/evolving_graph.md`; do not re-derive it here. Objects becoming first-class nodes also
buys **multi-hop** (an answer reachable by
chaining relations, stored nowhere directly), which the slot model structurally could not do. KG is
not the enemy of evolution — *static* triple KG is; a **belief-carrying** graph is not, and that is
what we build. Leave the possibility space open: the goal is SOTA memory evolution, and the
structure serves it, never the reverse.

For the empirical side (benchmarks, comparisons, and the current experiment plan) look at
`docs/eval/`:

- `docs/eval/benchmark_catalog.md` — full dimension/subset inventory of the four MemoryData
  benchmarks (MAB, MemBench, LongMemEval-s, LoCoMo), verified from host parquet + configs.
  Answers "what data exists" and "what's already wired".
- `docs/eval/evolution_comparison_plan.md` — **the current AAAI-27 experiment plan**: the three
  evolution-axis capabilities we must beat baselines on (A change-detection, B knowledge-update,
  C exception-preservation), the phase-by-phase execution schedule with ROI ordering, the
  handoff format for the baselines session, and the memory-structure comparison figure spec.
  Start here when picking up eval work.

## Repository layout

```
src/schemamem/
  core.py           # BASELINE L3: per-slot changepoint arbitration. Pure, deterministic, no LLM.
  graph_core.py     # FRONTIER L3 (v1, COUNTING): evolving belief graph — value+evidence(±polarity)+
                    #   intervals+context; actions routed by cardinality x polarity; contested->resolve,
                    #   revive, multi-hop; Resolver (entity/relation canon) + event-time. Pure, no LLM.
  coupled_core.py   # FRONTIER L3 (v2, GENERATIVE): the same dynamics as readings of ONE model —
                    #   divisively-normalised candidate competition p(v), endogenous residual −log p(v),
                    #   cardinality = coupling beta. See docs/design/evolving_graph.md "generative core".
  config.py         # RuntimeConfig — ONE place for base_url/api_key/model/embedding_* (MemoryData-aligned;
                    #   env + from_mapping loaders; /v1 normalisation). Pure stdlib.
  prompts.yaml      # the L1/L2 prompts as readable block scalars + the rationale for each earned rule
  prompts.py        # thin LOADER of prompts.yaml -> the same SLOT_MERGE_SYS/CLEAN_SYS/... names (edit the YAML)
  schema_memory.py  # SchemaMemorySystem — the composed class: __init__ + write API (add_chunk/add_chunks);
                    #   the pipeline stages are mixins so the public API + eval contract are unchanged:
  _llm.py           #   LLMMixin        — chat + embedding helpers (mockable)
  _l1.py            #   L1Mixin         — raw episode -> self-contained facts
  _l2.py            #   L2Mixin         — facts -> slot observations -> L3 ingest (+ schema-state view)
  _retrieval.py     #   RetrievalMixin  — render schema into retrieval context + timeline
  _answer.py        #   AnswerMixin     — answer over rendered context
  _util.py          #   _extract_json (shared JSON-recovery helper)
  __init__.py       # public exports (incl. RuntimeConfig)
tests/              # test_core.py (slot routing) + test_graph_core.py (graph dynamics + hops),
                    #   both no-LLM; test_system.py (adapter contract, mock LLM);
                    #   test_bench_adapters.py (FC subject parser, pure-Python)
examples/           # diet_dialogue.py — offline end-to-end demo, no API key
eval/               # MemoryData benchmark adapter + config + integration guide (see eval/README.md)
docs/CONFIGURATION.md   # LLM / embedding endpoint setup
docs/design/        # LIVING design docs — the science. Not frozen.
docs/eval/          # LIVING eval docs — benchmark catalog + AAAI-27 experiment plan
docs/               # method_architecture.png
```

## The pipeline (four layers)

- **L0** `turns: list[dict]` — raw dialogue, noisy, unresolved references.
- **L1** `facts: list[str]` — self-contained, time-anchored facts. One episode → many facts.
  A fact is a *faithful cleaning* of an episode (resolve refs, drop filler) — **not** a schema.
- **L2** `observations: list[Observation]` — slot-level points `{entity, slot, value, pred_error,
  episode_id, t, candidate_id, source_fact}`. One fact → possibly many observations. L2 reads L3's
  current belief to compute `pred_error`, so L2/L3 are coupled.
- **L3** `SchemaGraph` — an **entity-centric attributed graph** (Entity + Slot nodes; HAS_SLOT and
  EVIDENCE edges), NOT a triple KG. Each Slot holds belief / superseded / exceptions / ledger and
  runs the per-slot changepoint arbitration.

## Design invariants of the SLOT BASELINE (do NOT silently change *in `core.py`*)

These are deliberate decisions for the **slot baseline** (`core.py` + `schema_memory.py`). Changing
one *there* is a real decision — raise it, don't drift into it. The **frontier graph deliberately
revisits three of them** (marked ⟳), because the dump exposed them as slot-model artifacts, not
principles — see the Direction section. The distinction: invariants without ⟳ are principles that
carry to the graph too; invariants with ⟳ were structural choices the graph supersedes on purpose.

1. ⟳ **Change-vs-exception is the point** *(slot framing; the graph reframes)*. In the slot model the
   distinctive outcome was the *protected exception*. The frontier keeps the underlying capability
   but reframes it: an isolated conflict is not a terminal protected exception, it **incubates** and
   can be promoted (INCUBATE → UPDATE / new belief). Do not "simplify" the isolated-conflict handling
   away in either model — but do not treat "protect as a dead outcome" as the goal; incubation is.
2. **k ≥ 2 is a hard floor, not a tunable down to 1.** One observation cannot distinguish a
   permanent change from a one-off (identical likelihoods). Accommodation requires ≥ 2 *distinct
   independent episodes*. Episode-dedup (counting distinct `episode_id`, not raw hits) is load-bearing.
3. **Candidate ids must name a concrete POSITIVE value, never a negation.** `"meat"`, `"fish"` — never
   `"not_vegetarian"`. Negations let unrelated deviations merge and mix exceptions with real change.
4. **Do NOT decompose a belief into its parts during extraction.** "strict vegetarian (no meat/eggs/
   dairy)" is ONE assertion, not four.
5. **Arbitration is binary on `pred_error`.** The L2 extractor emits three labels — 0.0 (consistent),
   1.0 (conflict), 0.5 (partial: related but neither a clean match nor a clear contradiction), plus
   *drop* for irrelevant material. Only 1.0 opens a candidate and enters the cross-episode vote;
   0.0 confirms the belief; 0.5 is recorded in the ledger as a weak signal only — never a candidate,
   never counted toward accommodation (`candidate_id` MUST be null for 0.0 and 0.5, per prompts.py).
   The vote itself has been kept binary since the last revert — do not let 0.5 leak into candidate
   creation or counting.
6. ⟳ **No abstraction pyramid — but a belief-carrying graph is fine.** We still avoid
   MemTree/reflection-style bottom-raw→top-summary hierarchies (abstraction smooths exceptions away).
   The slot model expressed this as "flat attributed graph, not a triple KG". The frontier revisits
   the *not-a-KG* half: it IS a knowledge graph, but a **belief-carrying** one (edges hold evolving
   belief + timeline), which is not the static triple KG the invariant warned against and does not
   flatten evolution. What stays banned is the summary pyramid, not entity-to-entity edges.
7. **`retrieve_with_source_groups` degrades to empty context for an unseen entity** → the agent
   falls back to plain retrieval. This is the *built-in falsification test*: gains must concentrate
   on knowledge-update and exception questions, and single-hop must match a retrieval baseline. Do
   not "improve" single-hop by leaking schema context into it.
8. **Result claims are conservative: "competitive", accuracy-only.** Token-efficiency was dropped as
   a selling point (needs separate experiments). Don't reintroduce token/latency claims without the user.
9. **Library defaults vs paper main-result config.** `online_decay` and `enable_forgetting` (ε)
   are OFF by default *at the library level* — the safe library behavior is no forgetting, no online
   decay. **But the paper's main-result configuration turns `enable_forgetting` ON**:
   reconstruction-gated forgetting is a first-class contribution (§5.3 in `docs/design/full_paper_zh.md`)
   and the main results report it engaged. `online_decay` remains an ablation in both library and
   paper. When someone reads the eval harness config, `enable_forgetting: True` is expected for the
   main table; when they read `SchemaMemorySystem()` with no kwargs, `enable_forgetting=False` is
   expected. Both are correct; they are answering different questions ("safe default" vs "the
   configuration under which the paper's main-table numbers were produced").

## Prompt invariants

`prompts.py` earned each of its rules by fixing a real extraction failure. Invariants 3, 4, 5 above
live in `EXTRACT_SYS`. If you edit prompts, re-run `tests/test_system.py` and, ideally, re-validate
against a live endpoint on the diet dialogue in `examples/`.

## Development workflow (uv-managed, always)

Everything goes through [uv](https://docs.astral.sh/uv/). Do not use bare `pip`/`python`.

```bash
uv sync                            # create .venv + install (runtime + dev)
uv run pytest                      # full test suite (must stay green:
                                   #   13 core + 5 bench + 14 system + 17 graph + 8 coupled = 57 total)
uv run ruff check .                # lint
uv run examples/diet_dialogue.py   # offline end-to-end sanity check
```

If pytest isn't installed in the active env, a stdlib fallback works — each test file's
`test_*` functions can be run with plain `unittest`-style assertions:

```bash
PYTHONPATH=src:tests python -c "
import test_core as m, inspect
for n, f in inspect.getmembers(m, inspect.isfunction):
    if n.startswith('test_'):
        try: f(); print(f'PASS {n}')
        except AssertionError as e: print(f'FAIL {n}: {e}')
"
```

Add a dependency with `uv add <pkg>` (runtime) or `uv add --dev <pkg>` (dev); commit the updated
`uv.lock`. The core (`core.py`) must stay import-light and LLM-free — only `schema_memory.py` touches
the LLM (via an OpenAI-compatible client).

## Evaluation

Benchmarks run through the MemoryData harness on a remote GPU host (turing_pub), NOT locally.
`eval/README.md` has the integration contract and steps. The three-method contract the harness
calls is `add_chunk` / `retrieve_with_source_groups` / `ask_with_retrieved_context`, all on
`SchemaMemorySystem`. Integrating SchemaMem = vendoring `src/schemamem/*.py` into
`methods/schemamem/source/schemamem/`.

**AAAI-27 main table (three benchmarks, evolution-axis targeted)**:

- **LongMemEval-s** — the update axis + honest report of the temporal short-side. NOTE: we run the
  **MemoryAgentBench-packaged subset** (`longmemeval_s*`): 300 questions over 5 SHARED contexts, not
  the official 500. The official release gives each instance its own ~50-session haystack, i.e. 500
  separate memory builds (~12.7 min each measured) — infeasible for 4 methods in the window. Type mix
  is proportional; knowledge-update is 45, not 78. Do not cite 500/78 for what we actually ran.
  the temporal short-side.
- **MemoryAgentBench / Conflict_Resolution / FactConsolidation** — both single-hop (SH) and
  multi-hop (MH), 6k context tier. This is the change-detection axis.
- **MemBench / noisy** — the isolated-exception axis (`protect-as-exception` is our unique
  third outcome; MemBench-noisy is where it earns its keep).

LoCoMo is retained as a coverage sanity check (already-in-hand gpt-4o-mini numbers), not as a
main-table benchmark.

**Baselines are Mem0 / A-MEM / MemoryBank** — the three evolution-branch representatives
(update / consolidation / forgetting). They are prepared in a separate session and integrated
via the same harness. `docs/eval/evolution_comparison_plan.md` holds the current experiment
plan (phase ordering, matrix ledger, handoff format).

## How we work (conventions)

- **Discuss in Chinese, write artifacts in English.** The user thinks through the design in Chinese;
  code, docs, and paper prose are English.
- **Be honest and audit yourself.** Do not overclaim. Flag collisions with prior work, unverified
  citations, and framing that a reviewer could break. Distinguish "our synthesis" from "the field's
  consensus" explicitly. When you're unsure a citation says what we claim, say so.
- **Verify, don't confabulate.** Ground claims in the actual code / the survey / fetched sources.
  Cite identifiers from real lookups, not memory.
- **Keep the tests green and the example runnable** as the definition of "not broken".
