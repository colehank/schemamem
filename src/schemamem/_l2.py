"""L2: cleaned facts -> slot observations -> L3 ingest, + the schema-state view."""
from __future__ import annotations

import json
from typing import Optional

try:
    from .core import Observation, _differ_in_quantity
    from .prompts import EXTRACT_SYS
    from ._util import _extract_json
except ImportError:  # flat import when vendored
    from core import Observation, _differ_in_quantity
    from prompts import EXTRACT_SYS
    from _util import _extract_json


class L2Mixin:
    def _schema_state(self, relevant_to: Optional[str] = None) -> dict:
        # Nested {entity: {slot: {belief, candidates}}} so the model never sees a
        # flat "entity.slot" key it might copy back into the entity field.
        #
        # L2 needs current beliefs to score pred_error, but only for entities the
        # batch actually mentions. Dumping the whole graph does not scale: by ~800
        # entities the state JSON dwarfs the facts it is meant to contextualise, and
        # measured extraction coverage fell from 93% to 66% as the graph grew.
        # `relevant_to` (the batch's fact text) restricts it, so the prompt stays
        # the same size however large the memory becomes.
        hay = (relevant_to or "").lower()
        state = {}
        for schema in self._graph.entities.values():
            if relevant_to is not None:
                e = schema.entity.lower()
                if len(e) < 3 or e not in hay:
                    continue
            slots = {}
            for slot in schema.slots.values():
                slots[slot.name] = {
                    "belief": slot.belief,
                    "candidates": list(slot.candidates.keys()),
                }
            state[schema.entity] = slots
        return state
    def _ingest_facts(self, facts: list, episode_id: str, t: str, known: list) -> None:
        """L2 + L3 for one episode's already-cleaned facts. Stateful (reads the
        current schema for slot/candidate reuse and mutates it), so this runs
        sequentially even when L1 is parallelized."""
        if not facts:
            return
        # One assertion costs ~40 output tokens, so a single capped completion can
        # only carry ~25 of them. A dense chunk (a FactConsolidation page holds
        # ~277 facts) silently lost everything past the cap. Split into batches
        # small enough that the reply fits, and ingest them in order so the
        # cross-episode vote and the schema state stay correct.
        if len(facts) > self._l2_batch:
            for i in range(0, len(facts), self._l2_batch):
                self._ingest_facts(facts[i:i + self._l2_batch], episode_id, t, known)
            return
        # A fact with no subject is one L1 passed through verbatim (a declarative
        # list item). Do NOT invent one: the bracket tells L2 to use that exact
        # entity, and an empty subject normalises to "user", which would attribute
        # every world fact to the speaker. Leave it unprefixed so L2 reads the
        # subject off the sentence, per the narrative-input rule.
        facts_block = "\n".join(
            (f"- [{f['subject']}] {f['text']}" if f.get("subject") else f"- {f['text']}")
            for f in facts)
        state_json = json.dumps(self._schema_state(relevant_to=facts_block),
                                ensure_ascii=False)
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

        # COVERAGE ENFORCEMENT. Asking the model not to drop items is not reliable:
        # with the coverage rule in place it still returned ~7 assertions for 25
        # listed facts, so only 671 of 2,310 FactConsolidation entities reached the
        # graph. A fact that yields no assertion is an entity the system can never
        # answer about, and nothing downstream can recover it. When the yield is
        # far below the input count, halve the batch and retry — a shorter list is
        # harder to summarise away — until batches of one, where dropping is
        # unambiguous rather than a judgement call.
        got = len(parsed.get("assertions", []))
        if len(facts) > 1 and got < 0.6 * len(facts):
            mid = len(facts) // 2
            self._ingest_facts(facts[:mid], episode_id, t, known)
            self._ingest_facts(facts[mid:], episode_id, t, known)
            return

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
