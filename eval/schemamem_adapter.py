"""Repository adapter for the vendored SchemaMem source.

This is a SKELETON / integration template for MemoryData. It mirrors the shape of
methods/a_mem/a_mem_adapter.py so that once the real SchemaMem implementation is
finalized, dropping it under ``source/schemamem/`` and wiring the three methods
below is all that remains.

The MemoryData harness only ever calls three things on this adapter:
  * add_chunk(text, timestamp=...)                      -> None      (write / memorize)
  * retrieve_with_source_groups(query) -> (context_text, source_id_groups)  (read)
  * ask_with_retrieved_context(query, context) -> str  (answer)

Keep those signatures stable; everything else is internal to SchemaMem.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from openai import OpenAI

# --- vendored source path wiring (mirror of a_mem_adapter) --------------------
CURRENT_DIR = Path(__file__).resolve().parent
SCHEMAMEM_SOURCE_ROOT = CURRENT_DIR / "source" / "schemamem"
if SCHEMAMEM_SOURCE_ROOT.exists() and str(SCHEMAMEM_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SCHEMAMEM_SOURCE_ROOT))

# When the real implementation lands, import it here, e.g.:
#   from schema_memory import SchemaMemorySystem
# For now we degrade gracefully so the skeleton imports cleanly.
try:
    from schema_memory import SchemaMemorySystem  # type: ignore
    _HAVE_SOURCE = True
except Exception:  # pragma: no cover - skeleton fallback
    SchemaMemorySystem = None  # type: ignore
    _HAVE_SOURCE = False


class SchemaMemAdapter:
    """Thin wrapper around SchemaMem for the MemoryData benchmark harness.

    Parameters mirror AMemAdapter so _initialize_schemamem_agent in utils/agent.py
    can be adapted from _initialize_a_mem_agent with minimal edits.
    """

    def __init__(
        self,
        *,
        model: str,
        retrieve_k: int = 10,
        embedding_model: str = "Qwen3-Embedding-4B",
        embedding_provider: Optional[str] = None,
        embedding_api_key: Optional[str] = None,
        embedding_api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        state_path: Optional[str] = None,
        # SchemaMem-specific hyperparameters (read from config schemamem_* keys)
        change_threshold: float = 0.5,          # genuine-change vs exception decision
        reconstruction_tolerance: float = 0.15, # epsilon for reconstruction-gated forgetting
        min_evidence_count: int = 2,            # cumulative count to trigger expectation update
        **extra_kwargs,
    ) -> None:
        self.model = model
        self.retrieve_k = int(retrieve_k)
        self.embedding_model = embedding_model
        self.embedding_provider = embedding_provider
        self.embedding_api_base = embedding_api_base
        self.api_base = api_base
        self.state_path = state_path
        self.change_threshold = float(change_threshold)
        self.reconstruction_tolerance = float(reconstruction_tolerance)
        self.min_evidence_count = int(min_evidence_count)

        # LLM client for answering (OpenAI-compatible: points at local vLLM 9908).
        self._client = OpenAI(api_key=api_key or "EMPTY", base_url=api_base)

        # Real memory system (populated when vendored source is present).
        if _HAVE_SOURCE and SchemaMemorySystem is not None:
            self._mem = SchemaMemorySystem(
                model=model,
                retrieve_k=self.retrieve_k,
                embedding_model=embedding_model,
                embedding_provider=embedding_provider,
                embedding_api_key=embedding_api_key,
                embedding_api_base=embedding_api_base,
                change_threshold=self.change_threshold,
                reconstruction_tolerance=self.reconstruction_tolerance,
                min_evidence_count=self.min_evidence_count,
                state_path=state_path,
            )
        else:
            self._mem = None  # skeleton mode

    # -- write ----------------------------------------------------------------
    def add_chunk(self, text: str, timestamp: Optional[str] = None) -> None:
        """Ingest one context chunk into SchemaMem (schema assimilate/accommodate/protect)."""
        if self._mem is None:
            raise NotImplementedError(
                "SchemaMem source not vendored yet. Place the implementation under "
                f"{SCHEMAMEM_SOURCE_ROOT} exposing SchemaMemorySystem, then this call "
                "forwards to self._mem.add_chunk(...)."
            )
        self._mem.add_chunk(text, timestamp=timestamp)

    # -- read -----------------------------------------------------------------
    def retrieve_with_source_groups(self, query: str):
        """Return (context_text, source_id_groups).

        source_id_groups is a list of lists of evidence source ids, needed for the
        LoCoMo/MemBench recall@k metrics. Mirror A-MEM's retrieve_with_source_groups.
        """
        if self._mem is None:
            raise NotImplementedError(
                "SchemaMem source not vendored yet. This must return "
                "(context_text, source_id_groups) once implemented."
            )
        return self._mem.retrieve_with_source_groups(query, k=self.retrieve_k)

    # -- answer ---------------------------------------------------------------
    def ask_with_retrieved_context(self, query: str, context: str) -> str:
        """Answer the query given retrieved schema context, via the chat endpoint."""
        if self._mem is not None and hasattr(self._mem, "ask_with_retrieved_context"):
            return self._mem.ask_with_retrieved_context(query, context)
        # Generic fallback answering path (used if source delegates answering to adapter).
        messages = [
            {"role": "system", "content": "Answer the question using only the provided memory context."},
            {"role": "user", "content": f"Memory context:\n{context}\n\nQuestion: {query}\nAnswer:"},
        ]
        resp = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=0.0, max_tokens=256,
        )
        return resp.choices[0].message.content or ""
