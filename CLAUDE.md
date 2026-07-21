# CLAUDE.md — SchemaMem

Project memory for Claude Code. Read this first; it tells you what the project is, where things
live, how we work, and — importantly — **which things are stable and which are still moving**.

## What this is

SchemaMem is a long-term memory system for LLM agents, and the subject of an in-progress AAAI paper.
Its one idea: a per-entity **schema** (named slots + a time-ordered evidence ledger) that
distinguishes a **genuine change** to a belief from an **isolated exception** to it, using a single
criterion — the **prediction residual** of a new observation against the current belief — read
along two axes (magnitude × cross-episode recurrence). That criterion routes each observation to
one of a small set of actions (assimilate / accumulate / accommodate / protect, plus an optional
forget). The capability nobody else has is the third outcome: *protect as exception*.

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
  core.py           # L3: entity graph + per-slot changepoint arbitration. Pure, deterministic, no LLM.
  prompts.py        # validated L1/L2 extraction + rewrite + answer prompts (see "prompt invariants" below)
  schema_memory.py  # SchemaMemorySystem — LLM ingestion + query rendering; the public API + eval contract
  __init__.py       # public exports
tests/              # test_core.py (routing, no LLM) + test_system.py (adapter contract, mock LLM)
                    # + test_bench_adapters.py (FC subject parser, pure-Python)
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

## Locked design invariants (do NOT silently change)

These are structural decisions made deliberately with the user. Changing one is a real decision —
raise it, don't drift into it.

1. **Change-vs-exception is the point.** The system's reason to exist is producing the *protected
   exception* — the third outcome overwrite/merge systems structurally cannot. Never "simplify" it away.
2. **k ≥ 2 is a hard floor, not a tunable down to 1.** One observation cannot distinguish a
   permanent change from a one-off (identical likelihoods). Accommodation requires ≥ 2 *distinct
   independent episodes*. Episode-dedup (counting distinct `episode_id`, not raw hits) is load-bearing.
3. **Candidate ids must name a concrete POSITIVE value, never a negation.** `"meat"`, `"fish"` — never
   `"not_vegetarian"`. Negations let unrelated deviations merge and mix exceptions with real change.
4. **Do NOT decompose a belief into its parts during extraction.** "strict vegetarian (no meat/eggs/
   dairy)" is ONE assertion, not four.
5. **`pred_error` is a 3-class scheme: 0.0 (consistent) / 1.0 (conflict) / drop (irrelevant, no
   assertion).** No intermediate values (no 0.5). This has been reverted once already — keep it binary.
6. **The graph is a flat attributed graph, not an abstraction pyramid.** We deliberately avoid
   MemTree/reflection-style bottom-raw→top-summary hierarchies, because abstraction is exactly what
   smooths exceptions away.
7. **`retrieve_with_source_groups` degrades to empty context for an unseen entity** → the agent
   falls back to plain retrieval. This is the *built-in falsification test*: gains must concentrate
   on knowledge-update and exception questions, and single-hop must match a retrieval baseline. Do
   not "improve" single-hop by leaking schema context into it.
8. **Result claims are conservative: "competitive", accuracy-only.** Token-efficiency was dropped as
   a selling point (needs separate experiments). Don't reintroduce token/latency claims without the user.
9. **`online_decay` and `enable_forgetting` (ε) are OFF by default** — main runs use the simple
   stream-end version; these are ablation modes.

## Prompt invariants

`prompts.py` earned each of its rules by fixing a real extraction failure. Invariants 3, 4, 5 above
live in `EXTRACT_SYS`. If you edit prompts, re-run `tests/test_system.py` and, ideally, re-validate
against a live endpoint on the diet dialogue in `examples/`.

## Development workflow (uv-managed, always)

Everything goes through [uv](https://docs.astral.sh/uv/). Do not use bare `pip`/`python`.

```bash
uv sync                            # create .venv + install (runtime + dev)
uv run pytest                      # full test suite (must stay green:
                                   #   13 core routing + 5 bench_adapters + 2 system = 20 total)
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

- **LongMemEval-s** (full 6 question types, 500 questions) — the update axis + honest report of
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
