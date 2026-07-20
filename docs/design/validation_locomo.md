# Real-data validation — LoCoMo sample 0 (qualitative)

A small qualitative probe: build a SchemaMem memory from one real LoCoMo conversation
(Caroline & Melanie, 19 sessions, May–Oct 2023) with `gpt-4o-mini`, `k=2`, and read
the schema it produces. This is *not* a benchmark score — it is "what does the memory
actually look like on real dialogue". Reproduce with `examples/locomo_probe.py`.
Snapshot of the output: `examples/outputs/locomo_sample0_schema.json`.

## What worked

- **Two real belief evolutions were captured**, with a superseded trail dated to when
  the change happened:
  - `Caroline.support_system`: `friends, family and mentors` → **`supportive network`**
    (superseded 2023-10-22), with `community` and `adoption advice/assistance group`
    kept as **protected exceptions** — isolated mentions never folded into the belief.
  - `Caroline.parenting_plan`: `ready to be a mom` → **`adoptive mom`**.
- The rendered query context is exactly the intended three-part view — current belief
  + superseded trail + exceptions — i.e. the capability an overwrite/merge system can't
  produce, demonstrated on real data rather than a scripted demo.
- Candidate merging held: `support_group_experience` (4 obs), `art_expression` (5),
  `hobby` (6) each collapsed to one slot rather than one-per-mention.

## Bug this surfaced (fixed) — the reason to test on real data

The clean single-entity diet demo hid a serious failure that only appeared with
multiple entities and the schema-state feedback loop:

- **Entity-name explosion.** The extraction prompt is fed the current schema so it can
  reuse slots. The old `_schema_state()` rendered flat `"entity.slot"` keys; the LLM
  sometimes copied such a key back into the `entity` field, producing
  `Caroline.support_group_experience`, which then fed back as
  `Caroline.support_group_experience.support_group_experience`, and so on — 40+ junk
  "entities" for one conversation.

Fixes (see `schema_memory.py`, `prompts.py`):
1. `_schema_state()` now renders **nested** `{entity: {slot: ...}}` — no flat compound key to copy.
2. `add_chunk(..., speakers=[...])` passes known entity names; `_clean_entity()` strips any
   `Entity.slot` compound to its head and snaps to a known speaker.
3. Prompt rules: `entity` must be a bare name (never `Entity.slot`); reuse existing slots;
   keep slots coarse; skip null-valued assertions.

After the fix the same conversation yields exactly two entities (Caroline, Melanie) with
coherent slots.

## Still rough (honest, open) — L2-only run

- **Speaker attribution is fragile.** Extraction was per-chunk and did not hard-bind a value
  to its speaker, so a value could in principle be assigned to the wrong entity. (An earlier
  draft of this note gave a specific mis-attribution example that did not match the saved
  snapshot — retracted; in `examples/outputs/locomo_sample0_schema.json`, `husband and kids`
  is correctly under Melanie.) This motivated the L1 stage below.
- **Slots over-fragment.** `art_expression / art_impact / art_theme / art_belief` should
  arguably be one `art` slot.
- **Some "evolutions" are re-phrasings, not real change** (e.g. `support_group_experience`
  restating "felt accepted"). Distinguishing paraphrase from genuine change is open.

## Update — after adding the L1 cleaning stage

`add_chunk` now runs a two-stage pipeline: **L1** rewrites the raw chunk into subject-bound
self-contained facts (references resolved, speaker bound, filler dropped), then **L2** extracts
slot observations from those facts with the entity anchored to each fact's subject. Re-running
the same conversation:

- Slots collapsed from 18/7 (Caroline/Melanie) to **6/6** — much less fragmentation, each slot
  now backed by 3–4 observations.
- Attribution is bound at L1: Melanie's painting/family facts stay on Melanie, Caroline's
  support-group/career facts stay on Caroline; no cross-entity bleed observed in this run.
- Cost: one extra LLM call per chunk (L1). Runtime for the 19-session conversation ~4 min.

Still open after L1: slot granularity (painting_experience / _significance / _as_expression /
_as_relaxation could be one `painting` slot), and paraphrase-vs-change in the rewriter.

## Takeaway

The mechanism does the intended thing on real data (change vs exception, dated supersede trail),
and real data was necessary to (a) expose and fix the entity-explosion bug, and (b) motivate the
L1 cleaning stage that fixed attribution and cut slot fragmentation. Remaining boundaries — slot
granularity and paraphrase-vs-change — are for the next iteration, not demo artifacts.
