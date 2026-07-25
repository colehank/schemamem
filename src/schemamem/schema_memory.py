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

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

try:                                    # package-relative when vendored
    from .core import SchemaGraph
    from .config import RuntimeConfig
    from ._util import _extract_json
    from ._llm import LLMMixin
    from ._l1 import L1Mixin
    from ._l2 import L2Mixin
    from ._retrieval import RetrievalMixin
    from ._answer import AnswerMixin
except ImportError:                     # flat import in dev / vendored
    from core import SchemaGraph
    from config import RuntimeConfig
    from _util import _extract_json
    from _llm import LLMMixin
    from _l1 import L1Mixin
    from _l2 import L2Mixin
    from _retrieval import RetrievalMixin
    from _answer import AnswerMixin

__all__ = ["SchemaMemorySystem", "_extract_json"]


class SchemaMemorySystem(LLMMixin, L1Mixin, L2Mixin, RetrievalMixin, AnswerMixin):
    def __init__(
        self,
        *,
        model: Optional[str] = None,          # or supply config=RuntimeConfig(model=...)
        config: Optional[RuntimeConfig] = None,
        retrieve_k: int = 10,
        embedding_model: Optional[str] = None,
        embed_batch: int = 256,          # inputs per embeddings request (query-time ranking)
        # Characters of raw episode text appended after the schema gist at query
        # time. 0 disables the verbatim layer (schema-only, the previous behaviour).
        verbatim_budget: int = 24000,
        # facts per L2 completion; one assertion costs ~40 output tokens and the
        # reply is capped, so a larger batch silently truncates the tail.
        l2_batch: int = 25,
        # Characters an EPISODE must reach before extraction runs; 0 (default) keeps
        # one add_chunk = one episode. Raise it when the caller's granularity is finer
        # than an episode: MemBench sends 171 conversational TURNS totalling 6.3k
        # tokens, so per-turn extraction is both wasteful — a full L1+L2 pass on ~170
        # characters — and semantically wrong, since k>=2 counts DISTINCT episodes and
        # two adjacent turns of one conversation are not independent evidence.
        # Whether a call is an episode is the CALLER's granularity, so it is a config
        # decision rather than something to infer.
        min_episode_chars: int = 0,
        embedding_provider: Optional[str] = None,
        embedding_api_key: Optional[str] = None,
        embedding_api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        change_threshold: float = 0.5,
        reconstruction_tolerance: float = 0.15,
        min_evidence_count: int = 2,
        l1_quant_samples: int = 1,
        l1_window_chars: int = 4000,
        online_decay: bool = False,
        decay_window: int = 3,
        enable_forgetting: bool = False,
        enable_slot_merge: bool = False,     # slot canonicalization (merge duplicate slots)
        slot_merge_mode: str = "llm",        # "llm" (same-attribute judge) | "embedding"
        enable_paraphrase_guard: bool = True,
        slot_merge_threshold: float = 0.66,
        paraphrase_threshold: float = 0.90,
        state_path: Optional[str] = None,
        client=None,
    ):
        # Unified config: an explicit `config` is the base; loose kwargs override it (back-compat).
        cfg = (config or RuntimeConfig()).merged(
            model=model, api_key=api_key, base_url=api_base,
            embedding_model=embedding_model, embedding_base_url=embedding_api_base,
            embedding_api_key=embedding_api_key)
        self.config = cfg
        self.model = cfg.model
        self.retrieve_k = int(retrieve_k)
        self.change_threshold = float(change_threshold)
        self.reconstruction_tolerance = float(reconstruction_tolerance)
        self.min_evidence_count = int(min_evidence_count)
        self.l1_quant_samples = int(l1_quant_samples)
        self.l1_window_chars = int(l1_window_chars)
        self.online_decay = bool(online_decay)
        self.decay_window = int(decay_window)
        self.enable_forgetting = bool(enable_forgetting)
        self.enable_slot_merge = bool(enable_slot_merge)
        self.slot_merge_mode = slot_merge_mode
        self.embedding_model = cfg.embedding_model
        self._emb_cache: dict = {}
        self._embed_batch = int(embed_batch)
        self.verbatim_budget = int(verbatim_budget)
        self._l2_batch = max(1, int(l2_batch))
        self.min_episode_chars = int(min_episode_chars)
        self._pending: list = []          # buffered (text, timestamp) awaiting an episode
        self._pending_speakers = None
        self.state_path = state_path

        # LLM clients (OpenAI-compatible). Injected in tests; otherwise built from the unified
        # config (which already resolved env vars and normalised the /v1 suffix). Embeddings get
        # their OWN client when the config points them at a different endpoint (e.g. a dedicated
        # embedding server), reusing the chat client when they coincide.
        if client is not None:
            self._client = self._embed_client = client
        else:
            from openai import OpenAI
            self._client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
            if cfg.embedding_base_url == cfg.base_url and cfg.embedding_api_key == cfg.api_key:
                self._embed_client = self._client
            else:
                self._embed_client = OpenAI(api_key=cfg.embedding_api_key,
                                            base_url=cfg.embedding_base_url)

        # L3 graph with an LLM-backed belief rewriter (accommodation).
        # reconstruction_tolerance maps to core epsilon; forgetting is off unless enabled.
        self._graph = SchemaGraph(
            k=self.min_evidence_count, rewriter=self._rewrite_belief,
            online_decay=self.online_decay, decay_window=self.decay_window,
            epsilon=self.reconstruction_tolerance if self.enable_forgetting else None,
            # paraphrase guard and embedding slot-merge both need cosine; the LLM
            # slot judge needs the judge callable. Wire whichever the config asks for.
            similarity=(self._similarity
                        if (enable_paraphrase_guard
                            or (self.enable_slot_merge and self.slot_merge_mode == "embedding"))
                        else None),
            slot_judge=(self._judge_slot
                        if (self.enable_slot_merge and self.slot_merge_mode == "llm")
                        else None),
            slot_merge=self.enable_slot_merge,
            paraphrase_guard=bool(enable_paraphrase_guard),
            slot_merge_threshold=slot_merge_threshold,
            paraphrase_threshold=paraphrase_threshold,
        )

        # running schema-state view fed back into the extraction prompt so the LLM
        # can reuse existing candidate ids / know the current belief.
        self._episode_counter = 0
        # VERBATIM STORE: episode_id -> the raw chunk text, exactly as ingested.
        # The schema is an INDEX over these episodes, not a replacement for them.
        # L1 facts are an LLM rewrite and therefore already lossy; keeping the raw
        # text means a detail dropped by extraction is still recoverable at answer
        # time, and the "verbatim" half of the dual store is actually verbatim.
        self._episodes: dict = {}

    def add_chunk(self, text: str, timestamp: Optional[str] = None,
                  speakers: Optional[list] = None) -> None:
        """Ingest one context chunk as ONE episode: L1 clean -> L2 extract -> L3.
        For many chunks, prefer add_chunks() which parallelizes the L1 stage."""
        self._pending.append((text or "", timestamp))
        self._pending_speakers = speakers or getattr(self, "_pending_speakers", None)
        if sum(len(x) for x, _ in self._pending) >= self.min_episode_chars:
            self._flush_pending()
    def _flush_pending(self) -> None:
        """Turn everything buffered so far into ONE episode and ingest it."""
        if not self._pending:
            return
        buffered, self._pending = self._pending, []
        text = "\n".join(x for x, _ in buffered if x)
        timestamp = next((ts for _, ts in buffered if ts), None)
        if not text.strip():
            return
        self._episode_counter += 1
        episode_id = f"ep{self._episode_counter}"
        t = timestamp or episode_id
        self._episodes[episode_id] = (t, text)
        known = self._pending_speakers or list(self._graph.entities.keys())
        facts = self._clean_to_facts(text, known)
        self._ingest_facts(facts, episode_id, t, known)
    def add_chunks(self, chunks: list, speakers: Optional[list] = None,
                   max_workers: int = 8) -> None:
        """Ingest many chunks as an ordered episode stream.

        L1 cleaning is stateless per chunk, so it is run CONCURRENTLY across all
        chunks (I/O-bound LLM calls). L2 extraction + L3 arbitration read and mutate
        the shared schema, so they run SEQUENTIALLY in the original chunk order —
        preserving episode ordering and the cross-episode k-count.

        `chunks`: list of str, or list of (text, timestamp) tuples.
        """

        norm = [(c if isinstance(c, (tuple, list)) else (c, None)) for c in chunks]
        base_known = speakers or list(self._graph.entities.keys())

        # Phase 1 — parallel L1 (stateless). speakers known up front; if none given,
        # fall back to whatever entities already exist (empty on a fresh system).
        def _clean_with_retry(ct):
            # L1 is a network call; a transient failure or empty parse would silently
            # drop an entire episode. Retry a couple of times before giving up.
            for _ in range(3):
                try:
                    facts = self._clean_to_facts(ct[0], base_known)
                except Exception:
                    facts = []
                if facts:
                    return facts
            return []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fact_lists = list(ex.map(_clean_with_retry, norm))

        # Phase 2 — sequential L2/L3 in order.
        for (text, ts), facts in zip(norm, fact_lists):
            self._episode_counter += 1
            episode_id = f"ep{self._episode_counter}"
            self._episodes[episode_id] = (ts or episode_id, text)
            self._ingest_facts(facts, episode_id, ts or episode_id, base_known)
    def finalize(self):
        """Flush stalled candidates to protected exceptions (stream-end sweep)."""
        self._flush_pending()          # a partial episode still counts
        return self._graph.finalize()
    def dump_memory(self, traj_id: Optional[str] = None) -> dict:
        """Serialise the memory state for the cross-method structure comparison.

        Four fields per slot, chosen so every baseline can be rendered in the same
        shape and the structural gap is visible rather than argued:

            current    - the belief in force now
            history    - the superseded chain (overwrite-style systems leave this empty)
            exceptions - protected isolated violations (no baseline can produce these)
            n_obs      - observations that landed on this slot

        Calls finalize() first, since exceptions only materialise at stream end.
        `traj_id` is accepted for interface parity with the baseline adapters and
        is echoed back rather than used to filter — one system instance holds one
        trajectory in this harness.
        """
        self.finalize()
        entities = {}
        for schema in self._graph.entities.values():
            slots = {}
            for slot in schema.slots.values():
                slots[slot.name] = {
                    "current": slot.belief,
                    "history": [{"value": v, "t": t} for v, t in slot.superseded],
                    "exceptions": [{"value": o.value, "t": o.t,
                                    "source_fact": o.source_fact} for o in slot.exceptions],
                    "n_obs": len(slot.ledger),
                }
            entities[schema.entity] = slots
        out = {"method": "schemamem", "entities": entities}
        if traj_id is not None:
            out["traj_id"] = traj_id
        return out
