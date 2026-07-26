"""READ: render the schema into retrieval context + timeline view."""
from __future__ import annotations

import re
from typing import Optional


class RetrievalMixin:
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

    # A query is not always a question. Benchmarks that model realistic input (and
    # real users) bury the real request under conversational filler: MemBench-noisy
    # prefixes several sentences of chatter, INCLUDING decoy questions, before "what
    # I truly wanted to clarify is, <question>". Keying retrieval on the whole string
    # lets the filler drive both the embedding and the entity grounding, so the
    # ranked slots answer the chatter rather than the request.
    _ASK_CUE = re.compile(
        r"(?:wanted to (?:clarify|ask|know)|my question|really asking|actually)"
        r"(?:\s+is)?\s*[,:.]?\s*",
        re.I)
    @classmethod
    def _retrieval_key(cls, query: str) -> str:
        """The part of `query` retrieval should actually match on."""
        q = (query or "").strip()
        if len(q) < 200:
            return q
        m = list(cls._ASK_CUE.finditer(q))
        if m:                                   # explicit "what I really meant is ..."
            tail = q[m[-1].end():].strip()
            if len(tail) > 15:
                return tail
        # otherwise the LAST question plus whatever follows it (answer options)
        parts = [i for i, ch in enumerate(q) if ch == "?"]
        if len(parts) >= 2:
            start = q.rfind("?", 0, parts[-1]) + 1
            tail = q[start:].strip()
            if len(tail) > 15:
                return tail
        return q
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
        query = self._retrieval_key(query)
        # collect (entity, slot) pairs
        pairs = [(sch.entity, slot) for sch in self._graph.entities.values()
                 for slot in sch.slots.values()]
        if not pairs:
            return "", []

        def descriptor(entity, slot):
            parts = [slot.name.replace("_", " "), slot.belief or ""]
            parts += [o.value for o in slot.ledger[-3:]]
            return f"{entity} " + " ".join(str(p) for p in parts if p)

        # ENTITY GROUNDING. The graph is entity-centric, so a query that NAMES an
        # entity should read that entity's slots — not whatever embeds nearest.
        # Cosine over topical descriptors reliably loses this: asked which sport
        # the goaltender plays, it returned ten other sport slots and never the
        # goaltender's, because they are all "about sport". Resolve the mention
        # first, rank second; this is what having an entity index is for.
        # Match on TOKENS, not on the whole string: the extracted name and the
        # question rarely agree character-for-character ("The 2004 NBA Draft" vs
        # "2004 NBA Draft", "Apple Inc." vs "Apple Inc"). Requiring every
        # significant token of the entity to appear keeps that precise — a
        # two-token name must have both tokens present — while surviving
        # articles, punctuation and suffixes.
        _STOP = {"the", "a", "an", "of", "in", "at", "on", "for", "and", "is", "was"}
        q_tokens = set(re.findall(r"[a-z0-9]+", (query or "").lower()))

        def _mentioned(entity: str) -> bool:
            toks = [t for t in re.findall(r"[a-z0-9]+", (entity or "").lower())
                    if t not in _STOP]
            if not toks or sum(len(t) for t in toks) < 3:
                return False
            return all(t in q_tokens for t in toks)

        ranked = pairs
        try:
            # one batched request for the query + every slot descriptor, instead of
            # one round trip per slot (which dominated query latency).
            vecs = self._embed_many([query] + [descriptor(e, s) for e, s in pairs])
            qv, slot_vecs = vecs[0], vecs[1:]
            if qv is None:
                raise ValueError("no query embedding")
            import math
            def cos(a, b):
                if a is None or b is None:
                    return 0.0
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a))
                nb = math.sqrt(sum(y * y for y in b))
                return dot / (na * nb) if na and nb else 0.0
            # +1.0 for a named entity puts every mentioned entity's slots above
            # every unmentioned one, while cosine still orders within each band.
            scored = [(p, cos(qv, sv) + (1.0 if _mentioned(p[0]) else 0.0))
                      for p, sv in zip(pairs, slot_vecs)]
            scored.sort(key=lambda z: z[1], reverse=True)
            ranked = [p for p, _ in scored[:k]]
        except Exception:
            # no embeddings: entity grounding alone still beats arbitrary order
            named = [p for p in pairs if _mentioned(p[0])]
            ranked = (named + [p for p in pairs if p not in named])[:k]

        blocks, groups = [], []
        for entity, slot in ranked:
            blocks.append(self._render_slot_dual(entity, slot))
            srcs = [o.source_fact for o in slot.ledger if o.source_fact]
            if srcs:
                groups.append(srcs)
        gist = "\n".join(blocks)

        # VERBATIM LAYER — the schema names WHICH episodes matter; the episodes
        # themselves supply the wording. Without this the answerer only ever sees
        # an LLM rewrite of the source, so any detail L1 dropped is unrecoverable.
        # Episodes are emitted in slot-rank order (best-matching slot first) and
        # capped by verbatim_budget characters.
        if self.verbatim_budget > 0 and self._episodes:
            seen, chosen = set(), []
            for _, slot in ranked:
                for o in slot.ledger:
                    ep = o.episode_id
                    if ep in seen or ep not in self._episodes:
                        continue
                    seen.add(ep)
                    chosen.append(ep)
            spent, verbatim = 0, []
            for ep in chosen:
                t, text = self._episodes[ep]
                text = (text or "").strip()
                if not text:
                    continue
                if spent + len(text) > self.verbatim_budget:
                    room = self.verbatim_budget - spent
                    if room < 200:            # not worth a fragment
                        break
                    text = text[:room] + " …"
                verbatim.append(f"--- episode {ep} ({t}) ---\n{text}")
                spent += len(text)
                if spent >= self.verbatim_budget:
                    break
            if verbatim:
                gist = (gist + "\n\nSOURCE EPISODES (verbatim, most relevant first):\n"
                        + "\n".join(verbatim))
        return gist, groups

    # ---- TIMELINE VIEW -----------------------------------------------------
    _TEMPORAL_HINTS = ("when", "before", "after", "first", "last", "earlier",
                       "later", "how long", "since", "until", "order", "date",
                       "recent", "ago", "which came", "prior to", "following")
    @staticmethod
    def _parse_t(t: str):
        """Best-effort parse of a timestamp string to a sortable key. Returns a
        datetime, or None when unparseable. Handles the LoCoMo/LongMemEval forms
        seen in the data (e.g. '2023/10/10 (Tue) 23:08', '2023-06-12')."""
        import re as _re
        import datetime as _dt
        if not t:
            return None
        m = _re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(t))
        if not m:
            return None
        y, mo, d = (int(g) for g in m.groups())
        hm = _re.search(r"(\d{1,2}):(\d{2})", str(t))
        hh, mm = (int(hm.group(1)), int(hm.group(2))) if hm else (0, 0)
        try:
            return _dt.datetime(y, mo, d, hh, mm)
        except ValueError:
            return None
    def timeline_view(self, k: Optional[int] = None) -> str:
        """A SECOND view over the same observation history, organized by TIME
        rather than by attribute. The per-slot belief view answers 'what is the
        current value of X'; this view answers 'in what order did events happen'.
        Every observation already carries a timestamp; we flatten observations
        across all slots into one chronologically-sorted event line. This is a
        derived view (no new storage, no new edges), not a separate memory.
        Temporal reasoning is the one axis the attribute-organized schema
        compresses away, and this view restores it on demand."""
        self.finalize()
        events = []
        for sch in self._graph.entities.values():
            for slot in sch.slots.values():
                for o in slot.ledger:
                    key = self._parse_t(o.t)
                    label = (o.source_fact or f"{sch.entity} {slot.name.replace('_',' ')}: {o.value}").strip()
                    events.append((key, o.t, label))
        # keep only time-anchored events; sort chronologically (unparseable last)
        dated = [e for e in events if e[0] is not None]
        dated.sort(key=lambda e: e[0])
        if k:
            dated = dated[:k]
        lines = [f"  ({t}) {label}" for _, t, label in dated]
        return "Timeline (events in chronological order):\n" + "\n".join(lines) if lines else ""
    def _is_temporal(self, query: str) -> bool:
        q = query.lower()
        return any(h in q for h in self._TEMPORAL_HINTS)
