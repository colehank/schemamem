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
    from .core import SchemaGraph, Observation, Action, _differ_in_quantity
    from .prompts import CLEAN_SYS, QUANT_SYS, EXTRACT_SYS, REWRITE_SYS, ANSWER_SYS, SLOT_MERGE_SYS
except ImportError:                     # flat import in dev
    from core import SchemaGraph, Observation, Action, _differ_in_quantity
    from prompts import CLEAN_SYS, QUANT_SYS, EXTRACT_SYS, REWRITE_SYS, ANSWER_SYS, SLOT_MERGE_SYS


def _extract_json(text: str, key: str = "assertions") -> dict:
    """Parse a JSON object from an LLM reply, tolerating truncation.

    On a clean parse, return it. If the reply was cut off mid-array (common when
    max_tokens is hit), salvage every COMPLETE {...} object inside the first array
    under `key` rather than silently dropping the whole reply."""
    start = text.find("{")
    if start == -1:
        return {}
    try:
        return json.loads(text[start:text.rfind("}") + 1])
    except json.JSONDecodeError:
        pass
    # recovery: pull complete top-level objects out of the (possibly truncated) list
    objs, depth, buf, in_str, esc = [], 0, [], False, False
    for ch in text[start + 1:]:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True; buf.append(ch)
        elif ch == "{":
            depth += 1; buf.append(ch)
        elif ch == "}":
            depth -= 1; buf.append(ch)
            if depth == 0:
                try:
                    objs.append(json.loads("".join(buf)))
                except json.JSONDecodeError:
                    pass
                buf = []
        elif depth > 0:
            buf.append(ch)
    return {key: objs}


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
        self.model = model
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
        self.embedding_model = embedding_model
        self._emb_cache: dict = {}
        self.state_path = state_path

        # LLM client (OpenAI-compatible). Injected in tests; otherwise built from
        # explicit args, falling back to the standard OPENAI_* environment variables.
        # base_url is normalized to end in /v1 (the OpenAI SDK posts to <base>/chat/
        # completions, so a gateway root without /v1 silently 404s).
        if client is not None:
            self._client = client
        else:
            import os
            from openai import OpenAI
            key = api_key or os.environ.get("OPENAI_API_KEY") or "EMPTY"
            base = api_base or os.environ.get("OPENAI_BASE_URL")
            if base:
                base = base.rstrip("/")
                if not base.endswith("/v1"):
                    base = base + "/v1"
            self._client = OpenAI(api_key=key, base_url=base)

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

    # ---- LLM helpers (each a single call; mockable) ------------------------
    def _chat(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.0) -> str:
        r = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return r.choices[0].message.content or ""

    def _embed(self, text: str):
        """Embed one string via the OpenAI-compatible embeddings endpoint, cached.
        Returns None if the client has no embeddings support (e.g. a scripted mock),
        so callers degrade to purely structural behaviour."""
        text = (text or "").strip().lower()
        if text in self._emb_cache:
            return self._emb_cache[text]
        try:
            r = self._client.embeddings.create(model=self.embedding_model, input=text)
            vec = r.data[0].embedding
        except Exception:
            vec = None
        self._emb_cache[text] = vec
        return vec

    def _similarity(self, a: str, b: str) -> float:
        """Cosine similarity in [0,1] between two short strings. 0.0 when embeddings
        are unavailable (guards then no-op, preserving pure structural behaviour)."""
        if a == b:
            return 1.0
        va, vb = self._embed(a), self._embed(b)
        if va is None or vb is None:
            return 0.0
        dot = sum(x * y for x, y in zip(va, vb))
        na = sum(x * x for x in va) ** 0.5
        nb = sum(y * y for y in vb) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return max(0.0, dot / (na * nb))

    def _judge_slot(self, new_name: str, new_value, existing: list):
        """LLM same-attribute judge for slot canonicalization. `existing` is a list of
        (slot_name, belief). Returns an existing slot name to merge into, or None to
        keep the new slot. One LLM call; conservative (prefers None on doubt)."""
        if not existing:
            return None
        exist_block = "\n".join(f"- {n}: {b}" for n, b in existing)
        user = (f"ENTITY's EXISTING slots (name: current belief):\n{exist_block}\n\n"
                f"NEW slot -> name: {new_name}, value: {new_value}\n\n"
                f"Is the NEW slot the SAME ATTRIBUTE as one of the existing slots? JSON:")
        parsed = _extract_json(self._chat(SLOT_MERGE_SYS, user, max_tokens=40), key="_")
        chosen = parsed.get("merge_into")
        # accept only an exact existing-slot name
        return chosen if chosen in {n for n, _ in existing} else None

    def _rewrite_belief(self, old_belief, candidate) -> str:
        obs_lines = "\n".join(f"- {o.value} ({o.t})" for o in candidate.observations)
        user = f"OLD belief: {old_belief}\nNew corroborating observations:\n{obs_lines}\n\nNEW belief value:"
        out = self._chat(REWRITE_SYS, user, max_tokens=32).strip()
        # guard against empty / overlong: fall back to latest observed value
        return out if 0 < len(out) <= 60 else candidate.observations[-1].value

    # ---- schema-state view for the extraction prompt -----------------------
    def _schema_state(self) -> dict:
        # Nested {entity: {slot: {belief, candidates}}} so the model never sees a
        # flat "entity.slot" key it might copy back into the entity field.
        state = {}
        for schema in self._graph.entities.values():
            slots = {}
            for slot in schema.slots.values():
                slots[slot.name] = {
                    "belief": slot.belief,
                    "candidates": list(slot.candidates.keys()),
                }
            state[schema.entity] = slots
        return state

    @staticmethod
    def _clean_entity(raw, known=None):
        """Normalize an entity name: a bare person/thing, never a compound
        'Entity.slot' string (a failure mode when schema-state is fed back)."""
        e = (raw or "user").strip()
        if "." in e:                       # 'Caroline.adoption_goal' -> 'Caroline'
            e = e.split(".", 1)[0].strip()
        if known:                          # snap to a known speaker if one matches
            for k in known:
                if k.lower() == e.lower():
                    return k
        return e or "user"

    # ---- L1: raw episode -> self-contained, subject-bound facts ------------
    def _clean_to_facts(self, text: str, known: list) -> list:
        """L1 stage: rewrite a raw dialogue chunk into subject-bound self-contained
        facts. Returns [{"subject": <entity>, "text": <fact>}, ...]."""
        hint = f"PARTICIPANTS (use these exact names as subjects): {known}\n" if known else ""
        facts, seen = [], set()

        def run_pass(sys_prompt, mt, segment):
            u = f"{hint}RAW DIALOGUE (one episode):\n{segment}\n\nJSON:"
            parsed = _extract_json(self._chat(sys_prompt, u, max_tokens=mt), key="facts")
            for f in parsed.get("facts", []):
                ftext = (f.get("text") or "").strip()
                if not ftext:
                    continue
                key = ftext.lower()
                if key in seen:
                    continue
                seen.add(key)
                facts.append({"subject": self._clean_entity(f.get("subject"), known=known),
                              "text": ftext})

        # Two orthogonal L1 passes over the episode:
        #   (a) CLEAN topical/trait pass — run ONCE on the whole episode, because
        #       consolidating "the same attribute" needs a view of the whole chunk.
        #   (b) QUANT quantifiable-state pass — run over sliding WINDOWS of the episode.
        #       A scalar value (a count/amount) buried in the middle of a long chunk is
        #       under-recalled by a single pass whose attention is captured by topical
        #       detail; shortening the context each pass sees restores recall. Recall of
        #       a durable value is monotone under the union of windows (a value seen in
        #       ANY window is kept), and dedup keeps the fact set clean.
        run_pass(CLEAN_SYS, 1200, text)
        for seg in self._l1_windows(text):
            for _ in range(self.l1_quant_samples):
                run_pass(QUANT_SYS, 500, seg)
        return facts

    def _l1_windows(self, text: str) -> list:
        """Split an episode into overlapping windows by turn boundaries so each QUANT
        pass sees a short context. Returns [text] unchanged when windowing is disabled
        (l1_window_chars <= 0) or the episode already fits in one window."""
        w = self.l1_window_chars
        if w <= 0 or len(text) <= w:
            return [text]
        lines = text.split("\n")
        windows, cur, cur_len = [], [], 0
        for ln in lines:
            if cur and cur_len + len(ln) > w:
                windows.append("\n".join(cur))
                # 1-turn overlap so a value split across the boundary is not lost
                cur = cur[-1:]
                cur_len = sum(len(x) for x in cur)
            cur.append(ln)
            cur_len += len(ln)
        if cur:
            windows.append("\n".join(cur))
        return windows

    @staticmethod
    def _coerce_str(v):
        """Flatten a value the LLM may have returned as a nested object into a
        plain string (e.g. {'belief': 'x'} -> 'x')."""
        if isinstance(v, dict):
            for k in ("belief", "value", "text", "name"):
                if isinstance(v.get(k), str):
                    return v[k].strip()
            strs = [str(x) for x in v.values() if isinstance(x, (str, int, float))]
            return strs[0].strip() if strs else ""
        if isinstance(v, list):
            return ", ".join(SchemaMemorySystem._coerce_str(x) for x in v)
        return str(v).strip()

    # ---- L2: cleaned facts -> slot observations -> L3 ingest ---------------
    def _ingest_facts(self, facts: list, episode_id: str, t: str, known: list) -> None:
        """L2 + L3 for one episode's already-cleaned facts. Stateful (reads the
        current schema for slot/candidate reuse and mutates it), so this runs
        sequentially even when L1 is parallelized."""
        if not facts:
            return
        state_json = json.dumps(self._schema_state(), ensure_ascii=False)
        facts_block = "\n".join(f"- [{f['subject']}] {f['text']}" for f in facts)
        hint = f"KNOWN ENTITIES (reuse these exact names): {known}\n" if known else ""
        user = (f"{hint}CURRENT SCHEMA (nested entity -> slot -> belief + open candidate keys):\n"
                f"{state_json}\n\nFACTS (each prefixed with its subject entity in brackets — use "
                f"that exact entity):\n{facts_block}\n\nJSON:")
        # L2 is a network call; a transient empty/failed parse would silently drop
        # this episode's contribution. Retry a couple of times before giving up.
        parsed = {"assertions": []}
        for _ in range(3):
            try:
                parsed = _extract_json(self._chat(EXTRACT_SYS, user, max_tokens=1200), key="assertions")
            except Exception:
                parsed = {"assertions": []}
            if parsed.get("assertions"):
                break

        for a in parsed.get("assertions", []):
            slot = a.get("slot")
            value = self._coerce_str(a.get("value"))
            if not slot or value in ("", "null", "none", "None"):   # skip empty assertions
                continue
            entity = self._clean_entity(a.get("entity"), known=known)
            # Provenance: use the fact index the extractor tied this assertion to; fall back to
            # the first fact whose subject matches the entity, then to the first fact.
            idx = a.get("source_fact_index")
            src = None
            if isinstance(idx, int) and 0 <= idx < len(facts):
                src = facts[idx]["text"]
            if src is None:
                src = next((f["text"] for f in facts if f["subject"] == entity), facts[0]["text"])
            pe = float(a.get("pred_error", 0.0))
            cand = a.get("candidate_id")
            # Numeric override: on a slot that already holds a belief, a value carrying
            # a DIFFERENT quantity (count/amount/page/frequency) is a genuine update, not
            # a "partial" nuance — the LLM tends to mislabel a monotone change ("200→220
            # pages") as r=0.5. Force it to a conflict so it can supersede. This is the
            # same signal the paraphrase guard uses (quantity differs => not a paraphrase),
            # applied at scoring time.
            existing = self._graph.entities.get(entity)
            belief = None
            if existing is not None:
                s_obj = existing.slots.get(str(slot))
                belief = s_obj.belief if s_obj else None
            if belief is not None and _differ_in_quantity(value, str(belief)):
                pe = 1.0
                if not cand:
                    cand = value  # concrete positive value as the candidate key
            obs = Observation(
                entity=entity, slot=str(slot), value=value,
                pred_error=pe, episode_id=episode_id, t=t,
                candidate_id=cand, source_fact=src,
            )
            self._graph.ingest(obs)

    # ---- WRITE: L1 clean -> L2 extract -> L3 ingest ------------------------
    def add_chunk(self, text: str, timestamp: Optional[str] = None,
                  speakers: Optional[list] = None) -> None:
        """Ingest one context chunk as ONE episode: L1 clean -> L2 extract -> L3.
        For many chunks, prefer add_chunks() which parallelizes the L1 stage."""
        self._episode_counter += 1
        episode_id = f"ep{self._episode_counter}"
        t = timestamp or episode_id
        known = speakers or list(self._graph.entities.keys())
        facts = self._clean_to_facts(text, known)
        self._ingest_facts(facts, episode_id, t, known)

    # ---- WRITE (batch): parallel L1, then sequential L2/L3 -----------------
    def add_chunks(self, chunks: list, speakers: Optional[list] = None,
                   max_workers: int = 8) -> None:
        """Ingest many chunks as an ordered episode stream.

        L1 cleaning is stateless per chunk, so it is run CONCURRENTLY across all
        chunks (I/O-bound LLM calls). L2 extraction + L3 arbitration read and mutate
        the shared schema, so they run SEQUENTIALLY in the original chunk order —
        preserving episode ordering and the cross-episode k-count.

        `chunks`: list of str, or list of (text, timestamp) tuples.
        """
        from concurrent.futures import ThreadPoolExecutor

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
            self._ingest_facts(facts, episode_id, ts or episode_id, base_known)

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

    def _render_slot_dual(self, entity: str, slot) -> str:
        """Dual-trace rendering of one slot: gist (belief + evolution) over
        verbatim (time-anchored source facts). This is what the retriever hands
        the answerer — the gist gives the current value, the verbatim ledger
        gives the specific wording / time / count that a precise question needs."""
        out = [f"[{entity}] {slot.name}:"]
        if slot.belief is not None:
            out.append(f"  current: {slot.belief}" + (f"  (as of {slot.belief_t})" if slot.belief_t else ""))
        for old, when in slot.superseded:
            out.append(f"  previously: {old}  (superseded {when})")
        for o in slot.exceptions:
            out.append(f"  exception: {o.value}  ({o.t})")
        # verbatim layer: the original time-anchored facts behind this slot
        if slot.ledger:
            out.append("  evidence:")
            for o in slot.ledger:
                src = (o.source_fact or o.value or "").strip()
                if src:
                    out.append(f"    - ({o.t}) {src}")
        return "\n".join(out)

    def retrieve_with_source_groups(self, query: str, k: Optional[int] = None):
        """Return (context_text, source_id_groups).

        Query-ranked dual-trace retrieval: score every slot by embedding
        similarity between the query and the slot's descriptor (name + belief +
        recent evidence), take the top-k, and render each in dual-trace form
        (gist over verbatim). Falls back to rendering all slots when embeddings
        are unavailable. source_id_groups groups the source facts backing each
        rendered slot (rank order), for recall@k metrics.
        """
        self.finalize()
        k = k or self.retrieve_k
        # collect (entity, slot) pairs
        pairs = [(sch.entity, slot) for sch in self._graph.entities.values()
                 for slot in sch.slots.values()]
        if not pairs:
            return "", []

        def descriptor(entity, slot):
            parts = [slot.name.replace("_", " "), slot.belief or ""]
            parts += [o.value for o in slot.ledger[-3:]]
            return f"{entity} " + " ".join(str(p) for p in parts if p)

        ranked = pairs
        try:
            qv = self._embed(query)
            import math
            def cos(a, b):
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
                return dot / (na * nb) if na and nb else 0.0
            scored = [((e, s), cos(qv, self._embed(descriptor(e, s)))) for e, s in pairs]
            scored.sort(key=lambda z: z[1], reverse=True)
            ranked = [p for p, _ in scored[:k]]
        except Exception:
            ranked = pairs[:k]

        blocks, groups = [], []
        for entity, slot in ranked:
            blocks.append(self._render_slot_dual(entity, slot))
            srcs = [o.source_fact for o in slot.ledger if o.source_fact]
            if srcs:
                groups.append(srcs)
        return "\n".join(blocks), groups

    # ---- ANSWER ------------------------------------------------------------
    def ask_with_retrieved_context(self, query: str, context: str) -> str:
        user = f"Memory context:\n{context}\n\nQuestion: {query}\nAnswer:"
        return self._chat(ANSWER_SYS, user, max_tokens=256).strip()
