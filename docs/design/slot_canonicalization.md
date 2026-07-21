# Slot canonicalization (a) and paraphrase guard (b)

Two embedding-backed guards, added to address the residual issues from the LoCoMo
validation (slot fragmentation, paraphrase-as-false-change). Both hang off a single
injected `similarity(a, b) -> float` callable so `core.py` stays pure (no network);
the embedding implementation lives in `SchemaMemorySystem._similarity` (cached cosine
over an OpenAI-compatible embeddings endpoint). If embeddings are unavailable (e.g. a
scripted mock), `_similarity` returns 0.0 and both guards no-op — behaviour falls back
to the pure structural core.

## (a) Slot canonicalization — `enable_slot_merge` (DEFAULT OFF), two modes

When a would-be-new slot is about to be minted, decide whether it names the SAME ATTRIBUTE
as an existing slot of the entity; if so, route the observation into that slot instead of
minting a duplicate. Two modes (`slot_merge_mode`):

### `slot_merge_mode="llm"` (default when merge is on) — same-attribute judge

One LLM call asks whether the new `name: value` is the same underlying attribute as one of
the existing slots (`name: belief`), with the explicit instruction that *same topic is not
enough — the property itself must match*, and to prefer "keep separate" on doubt.

Clean A/B on a **fixed** observation stream (one extraction pass, 49 obs, replayed with the
merge toggled so LLM nondeterminism is controlled for):

- Correctly merged Melanie's `artistic_expression` into `artwork` (both her painting).
- **Correctly kept Caroline's `volunteering_experience`, `community_support`, `art_show`
  separate** — the three slots embeddings wrongly merged (below). The LLM distinguishes
  same-topic (all LGBTQ life) from same-attribute (three different properties).
- Conservative: it made only the one clearly-correct merge and did not chase borderline
  ones (e.g. `relaxation_method: painting` was left separate that run). Precision over
  recall — a wrong merge destroys a real distinction; a missed one only leaves a duplicate.

This is the recommended mode. Cost: one extra LLM call per newly-minted slot.

### `slot_merge_mode="embedding"` — cosine fallback (ablation)

Compares `name: value` descriptors by embedding cosine ≥ `slot_merge_threshold`. Same fixed
stream shows why it is **not** default-safe:

- At 0.55 it merged Melanie's `relaxation_method: painting` correctly, but **also merged
  Caroline's three distinct LGBTQ-topic slots** — embeddings capture topical *relatedness*,
  not attribute *identity* (semantic drift).
- Raising the threshold to kill the false merges (≈0.66+) also kills most true merges — a
  narrow, data-dependent usable band.

Kept as an ablation for comparison, not recommended.

**Why merge defaults OFF regardless of mode.** It adds cost (an LLM call or an embedding call
per new slot) and the LLM mode is deliberately conservative, so the gain over leaving
duplicate slots is modest; enable it explicitly (`enable_slot_merge=True`) when clean slots
matter more than throughput.

## (b) Paraphrase guard — `enable_paraphrase_guard` (DEFAULT ON)

Before a corroborated candidate accommodates (supersedes the belief), compare its value
to the current belief; if cosine ≥ `paraphrase_threshold` (0.90), treat it as
reinforcement (ASSIMILATE, mark the line won) rather than a change. This stops
"felt accepted" → "feels accepted" from manufacturing a false evolution.

**Why it is safer than (a).** The comparison is *within one slot* (candidate value vs the
slot's own belief), not across slots, so it measures same-attribute paraphrase directly and
does not suffer the cross-slot topical-drift failure of (a). It is unit-tested
(`test_paraphrase_guard_reinforces_instead_of_superseding`). On the current LoCoMo stream it
had no accommodation to act on (that run caught no k≥2 change — evolution capture is
run-dependent), so its real-data effect is visible only on runs that do catch a change.

## Status

- Core tests: `test_slot_judge_merges_same_attribute_not_same_topic` (LLM path),
  `test_slot_merge_routes_near_duplicate_into_existing_slot` (embedding path),
  `test_paraphrase_guard_reinforces_instead_of_superseding`. Full suite:
  13 core routing + 5 bench_adapters + 2 system contract = 20/20.
- Defaults: slot-merge OFF; when on, `slot_merge_mode="llm"` (same-attribute judge, the
  signal that fixed the topic-vs-attribute confusion embeddings could not). Paraphrase-guard ON.
- Open: the LLM judge is precise but conservative (low merge recall) — tuning it toward more
  aggressive merging without reintroducing false merges is the next lever.
