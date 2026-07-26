# Prompts — one file per prompt

Each `.md` file in this directory is a single L1/L2 prompt; its whole content is the prompt text,
loaded verbatim by `__init__.py` and re-exported as `SLOT_MERGE_SYS` / `CLEAN_SYS` / … . Edit the
`.md`, not the loader. Every rule below was **earned by fixing a concrete extraction failure** — the
rationale is here so an edit doesn't silently undo a hard-won invariant.

| file | stage | what it does |
|---|---|---|
| `clean.md` | L1 | raw episode → self-contained, time-anchored facts |
| `quant.md` | L1 | a focused pass for quantifiable state (counts / amounts / frequencies / progress) |
| `extract.md` | L2 | facts → assertions + the 3-valued surprise label |
| `slot_merge.md` | L2 | is a NEW slot the SAME attribute as an existing one? (bias to keep separate) |
| `rewrite.md` | — | accommodation: fold OLD belief + new evidence into one concise value |
| `answer.md` | query | answer over the rendered schema context |

## Load-bearing invariants (do NOT weaken without re-running `tests/test_system.py`)

**`extract.md`**
- `candidate_id` names a concrete **POSITIVE** value, never a negation of the old belief
  (`meat` / `fish`, never `not_vegetarian`) — negations let unrelated deviations merge, mixing
  exceptions with genuine change.
- Do **not** decompose a belief into its defining parts: "strict vegetarian (no meat/eggs/dairy)"
  is ONE assertion, not four.
- `pred_error` is `0.0` / `0.5` / `1.0`; `candidate_id` MUST be null for `0.0` and `0.5` — only a
  `1.0` conflict opens a candidate.
- COVERAGE FIRST: for a list of independent facts, emit exactly one assertion per fact, drop none.

**`clean.md`**
- Bind each fact to its SUBJECT. An assistant "contribute" turn (a recommendation/name/place) has
  SUBJECT = the TOPIC it's about, never "assistant" and never the user.
- NEVER drop a list item or a concrete scalar value (a count/amount/frequency/location/day/page) —
  a fact never emitted can never be arbitrated.
- Consolidate only WITHIN one attribute of one subject; never across subjects or attributes.

**`answer.md`**
- MEMORY OVERRIDES WORLD KNOWLEDGE; the "current" value wins over any "previously"/evidence line.
