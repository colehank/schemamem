# Mechanism → benchmark ROI (don't pay for machinery that wins no question)

The frontier accumulated a lot of cognitively-motivated machinery. Cognitive richness is **not**
eval points. This maps each mechanism to the benchmark **question type** it actually wins, so we
invest where the leaderboard is and keep the rest minimal. Benchmarks per `docs/eval/benchmark_catalog.md`
and the AAAI-27 table (LongMemEval-s / MAB FactConsolidation / MemBench-noisy; LoCoMo = coverage).

| mechanism | question type it wins | benchmark | ROI | verdict |
|---|---|---|---|---|
| **entity + relation resolution** | *all* — prevents "Apple"/"Apple Inc." and "lives_in"/"resides_in" fragmenting into non-competing nodes/slots | every one | **foundational** | **must-have, do first.** A prerequisite, not a question type; a mislink silently corrupts change-detection *and* multi-hop. Shipped in `graph_core.py` (`Resolver`). |
| **REVISE** (update) | a fact that changed ("used to live in X, now Y") | LongMemEval knowledge-update; FC change-detection | **high** | core selling point — the update axis. |
| **ACCRETE** (plural) | many coexisting values ("Apple developed iPod AND QuickTime") | FC (esp. multi-hop tier) | **high** | the slot model threw these to exceptions; the graph wins them. |
| **multi-hop** | answer reachable only by chaining relations | FC-MH; LongMemEval chained | **high** | needs entity resolution to work at all. |
| **event-time onset** | "*when* did X happen?" | LongMemEval temporal subset | **high** | shipped (`t` = event time, `onset()`); needs L2 to pass extracted event time. |
| **INCUBATE / exception** | an isolated fact against a noisy background | MemBench-noisy | **medium** | our distinctive third outcome; MemBench is where it earns its keep. |
| **ASSIMILATE** (consolidation) | a repeated/confirmed fact | FC single-hop; MemBench | **medium** | table stakes; every method does some of this. |
| **RETRACT** (removal) | something that *stopped* being true, no successor | LongMemEval update subset | **low-med** | a slice of the update axis; keep, don't over-invest. |
| **context / conditional** | belief that depends on situation ("weekday vs weekend") | LongMemEval preference (some) | **low** | few questions probe it; keep the backoff, don't build a context lattice. |
| **CONTESTED / RESOLVE** | a genuinely oscillating belief | *none identified* | **low** | cognitively motivated (sound evolution), **no clear eval question**. Keep minimal; do not optimise or tune. |
| **REVIVE** | a belief that returns after lapsing | *none identified* | **low** | same — for the "no dead exceptions" story, not the leaderboard. |
| **soft cardinality (β between 0 and 1)** | "usually one, sometimes two" relations | *rare* | **low** | elegance/expressiveness, not points. Ship functional/plural (β∈{0,1}); leave soft-β as theory. |
| **forgetting** (reconstruction-gated) | — (token efficiency, not accuracy) | — | **ablation** | token-efficiency was dropped as a selling point; keep as an ablation only, not a main-table claim. |

## The discipline

- **Do first (foundational):** entity + relation resolution. Everything else's ROI is gated on it —
  fragmented nodes/slots poison change-detection and multi-hop alike.
- **Invest (win real questions):** REVISE, ACCRETE, multi-hop, event-time, INCUBATE.
- **Keep minimal (sound-evolution story, no eval question):** CONTESTED/RESOLVE, REVIVE, soft-β,
  context. They belong in the paper's *model* for coherence; they should not consume tuning budget.
- **Ablation only:** forgetting.

When a mechanism in the "keep minimal" tier starts costing engineering or tuning time, that is the
signal to stop — it is paying for the story, not the score. If eval later surfaces a question type
that one of them wins, promote it with evidence, not on cognitive appeal alone.
