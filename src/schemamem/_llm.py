"""LLM + embedding helpers (each a single, mockable call)."""
from __future__ import annotations


try:
    from .prompts import REWRITE_SYS, SLOT_MERGE_SYS
    from ._util import _extract_json
except ImportError:  # flat import when vendored
    from prompts import REWRITE_SYS, SLOT_MERGE_SYS
    from _util import _extract_json


class LLMMixin:
    def _chat(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.0) -> str:
        """One chat call, retried on transient gateway failures.

        A shared gateway returns 5xx / rate-limit errors under load (a 503
        'no available channel' burst killed several hour-long runs), and an
        unhandled one propagates out of add_chunk and loses the whole run.
        Back off and retry; only give up after the last attempt.
        """
        import time
        for attempt in range(5):
            try:
                r = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    temperature=temperature, max_tokens=max_tokens,
                )
                return r.choices[0].message.content or ""
            except Exception as e:                       # noqa: BLE001 - gateway-agnostic
                status = getattr(e, "status_code", None)
                # A 4xx other than rate-limiting is the gateway's final answer —
                # a content-filter rejection never succeeds on retry. Retrying it
                # five times and then raising killed whole runs over one prompt.
                # Degrade instead: this chunk contributes nothing, the run goes on.
                if isinstance(status, int) and 400 <= status < 500 and status != 429:
                    return ""
                if attempt == 4:
                    return ""
                time.sleep(2 ** attempt)                 # 1, 2, 4, 8s
        return ""
    def _embed(self, text: str):
        """Embed one string via the OpenAI-compatible embeddings endpoint, cached.
        Returns None if the client has no embeddings support (e.g. a scripted mock),
        so callers degrade to purely structural behaviour."""
        text = (text or "").strip().lower()
        if text in self._emb_cache:
            return self._emb_cache[text]
        try:
            r = self._embed_client.embeddings.create(model=self.embedding_model, input=text)
            vec = r.data[0].embedding
        except Exception:
            vec = None
        self._emb_cache[text] = vec
        return vec
    def _embed_many(self, texts: list) -> list:
        """Embed many strings in as few requests as possible, cached.

        The embeddings endpoint takes a LIST input, so ranking N slots costs one
        request instead of N. Ranking every slot one-at-a-time dominated query
        latency (a few hundred slots => a few hundred sequential round trips).
        Falls back to per-item `_embed` when a gateway rejects batch input, so
        behaviour is unchanged wherever batching is unavailable.
        """
        norm = [(t or "").strip().lower() for t in texts]
        missing = [t for t in dict.fromkeys(norm) if t not in self._emb_cache]
        for i in range(0, len(missing), self._embed_batch):
            batch = missing[i:i + self._embed_batch]
            try:
                r = self._embed_client.embeddings.create(model=self.embedding_model, input=batch)
                vecs = [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
            except Exception:
                vecs = []
            if len(vecs) == len(batch):
                for t, v in zip(batch, vecs):
                    self._emb_cache[t] = v
            else:                            # batch unsupported/partial -> one at a time
                for t in batch:
                    self._embed(t)
        return [self._emb_cache.get(t) for t in norm]
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
