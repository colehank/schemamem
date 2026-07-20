"""Integration test for SchemaMemorySystem using a scripted mock client (no LLM cost).

Verifies the adapter contract end-to-end: add_chunk (L1->L2->L3) then
retrieve_with_source_groups renders belief + superseded + exception correctly.
"""
from schemamem.schema_memory import SchemaMemorySystem


class _Resp:
    def __init__(self, c):
        self.choices = [type("X", (), {"message": type("M", (), {"content": c})()})()]


class _Chat:
    def __init__(self, scripts):
        self.scripts = scripts; self.i = 0

    def create(self, **kw):
        sysmsg = kw["messages"][0]["content"]
        if sysmsg.startswith("You are the L1 cleaning stage"):
            # L1: echo the raw dialogue as a single user-subject fact so the
            # existing per-message scripts map 1:1 to L2 extraction calls.
            raw = kw["messages"][-1]["content"].split("RAW DIALOGUE (one episode):\n", 1)[-1]
            raw = raw.rsplit("\n\nJSON:", 1)[0].strip()
            import json as _j
            return _Resp(_j.dumps({"facts": [{"subject": "user", "text": raw}]}))
        if sysmsg.startswith("A user's belief"):
            return _Resp("pescatarian")
        if sysmsg.startswith("Answer the question"):
            return _Resp("pescatarian; formerly strict vegetarian; once ate meat (ep2).")
        r = self.scripts[self.i]; self.i += 1
        return _Resp(r)


class _Client:
    def __init__(self, scripts):
        self.chat = type("C", (), {"completions": _Chat(scripts)})()


SCRIPTS = [
    '{"assertions":[{"entity":"user","slot":"diet","value":"strict vegetarian","pred_error":0.0,"candidate_id":null}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"ate meat","pred_error":1.0,"candidate_id":"meat"}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"pescatarian","pred_error":1.0,"candidate_id":"fish"}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"pescatarian","pred_error":1.0,"candidate_id":"fish"}]}',
    '{"assertions":[{"entity":"user","slot":"diet","value":"pescatarian","pred_error":1.0,"candidate_id":"fish"}]}',
    '{"assertions":[{"entity":"user","slot":"location","value":"Beijing","pred_error":0.0,"candidate_id":null}]}',
]
MSGS = [
    "I'm a strict vegetarian, I don't touch meat, eggs or dairy.",
    "Yesterday was my birthday and I had a steak.",
    "I've started eating fish.",
    "Had a salmon salad today.",
    "I'm basically pescatarian now.",
    "I'm moving to Beijing next month.",
]


def test_full_pipeline_renders_all_three_outcomes():
    sm = SchemaMemorySystem(model="mock", client=_Client(SCRIPTS), min_evidence_count=2)
    for m in MSGS:
        sm.add_chunk(m)
    ctx, groups = sm.retrieve_with_source_groups("diet")
    # current belief
    assert "pescatarian (current)" in ctx, ctx
    # superseded trail (knowledge-update capability)
    assert "strict vegetarian (was, superseded" in ctx, ctx
    # protected exception (the capability change-only systems lose)
    assert "ate meat (exception" in ctx, ctx
    # second slot seeded from a congruent first observation
    assert "Beijing (current)" in ctx, ctx
    # source groups exist for recall metrics
    assert len(groups) >= 1


def test_unseen_entity_yields_empty_context():
    """A query before any chunk => empty context => harness falls back to pure RAG."""
    sm = SchemaMemorySystem(model="mock", client=_Client([]), min_evidence_count=2)
    ctx, groups = sm.retrieve_with_source_groups("anything")
    assert ctx == ""
    assert groups == []


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}"); passed += 1
        except Exception:
            print(f"FAIL {t.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
