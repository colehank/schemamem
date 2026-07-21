---
description: Show current state of the AAAI-27 evolution-comparison experiments — which phases are done, which are pending, where the numbers live.
---

Read `docs/eval/evolution_comparison_plan.md` — that document holds the current experiment
matrix, phase ordering, handoff format, and numbers. When picking up eval work:

1. Look at §2 (the matrix) first — it marks each `[method × subset]` cell `✓done` / `→now` /
   `⏳pending`. This is the ground truth for what's been run.
2. Then read §3 for phase ordering and §7 for what to do if a phase fails.
3. Existing SchemaMem memory samples are catalogued in §5 with their artifact IDs.
4. If a run has produced new numbers or memory dumps, update §2 IN PLACE (don't append below
   the table — keep it a running ledger, one row per subset), then commit.

For the four-benchmark data inventory itself (what parquet is where, which sub_datasets exist,
config paths), the sibling doc is `docs/eval/benchmark_catalog.md`.
