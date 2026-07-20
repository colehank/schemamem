"""SchemaMemorySystem: the object the MemoryData adapter imports.

Packages the full SchemaMem pipeline behind the harness's three-method contract:

    add_chunk(text, timestamp)                     -> None      (L1 clean -> L2 extract -> L3 ingest)
    retrieve_with_source_groups(query, k)          -> (context, source_id_groups)
    ask_with_retrieved_context(query, context)     -> str

L3 arbitration (assimilate / accumulate / accommodate / protect) lives in core.py
and is fully deterministic + unit-tested. This module adds the LLM-driven L1/L2
(extraction + surprise + candidate merge) and query-time schema rendering.

The single LLM dependency is an OpenAI-compatible chat endpoint (local vLLM on
the eval host, or any gateway). Embeddings are optional and only used for the
flat-retrieval fallback on entities that have no schema yet (the design's
"degrade to pure RAG" path, source of single-hop parity).
"""
from __future__ import annotations

import json
import re
from typing import Optional

try:                                    # package-relative when vendored
    from .core import SchemaGraph, Observation, Action
    from .prompts import EXTRACT_SYS, REWRITE_SYS, ANSWER_SYS
except ImportError:                     # flat import in dev
    from core import SchemaGraph, Observation, Action
    from prompts import EXTRACT_SYS, REWRITE_SYS, ANSWER_SYS


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"assertions": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"assertions": []}


class SchemaMemorySystem:
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
        change_threshold: float = 0.5,
        reconstruction_tolerance: float = 0.15,
        min_evidence_count: int = 2,
        online_decay: bool = False,
        decay_window: int = 3,
        enable_forgetting: bool = False,
        state_path: Optional[str] = None,
        client=None,
    ):
        self.model = model
        self.retrieve_k = int(retrieve_k)
        self.change_threshold = float(change_threshold)
        self.reconstruction_tolerance = float(reconstruction_tolerance)
        self.min_evidence_count = int(min_evidence_count)
        self.online_decay = bool(online_decay)
        self.decay_window = int(decay_window)
        self.enable_forgetting = bool(enable_forgetting)
        self.state_path = state_path

        # LLM client (OpenAI-compatible). Injected in tests; built from env args otherwise.
        if client is not None:
            self._client = client
        else:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key or "EMPTY", base_url=api_base)

        # L3 graph with an LLM-backed belief rewriter (accommodation).
        # reconstruction_tolerance maps to core epsilon; forgetting is off unless enabled.
        self._graph = SchemaGraph(
            k=self.min_evidence_count, rewriter=self._rewrite_belief,
            online_decay=self.online_decay, decay_window=self.decay_window,
            epsilon=self.reconstruction_tolerance if self.enable_forgetting else None,
        )

        # running schema-state view fed back into the extraction prompt so the LLM
        # can reuse existing candidate ids / know the current belief.
        self._episode_counter = 0

    # ---- LLM helpers (each a single call; mockable) ------------------------
    def _chat(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.0) -> str:
        r = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return r.choices[0].message.content or ""

    def _rewrite_belief(self, old_belief, candidate) -> str:
        obs_lines = "\n".join(f"- {o.value} ({o.t})" for o in candidate.observations)
        user = f"OLD belief: {old_belief}\nNew corroborating observations:\n{obs_lines}\n\nNEW belief value:"
        out = self._chat(REWRITE_SYS, user, max_tokens=32).strip()
        # guard against empty / overlong: fall back to latest observed value
        return out if 0 < len(out) <= 60 else candidate.observations[-1].value

    # ---- schema-state view for the extraction prompt -----------------------
    def _schema_state(self) -> dict:
        state = {}
        for schema in self._graph.entities.values():
            for slot in schema.slots.values():
                key = f"{schema.entity}.{slot.name}"
                state[key] = {
                    "belief": slot.belief,
                    "candidates": list(slot.candidates.keys()),
                }
        return state

    # ---- WRITE: L1 clean -> L2 extract -> L3 ingest ------------------------
    def add_chunk(self, text: str, timestamp: Optional[str] = None) -> None:
        self._episode_counter += 1
        episode_id = f"ep{self._episode_counter}"
        t = timestamp or episode_id

        state_json = json.dumps(self._schema_state(), ensure_ascii=False)
        user = (f"CURRENT SCHEMA (per 'entity.slot': belief + open candidate keys):\n{state_json}\n\n"
                f"NEW MESSAGE:\n{text}\n\nJSON:")
        parsed = _extract_json(self._chat(EXTRACT_SYS, user, max_tokens=400))

        for a in parsed.get("assertions", []):
            entity = a.get("entity") or "user"
            slot = a.get("slot")
            if not slot:
                continue
            obs = Observation(
                entity=entity, slot=slot, value=a.get("value", ""),
                pred_error=float(a.get("pred_error", 0.0)), episode_id=episode_id, t=t,
                candidate_id=a.get("candidate_id"), source_fact=text,
            )
            self._graph.ingest(obs)

    def finalize(self):
        """Flush stalled candidates to protected exceptions (stream-end sweep)."""
        return self._graph.finalize()

    # ---- READ: render schema into context ----------------------------------
    def _render_entity(self, schema) -> str:
        lines = [f"Entity: {schema.entity}"]
        for slot in schema.slots.values():
            if slot.belief is not None:
                lines.append(f"  {slot.name}: {slot.belief} (current)")
            for old, when in slot.superseded:
                lines.append(f"  {slot.name}: {old} (was, superseded {when})")
            for o in slot.exceptions:
                lines.append(f"  {slot.name}: {o.value} (exception, {o.t})")
        return "\n".join(lines)

    def retrieve_with_source_groups(self, query: str, k: Optional[int] = None):
        """Return (context_text, source_id_groups).

        MVP: render every entity's schema (small in these benchmarks). Entities
        with no schema contribute nothing -> for a query about an unseen entity
        the context is empty and the harness answers from raw retrieval (the
        design's pure-RAG fallback). source_id_groups groups the source facts
        backing each rendered slot, for recall@k metrics.
        """
        self.finalize()
        blocks, groups = [], []
        for schema in self._graph.entities.values():
            blocks.append(self._render_entity(schema))
            for slot in schema.slots.values():
                srcs = [o.source_fact for o in slot.ledger if o.source_fact]
                if srcs:
                    groups.append(srcs)
        return "\n".join(blocks), groups

    # ---- ANSWER ------------------------------------------------------------
    def ask_with_retrieved_context(self, query: str, context: str) -> str:
        user = f"Memory context:\n{context}\n\nQuestion: {query}\nAnswer:"
        return self._chat(ANSWER_SYS, user, max_tokens=256).strip()
