"""ANSWER: generate the final answer over rendered schema context."""
from __future__ import annotations


try:
    from .prompts import ANSWER_SYS
except ImportError:  # flat import when vendored
    from prompts import ANSWER_SYS


class AnswerMixin:
    def ask_with_retrieved_context(self, query: str, context: str,
                                   include_timeline: bool = False) -> str:
        # timeline_view() is a valid second (time-organized) view, but a full
        # chronological dump dilutes the context and hurt accuracy in an A/B on
        # temporal instances (the failing cases were upstream extraction misses,
        # not missing time order). It is therefore OFF by default and opt-in;
        # a query-relevant timeline (filter events to the queried entity/slot
        # before ordering) is the right form and is left as future work.
        if include_timeline and self._is_temporal(query):
            tl = self.timeline_view()
            if tl:
                context = f"{context}\n\n{tl}"
        user = f"Memory context:\n{context}\n\nQuestion: {query}\nAnswer:"
        return self._chat(ANSWER_SYS, user, max_tokens=256).strip()
