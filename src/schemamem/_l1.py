"""L1: raw episode -> self-contained, subject-bound facts."""
from __future__ import annotations

import re
from typing import Optional

try:
    from .prompts import CLEAN_SYS, QUANT_SYS
    from ._util import _extract_json
except ImportError:  # flat import when vendored
    from prompts import CLEAN_SYS, QUANT_SYS
    from _util import _extract_json


class L1Mixin:
    @staticmethod
    def _clean_entity(raw, known=None):
        """Normalize an entity name: a bare person/thing, never a compound
        'Entity.slot' string (a failure mode when schema-state is fed back)."""
        e = (raw or "user").strip()
        # 'Caroline.adoption_goal' -> 'Caroline', but a dot is also part of many real
        # names ("L. Ron Hubbard", "Apple Inc.", "Martin Luther King Jr."). Only split
        # when it looks like the entity.slot compound this guards against: no space
        # around the dot and a slot-shaped suffix (lowercase word / snake_case).
        m = re.match(r"^([^.\s][^.]*?)\.([a-z][a-z0-9_]*)$", e)
        if m:
            e = m.group(1).strip()
        if known:                          # snap to a known speaker if one matches
            for k in known:
                if k.lower() == e.lower():
                    return k
        return e or "user"

    # ---- L1: raw episode -> self-contained, subject-bound facts ------------
    # A chunk that is already a list of self-contained declarative facts (numbered,
    # bulleted, or one-per-line) needs no L1 rewrite: L1's job is to PRODUCE such
    # facts, so running an LLM over them can only lose some. On FactConsolidation a
    # 4096-token chunk holds ~277 numbered facts, far past what a single capped
    # completion can re-emit, so the rewrite silently dropped most of every chunk.
    _LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(.+?)\s*$")
    @classmethod
    def _as_fact_list(cls, text: str) -> Optional[list]:
        """Return the list items if `text` is predominantly a declarative list,
        else None. Conservative: needs several items and near-total coverage, so
        a dialogue that happens to contain a bulleted aside is not misread."""
        lines = [ln for ln in (text or "").split("\n") if ln.strip()]
        if len(lines) < 5:
            return None
        items = [m.group(1) for m in (cls._LIST_ITEM.match(ln) for ln in lines) if m]
        if len(items) < 5 or len(items) < 0.8 * len(lines):
            return None
        return [i for i in items if len(i) > 3]
    def _clean_to_facts(self, text: str, known: list) -> list:
        """L1 stage: rewrite a raw dialogue chunk into subject-bound self-contained
        facts. Returns [{"subject": <entity>, "text": <fact>}, ...]."""
        listed = self._as_fact_list(text)
        if listed is not None:
            # already self-contained facts — pass through verbatim, lossless.
            return [{"subject": "", "text": s} for s in listed]

        hint = f"PARTICIPANTS (use these exact names as subjects): {known}\n" if known else ""
        facts, seen = [], set()

        def call_pass(spec):
            sys_prompt, mt, segment = spec
            u = f"{hint}RAW DIALOGUE (one episode):\n{segment}\n\nJSON:"
            return _extract_json(self._chat(sys_prompt, u, max_tokens=mt), key="facts")

        def collect(parsed):
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
        # The passes are independent, so they go out CONCURRENTLY and are collected
        # in a FIXED order — results stay deterministic (dedup is order-sensitive)
        # while latency drops to the slowest single call instead of their sum. This
        # is the dominant cost of ingestion: MemBench rebuilds memory once per
        # trajectory, so serial passes put the full benchmark out of reach.
        specs = [(CLEAN_SYS, 1200, text)]
        for seg in self._l1_windows(text):
            for _ in range(self.l1_quant_samples):
                specs.append((QUANT_SYS, 500, seg))
        if len(specs) == 1:
            collect(call_pass(specs[0]))
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(specs))) as ex:
                for parsed in list(ex.map(call_pass, specs)):
                    collect(parsed)
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
            return ", ".join(L1Mixin._coerce_str(x) for x in v)
        return str(v).strip()
