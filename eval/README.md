# Evaluating SchemaMem on MemoryData

SchemaMem is evaluated through the [MemoryData](https://github.com/OpenDataBox/MemoryData)
harness (arXiv 2606.24775), which runs many memory systems behind one interface on
LongMemEval, LoCoMo, LongBench and MemBench. This directory holds the two files that
plug SchemaMem into that harness.

## Contract

The harness only ever calls three methods on a memory system:

| method | role |
|---|---|
| `add_chunk(text, timestamp)` | write / memorize one context chunk |
| `retrieve_with_source_groups(query) -> (context, source_id_groups)` | read |
| `ask_with_retrieved_context(query, context) -> str` | answer |

`schemamem.SchemaMemorySystem` implements exactly this contract, so the adapter is thin.

## Files

- **`schemamem_adapter.py`** — repository adapter mirroring MemoryData's `a_mem` adapter.
  It imports `SchemaMemorySystem` from the vendored source and forwards the three calls.
- **`hybrid_schemamem.yaml`** — method config: model / endpoints / embedding dim, plus the
  SchemaMem hyperparameters (`change_threshold`, `reconstruction_tolerance`,
  `min_evidence_count`). `agent_name` contains the `schemamem` substring so the harness
  routes to the SchemaMem handler.

## Integration steps

1. Vendor the implementation into the harness:
   `methods/schemamem/source/schemamem/`  ← copy `src/schemamem/*.py` here
   (so `from schema_memory import SchemaMemorySystem` resolves inside the adapter).
2. Place `schemamem_adapter.py` at `methods/schemamem/schemamem_adapter.py`.
3. Place `hybrid_schemamem.yaml` at `config/hybrid_schemamem.yaml`.
4. Smoke one query:
   ```bash
   python main.py \
     --agent_config   config/hybrid_schemamem.yaml \
     --dataset_config benchmark/memoryagentbench/Accurate_Retrieval/config/LongMemEval/Longmemeval_s.yaml \
     --max_test_queries_ablation 1 --force
   ```
5. Drop `--max_test_queries_ablation 1` for the full run.

## Hyperparameter map (config key ↔ core)

| config key | `SchemaMemorySystem` arg | `SchemaGraph` arg | meaning |
|---|---|---|---|
| `min_evidence_count` | `min_evidence_count` | `k` | distinct episodes to accommodate |
| `reconstruction_tolerance` | `reconstruction_tolerance` | `epsilon` (only if `enable_forgetting`) | forget tolerance |
| `change_threshold` | `change_threshold` | — | reserved for embedding-distance surprise (ablation) |

`online_decay` / `enable_forgetting` are off by default (main runs use the simple
stream-end version); switch them on for the corresponding ablations.

## Main table scope

**AAAI-27 main comparison (three benchmarks, each targeting one evolution axis)**:

- **LongMemEval-s** (full 6 question types) — the *knowledge-update* axis; the temporal
  short-side is reported honestly rather than hidden.
- **MemoryAgentBench / Conflict_Resolution / FactConsolidation** (SH-6k + MH-6k) — the
  *change-detection* axis. SH-6k is where the largest headroom is expected on this benchmark;
  the specific per-system numbers should be cited from the MAB paper directly when written into
  the final paper (do not copy leaderboard figures from memory).
- **MemBench / noisy** — the *isolated-exception* axis; the `protect-as-exception` outcome
  is what other systems structurally cannot produce.

**LoCoMo** is a coverage sanity check (gpt-4o-mini numbers already in hand), not a main-table
entry.

**Baselines** are the three evolution-branch representatives: **Mem0** (update),
**A-MEM** (consolidation/associative organization), **MemoryBank** (Ebbinghaus-style
forgetting). They are prepared in a separate session and integrated via the same
`methods/<name>/` + `config/hybrid_<name>.yaml` pattern as SchemaMem.

For the current experiment plan (phase ordering, matrix ledger, handoff format), see
`docs/eval/evolution_comparison_plan.md` in the repo root. Full per-benchmark data-shape
inventory (sub_datasets, config paths, wiring status) is in `docs/eval/benchmark_catalog.md`.
