# Design prototypes — the arbitration core, in progression

These are **illustrative, standalone prototypes** (pure stdlib, no LLM, not imported by the package or
tests, excluded from lint). They trace how the frontier arbitration core evolved and back the claims in
[`../evolving_graph.md`](../evolving_graph.md). The runnable, tested core is
[`src/schemamem/graph_core.py`](../../../src/schemamem/graph_core.py); these show where its *math* is
heading.

Run any of them directly:

```bash
python3 docs/design/prototypes/<file>.py
```

| file | what it demonstrates | maturity |
|---|---|---|
| `schema_proto.py` | the **counting** engine on a broad dataset — every dynamic (assimilate / incubate / revise / retract / accrete / revive / context+absorption / contested→resolve / asserted-absent / multi-hop), plus the "unreasonable" behaviours a real run exposes | mirrors `graph_core.py` (shipped) |
| `schema_sprt.py` | replaces counting+thresholds with **evidence mass + argmax**; shows `contested`/`resolve`/`flip_max`/`k+1` collapse into a continuous **confidence** readout, and `k≥2` survive as the one floor | v1.5 math |
| `schema_coupled.py` | the **generative core**: divisively-normalised candidate competition `p(v)=e^{m_v}/(M0+e^{m_v}+β·Σ e^{m_j})` with an **endogenous** residual `−log p(v)` and a U-shaped gain. Cardinality = coupling β (functional↔soft↔plural); context = backoff; relation canonicalisation + event-time onsets; forgetting inherent (mass = sufficient statistic) | v2 math (the paper spine) |

The progression is the story: **a pile of rules → one decaying mass + argmax → one generative model
whose readings are the actions.** See `evolving_graph.md` §"The generative core (v2 math)".
