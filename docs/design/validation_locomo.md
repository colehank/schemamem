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

## Still rough (honest, open)

- **Speaker attribution leaks across turns.** One `support_system: husband and kids`
  landed on Caroline though it is Melanie's — when a conflicting observation is
  mis-attributed, it can overwrite the wrong entity's belief. Extraction is per-chunk and
  does not hard-bind a value to its speaker. Candidate for a stricter L1/L2 attribution step.
- **Slots still over-fragment.** `art_expression / art_impact / art_theme / art_belief`
  should arguably be one `art` slot. The "keep slots coarse" instruction helps but does not
  fully solve it; embedding-based slot canonicalization is a candidate.
- **Some "evolutions" are re-phrasings, not real change** (e.g. `support_group_experience`
  restating "felt accepted"). The rewriter treats a corroborated candidate as a new belief
  even when it is a paraphrase; distinguishing paraphrase from genuine change is open.

## Takeaway

The mechanism does the intended thing on real data (change vs exception, dated supersede
trail), and real data was necessary to expose the entity-explosion bug and the still-open
attribution / fragmentation / paraphrase issues. These are method boundaries to address
before the full benchmark run, not demo artifacts.
