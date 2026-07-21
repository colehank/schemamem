---
description: Run the full test suite and the offline example via uv (with a stdlib fallback if pytest isn't installed)
---
Run the SchemaMem checks and report results concisely.

1. `uv run pytest` if uv/pytest are available — all tests must pass.
   Current suite: 13 core routing + 5 bench_adapters + 2 system contract = **20 tests**.
2. If pytest isn't installed in the active env, use the stdlib fallback (per test file):
   ```
   PYTHONPATH=src:tests python -c "
   import test_core as m, inspect
   for n, f in inspect.getmembers(m, inspect.isfunction):
       if n.startswith('test_'):
           try: f(); print(f'PASS {n}')
           except AssertionError as e: print(f'FAIL {n}: {e}')
   "
   ```
   Repeat for `test_bench_adapters` and `test_system`.
3. `uv run ruff check .` — lint (if available).
4. `uv run examples/diet_dialogue.py` — the offline end-to-end demo must render belief +
   superseded trail + the protected exception (`ate meat`).

If anything fails, show the failing output and stop; do not "fix" a test by weakening a locked
invariant (see CLAUDE.md → Locked design invariants).
