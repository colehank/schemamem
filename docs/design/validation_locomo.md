# Real-data validation — LoCoMo sample 0 (qualitative)

A small qualitative probe: build a SchemaMem memory from one real LoCoMo conversation
(Caroline & Melanie, 19 sessions, May–Oct 2023) with `gpt-4o-mini`, `k=2`, and read
the schema it produces. This is *not* a benchmark score — it is "what does the memory
actually look like on real dialogue". Reproduce with `examples/locomo_probe.py`.
Snapshot of the output: `examples/outputs/locomo_sample0_schema.json`.

> **Related qualitative probes on the other two AAAI-27 benchmarks** — MAB FactConsolidation
> SH-6k (60-fact slice, 2/2 target conflicts correctly evolved into `superseded` trails) and
> MemBench-noisy (traj0, 9 entities × 84 slots, one real belief evolution captured) — are
> saved as artifacts and summarized in the experiment ledger at
> `docs/eval/evolution_comparison_plan.md` §5. This file focuses on LoCoMo.

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

## Update — after adding the L1 cleaning stage (+ tightening + parallel L1)

`add_chunk` now runs a two-stage pipeline: **L1** rewrites the raw chunk into subject-bound
self-contained facts (references resolved, speaker bound, filler dropped), then **L2** extracts
slot observations from those facts with the entity anchored to each fact's subject. L1 was then
tightened to emit attribute-level facts, not a play-by-play (one heavy session dropped from 37
raw facts to 7 consolidated ones). Batch ingestion (`add_chunks`) runs the stateless L1 stage
concurrently and keeps L2/L3 sequential.

Attribution is the clear win: bound at L1, Melanie's painting/family facts stay on Melanie and
Caroline's support-group/career facts stay on Caroline — no cross-entity bleed in these runs.
Runtime for the 19-session conversation: ~132 s serial → ~72–81 s with parallel L1
(measured across two runs; LLM latency varies).

Slot fragmentation improved but is **not** fully solved, and counts vary run to run (LLM
nondeterminism — including whether a given evolution gets caught). The saved snapshot
(`examples/outputs/locomo_sample0_schema.json`, after the seed fix below):

- Caroline: 9 slots, observation counts `[1,1,1,2,2,3,3,3,5]`.
- Melanie: 6 slots, observation counts `[1,1,1,2,3,4]`.

Many slots still carry only 1–2 observations — merging is partial, not the uniform "3–4 per slot"
an earlier draft of this note claimed (that was true only for Caroline; retracted). Earlier runs
of the same conversation did catch belief changes (`support_system`, `parenting_plan`, `plan`
accommodating), so evolution capture is real but run-dependent, not guaranteed every run.

## Still open

- **Slot granularity.** Related attributes still split (e.g. Melanie's `artwork` /
  `artistic_expression` / `relaxation_method` are all about painting). L1 consolidation and the
  L2 slot-reuse hint help but don't merge everything; embedding-based slot canonicalization is a
  candidate.
- **Paraphrase vs change** in the rewriter (unchanged from before).

## Fixed this iteration

- **`belief == None` slots (was 5, now 0).** An observation with `pred_error=0` but a non-null
  `candidate_id` (the extractor naming a value while calling it non-conflicting) fell through the
  seed path — the empty slot never formed a belief and the value ended up as a lone exception.
  Fixed in `core.py`: the first observation on an empty slot now seeds the belief regardless of
  `candidate_id` (there is nothing to conflict with yet); if it carried a candidate_id, that line
  is recorded as won. Regression test `test_empty_slot_seeds_even_with_candidate_id`. This is a
  pure-L3 fix and does not depend on the extractor obeying the "pred_error=0 ⇒ candidate_id null"
  prompt rule.

## Takeaway

The mechanism does the intended thing on real data (change vs exception, dated supersede trail),
and real data was necessary to expose and fix the entity-explosion bug and to motivate the L1
cleaning stage, which fixed attribution and reduced (not eliminated) slot fragmentation. Open
boundaries — residual slot granularity, `None`-belief slots, and paraphrase-vs-change — are for
the next iteration.
