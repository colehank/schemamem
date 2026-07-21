"""End-to-end SchemaMem demo on a diet dialogue, using a scripted mock LLM client
so it runs offline (no API key). To run against a real endpoint, construct
SchemaMemorySystem(model=..., api_base=..., api_key=...) instead of passing client=.

    uv run examples/diet_dialogue.py
"""
from schemamem import SchemaMemorySystem


class _Resp:
    def __init__(self, c):
        self.choices = [type("X", (), {"message": type("M", (), {"content": c})()})()]


class _Chat:
    """Scripted extraction responses; deterministic stand-in for the LLM."""
    def __init__(self, scripts):
        self.scripts, self.i = scripts, 0

    def create(self, **kw):
        sysmsg = kw["messages"][0]["content"]
        if sysmsg.startswith("You are the L1 cleaning stage"):
            # L1 topical pass: echo the raw message back as one user-subject fact,
            # so each MESSAGES entry maps 1:1 to an L2 extraction script below.
            import json as _j
            raw = kw["messages"][-1]["content"].split("RAW DIALOGUE (one episode):\n", 1)[-1]
            return _Resp(_j.dumps({"facts": [{"subject": "user",
                                              "text": raw.rsplit("\n\nJSON:", 1)[0].strip()}]}))
        if sysmsg.startswith("You extract QUANTIFIABLE STATE"):
            # L1 quantifiable-state pass: this dialogue carries no counts or amounts,
            # so it contributes nothing and must not consume a script.
            return _Resp('{"facts": []}')
        if sysmsg.startswith("A user's belief"):      # accommodation rewrite
            return _Resp("pescatarian")
        if sysmsg.startswith("Answer"):                # answering
            return _Resp("Pescatarian now; formerly a strict vegetarian; once ate meat (a birthday).")
        r = self.scripts[self.i]
        self.i += 1
        return _Resp(r)


class _Client:
    def __init__(self, scripts):
        self.chat = type("C", (), {"completions": _Chat(scripts)})()


SCRIPTS = [
    '{"assertions":[{"entity":"user","slot":"diet","value":"strict vegetarian","pred_error":0.0,"candidate_id":null}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"ate meat","pred_error":1.0,"candidate_id":"meat"}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"pescatarian","pred_error":1.0,"candidate_id":"fish"}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"pescatarian","pred_error":1.0,"candidate_id":"fish"}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"pescatarian","pred_error":0.0,"candidate_id":"fish"}]}',
    '{"assertions":[{"entity":"user","slot":"location","value":"Beijing","pred_error":0.0,"candidate_id":null}]}',
]
MESSAGES = [
    "I'm a strict vegetarian, I don't touch meat, eggs or dairy.",
    "Yesterday was my birthday and I couldn't resist my friends, so I had a steak.",
    "My checkup said I'm low on protein, so I've started eating fish.",
    "Had a salmon salad for lunch today.",
    "I'm basically pescatarian now, fish and shrimp yes, red meat no.",
    "By the way, I'm moving to Beijing next month.",
]


def main():
    mem = SchemaMemorySystem(model="mock", client=_Client(SCRIPTS), min_evidence_count=2)
    for m in MESSAGES:
        mem.add_chunk(m)

    context, _groups = mem.retrieve_with_source_groups("diet")
    print("=== schema rendered into context ===")
    print(context)
    print()
    print("Q: What does the user eat now, and what did they used to eat?")
    print("A:", mem.ask_with_retrieved_context(
        "What does the user eat now, and what did they used to eat?", context))
    print()
    print("Q: Has the user ever eaten meat? (the exception a change-only system would drop)")
    print("A:", mem.ask_with_retrieved_context("Has the user ever eaten meat? When?", context))


if __name__ == "__main__":
    main()
