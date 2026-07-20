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

Core comparison: **LongMemEval + LoCoMo**; LongBench / MemBench are extensions.
Cross-paradigm baselines already prepared in the harness cover reference (Long Context,
Embedding RAG), structural (Mem0), topological (GraphRAG) and hybrid (A-MEM).
