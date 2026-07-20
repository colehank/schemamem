# Slot canonicalization (a) and paraphrase guard (b)

Two embedding-backed guards, added to address the residual issues from the LoCoMo
validation (slot fragmentation, paraphrase-as-false-change). Both hang off a single
injected `similarity(a, b) -> float` callable so `core.py` stays pure (no network);
the embedding implementation lives in `SchemaMemorySystem._similarity` (cached cosine
over an OpenAI-compatible embeddings endpoint). If embeddings are unavailable (e.g. a
scripted mock), `_similarity` returns 0.0 and both guards no-op — behaviour falls back
to the pure structural core.

## (a) Slot canonicalization — `enable_slot_merge` (DEFAULT OFF)

When a would-be-new slot is about to be minted, compare its `name: value` descriptor
against existing slots of the same entity; if cosine ≥ `slot_merge_threshold`, route the
observation into the existing slot instead. The value carries most of the signal —
abstract names like `relaxation_method` and `artwork` look far apart, but their values
are both "painting".

**Why it defaults OFF.** A clean A/B on a *fixed* observation stream (one extraction pass,
49 obs, replayed with the merge toggled — LLM nondeterminism controlled for) shows the
mechanism works but is **too blunt to enable by default**:

- At threshold 0.55 it correctly merged Melanie's `relaxation_method: painting` into the
  `artwork`/`artistic_expression` cluster.
- But it also merged three of Caroline's genuinely distinct slots — `volunteering_experience`,
  `community_support`, `art_show` — because all three are about LGBTQ topics. The embedding
  captures topical *relatedness*, whereas slot identity needs *same-attribute*. This is
  semantic drift: relatedness ≠ identity.
- Raising the threshold to remove the false merges (≈0.66+) also removes most true merges.

So embedding slot-merge has a narrow, data-dependent usable band. It is kept as an
**ablation** (`enable_slot_merge=True`, tune `slot_merge_threshold` per dataset), not a
default. A stronger signal (e.g. an LLM same-attribute judgment, or clustering over
value distributions rather than a single descriptor) is the direction for making it
default-safe.

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

- Core guards: `test_slot_merge_routes_near_duplicate_into_existing_slot`,
  `test_paraphrase_guard_reinforces_instead_of_superseding`. Suite 14/14.
- Defaults: slot-merge OFF (ablation, needs per-dataset threshold), paraphrase-guard ON.
- Open: a same-attribute (not same-topic) slot-merge signal that is default-safe.
