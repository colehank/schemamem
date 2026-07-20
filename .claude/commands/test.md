---
description: Run the full test suite and the offline example via uv
---
Run the SchemaMem checks and report results concisely.

1. `uv run pytest` — all tests must pass (9 core routing + 2 system contract).
2. `uv run ruff check .` — lint.
3. `uv run examples/diet_dialogue.py` — the offline end-to-end demo must render
   belief + superseded trail + the protected exception (`ate meat`).

If anything fails, show the failing output and stop; do not "fix" a test by
weakening a locked invariant (see CLAUDE.md → Locked design invariants).
