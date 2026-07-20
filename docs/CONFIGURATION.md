# Configuration — LLM & embedding endpoints

SchemaMem's core arbitration (`core.py`) is pure and needs nothing. The
`SchemaMemorySystem` layer makes **one LLM call per ingested chunk** (extraction +
surprise + candidate merge) plus one per belief rewrite and one per answer, through
an **OpenAI-compatible** chat API. Any endpoint that speaks that protocol works:
OpenAI, a gateway, or a local server (vLLM / Ollama / LM Studio / TGI).

## Two ways to configure

### 1. Environment variables (recommended)

The system reads the standard OpenAI variables when `api_base` / `api_key` are not
passed explicitly:

```bash
export OPENAI_BASE_URL="http://127.0.0.1:9908/v1"   # your endpoint
export OPENAI_API_KEY="EMPTY"                        # any non-empty string for a local server
```

```python
from schemamem import SchemaMemorySystem
mem = SchemaMemorySystem(model="Qwen3-8B")           # picks up OPENAI_* from env
```

### 2. Explicit arguments

```python
mem = SchemaMemorySystem(
    model="gpt-4o-mini",
    api_base="https://api.openai.com/v1",
    api_key="sk-...",
    min_evidence_count=2,
)
```

Explicit arguments win over environment variables.

## The `/v1` suffix (important)

The OpenAI SDK posts to `<base_url>/chat/completions`. If your `base_url` is a
gateway **root** without `/v1`, requests 404 silently. SchemaMem normalizes this
for you — it appends `/v1` if the base URL doesn't already end in it — so both of
these are fine:

```
http://127.0.0.1:9908          ->  normalized to  http://127.0.0.1:9908/v1
http://127.0.0.1:9908/v1       ->  used as-is
```

If you construct your own `openai.OpenAI(...)` client and pass it via `client=`,
this normalization does **not** apply — include `/v1` yourself.

## Model choice

- **Extraction quality matters.** Entity/slot naming and candidate merging depend
  on instruction-following; a small but capable instruct model (e.g. `gpt-4o-mini`,
  `Qwen3-8B`) is the tested floor. Very small models tend to over-fragment slots.
- `model` is passed straight through as the OpenAI `model` field — set it to
  whatever your endpoint serves.

## Embeddings (optional, not required for the default path)

The default retrieval renders every entity's schema directly and does **not** call
an embedding model. `embedding_model` / `embedding_api_base` are placeholders for
the ablation that scores surprise by embedding distance instead of an LLM label.
When you wire that path, point it at an OpenAI-compatible `/v1/embeddings` endpoint
the same way. Note the embedding dimension must match whatever the eval harness /
vector store expects.

## Local vLLM example (as used on the eval host)

```bash
# chat
vllm serve Qwen/Qwen3-8B --port 9908 --served-model-name Qwen3-8B
# embeddings (dim must match the store; 4B = 2560-dim)
vllm serve Qwen/Qwen3-Embedding-4B --port 9009 --served-model-name Qwen3-Embedding-4B
```

```bash
export OPENAI_BASE_URL="http://127.0.0.1:9908/v1"
export OPENAI_API_KEY="EMPTY"
uv run examples/locomo_probe.py locomo10.json --sample 0 --model Qwen3-8B
```

## No key needed for tests / the offline demo

`tests/` and `examples/diet_dialogue.py` inject a scripted mock client, so they run
with no endpoint and no key. Only the real-LLM paths (`examples/locomo_probe.py`,
production use) need configuration.
