---
description: Reconcile a framing/method change into the living design docs
---
The scientific framing (method emphasis, motivation, novelty, abstract) is NOT
frozen — it changes in real time. When the user has just made such a decision:

1. Identify which living doc it belongs in:
   - `docs/design/core_model.md` — the core mental model / conceptual framing
   - `docs/design/method_reflection.md` — algorithm design reasoning + open forks
   - `docs/design/abstract.md` — paper abstract, title, author notes
2. Edit that doc to reflect the decision. Keep the four-part structure of
   core_model.md (field gap → human memory → motivation → the model).
3. Do NOT copy the changed framing into CLAUDE.md or into code comments —
   CLAUDE.md stays about structure/process; the design docs are the source of truth.
4. If the change touches a Locked design invariant in CLAUDE.md, surface that
   explicitly to the user as a real decision before proceeding.
5. Summarize what changed in one paragraph.

$ARGUMENTS
