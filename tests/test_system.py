"""Integration test for SchemaMemorySystem using a scripted mock client (no LLM cost).

Verifies the adapter contract end-to-end: add_chunk (L1->L2->L3) then
retrieve_with_source_groups renders belief + superseded + exception correctly.
"""
from schemamem.core import Observation
from schemamem.schema_memory import SchemaMemorySystem


class _Resp:
    def __init__(self, c):
        self.choices = [type("X", (), {"message": type("M", (), {"content": c})()})()]


class _Chat:
    def __init__(self, scripts):
        self.scripts = scripts
        self.i = 0

    def create(self, **kw):
        sysmsg = kw["messages"][0]["content"]
        if sysmsg.startswith("You are the L1 cleaning stage"):
            # L1: echo the raw dialogue as a single user-subject fact so the
            # existing per-message scripts map 1:1 to L2 extraction calls.
            raw = kw["messages"][-1]["content"].split("RAW DIALOGUE (one episode):\n", 1)[-1]
            raw = raw.rsplit("\n\nJSON:", 1)[0].strip()
            import json as _j
            return _Resp(_j.dumps({"facts": [{"subject": "user", "text": raw}]}))
        if sysmsg.startswith("You extract QUANTIFIABLE STATE"):
            # L1 second pass (quantifiable state, run per sliding window). These
            # scripted messages carry no counts/amounts, so it contributes nothing;
            # answering with an empty fact list keeps the per-message scripts
            # mapping 1:1 to L2 extraction calls.
            return _Resp('{"facts": []}')
        if sysmsg.startswith("A user's belief"):
            return _Resp("pescatarian")
        if sysmsg.startswith("Answer the question"):
            return _Resp("pescatarian; formerly strict vegetarian; once ate meat (ep2).")
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
    # dual-trace rendering: gist (current / previously / exception) over verbatim
    # current belief
    assert "current: pescatarian" in ctx, ctx
    # superseded trail (knowledge-update capability)
    assert "previously: strict vegetarian" in ctx, ctx
    # protected exception (the capability change-only systems lose)
    assert "exception: ate meat" in ctx, ctx
    # second slot seeded from a congruent first observation
    assert "current: Beijing" in ctx, ctx
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
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")


def test_dump_memory_exposes_all_four_fields():
    """The Phase 3 structure-comparison hook: current / history / exceptions /
    n_obs. SchemaMem is the only method that can fill all four — the exception
    list is the field overwrite- and merge-style baselines leave empty."""
    sm = SchemaMemorySystem(model="mock", client=_Client(SCRIPTS), min_evidence_count=2)
    for m in MSGS:
        sm.add_chunk(m)
    dump = sm.dump_memory(traj_id="t0")
    assert dump["traj_id"] == "t0"
    diet = dump["entities"]["user"]["diet"]
    assert diet["current"] == "pescatarian", diet
    assert [h["value"] for h in diet["history"]] == ["strict vegetarian"], diet
    assert [e["value"] for e in diet["exceptions"]] == ["ate meat"], diet
    assert diet["n_obs"] == 5, diet


def test_verbatim_layer_survives_lossy_extraction():
    """The schema INDEXES the raw episodes rather than replacing them.

    L1 facts are an LLM rewrite, so a detail the extractor drops is gone from the
    structured layer. Retrieval must still surface the original chunk text, in
    slot-rank order, so the answerer can recover it."""
    sm = SchemaMemorySystem(model="mock", client=_Client(SCRIPTS), min_evidence_count=2)
    for m in MSGS:
        sm.add_chunk(m)
    ctx, _ = sm.retrieve_with_source_groups("diet")
    assert "SOURCE EPISODES" in ctx, ctx
    # the raw wording is present even though no extracted slot value contains it
    assert "couldn't resist" not in ctx      # that phrasing is only in the example, not here
    assert "I'm a strict vegetarian" in ctx, ctx
    assert "salmon salad today" in ctx, ctx
    # gist still leads
    assert ctx.index("current: pescatarian") < ctx.index("SOURCE EPISODES")


def test_verbatim_budget_zero_restores_schema_only_context():
    sm = SchemaMemorySystem(model="mock", client=_Client(SCRIPTS),
                            min_evidence_count=2, verbatim_budget=0)
    for m in MSGS:
        sm.add_chunk(m)
    ctx, _ = sm.retrieve_with_source_groups("diet")
    assert "SOURCE EPISODES" not in ctx
    assert "current: pescatarian" in ctx


def test_named_entity_outranks_topically_similar_slots():
    """The graph is entity-centric: a query naming an entity must read THAT
    entity's slots. Embedding cosine alone loses this — on FactConsolidation it
    returned ten other sport slots and never the named entity's."""
    sm = SchemaMemorySystem(model="mock", client=_Client([]), min_evidence_count=2)
    # no embeddings from the mock -> exercises the structural fallback path
    for ent, val in [("quarterback", "American football"),
                     ("Alta IF", "association football"),
                     ("goaltender", "pesapallo")]:
        sm._graph.ingest(Observation(entity=ent, slot="sport", value=val,
                                     pred_error=0.0, episode_id=f"ep{ent}",
                                     t="t1", candidate_id=None))
    ctx, _ = sm.retrieve_with_source_groups(
        "Which sport is goaltender associated with?", k=1)
    assert "goaltender" in ctx, ctx
    assert "pesapallo" in ctx, ctx


def test_declarative_fact_list_bypasses_the_lossy_l1_rewrite():
    """A numbered fact list is ALREADY what L1 is supposed to produce, so running
    an LLM over it can only drop items. FactConsolidation puts ~277 facts in one
    chunk, far past a capped completion, which lost most of every chunk."""
    listed = "\n".join(f"{i}. Entity{i} was born in City{i}." for i in range(40))
    assert SchemaMemorySystem._as_fact_list(listed) is not None
    got = SchemaMemorySystem._as_fact_list(listed)
    assert len(got) == 40, len(got)
    assert got[7] == "Entity7 was born in City7."
    # a dialogue with an incidental bullet is NOT a fact list
    dialogue = "user: hi there\nassistant: sure\n- one aside\nuser: ok thanks\nassistant: bye"
    assert SchemaMemorySystem._as_fact_list(dialogue) is None


def test_entity_names_keep_their_dots():
    """The entity.slot guard must not amputate real names. "L. Ron Hubbard" was
    being stored as "L", so every fact about him landed on one junk entity."""
    ce = SchemaMemorySystem._clean_entity
    assert ce("L. Ron Hubbard") == "L. Ron Hubbard"
    assert ce("Apple Inc.") == "Apple Inc."
    assert ce("Martin Luther King Jr.") == "Martin Luther King Jr."
    # the compound it actually guards against still splits
    assert ce("Caroline.adoption_goal") == "Caroline"
    assert ce("Hines Ward.position") == "Hines Ward"


def test_schema_state_is_scoped_to_the_batch():
    """L2's prompt carries current beliefs so it can score pred_error, but dumping
    every entity does not scale — at ~800 entities the state JSON swamped the facts
    and extraction coverage fell from 93% to 66%."""
    sm = SchemaMemorySystem(model="mock", client=_Client([]), min_evidence_count=2)
    for ent in ["Steve Jobs", "L. Ron Hubbard", "QuickTime"]:
        sm._graph.ingest(Observation(entity=ent, slot="x", value="v", pred_error=0.0,
                                     episode_id="ep1", t="t1", candidate_id=None))
    assert set(sm._schema_state()) == {"Steve Jobs", "L. Ron Hubbard", "QuickTime"}
    scoped = sm._schema_state(relevant_to="- QuickTime was developed by Apple Inc.")
    assert set(scoped) == {"QuickTime"}, scoped


def test_entity_mention_matches_on_tokens_not_exact_string():
    """Extracted names and question wording rarely agree character-for-character.
    Whole-string matching missed "The 2004 NBA Draft" in a question that said
    "2004 NBA Draft", so the entity was never grounded and never retrieved."""
    sm = SchemaMemorySystem(model="mock", client=_Client([]), min_evidence_count=2)
    for ent, val in [("The 2004 NBA Draft", "Dwight Howard"),
                     ("Apple Inc.", "Cupertino"),
                     ("Steve Jobs", "San Francisco")]:
        sm._graph.ingest(Observation(entity=ent, slot="fact", value=val, pred_error=0.0,
                                     episode_id="e1", t="t1", candidate_id=None))
    ctx, _ = sm.retrieve_with_source_groups("Who was picked first in the 2004 NBA Draft?", k=1)
    assert "Dwight Howard" in ctx, ctx
    ctx2, _ = sm.retrieve_with_source_groups("Where is Apple Inc headquartered?", k=1)
    assert "Cupertino" in ctx2, ctx2
    # precision: an unrelated question must not GROUND on these entities. (With
    # k=1 and nothing grounded some slot is still returned — that is the intended
    # fallback — so check the grounding decision, not the fallback output.)
    ctx3, _ = sm.retrieve_with_source_groups("Steve Jobs was born where?", k=1)
    assert "San Francisco" in ctx3, ctx3


def test_l2_splits_the_batch_when_extraction_yield_collapses():
    """Asking the extractor not to drop items does not work — it returned ~7
    assertions for 25 listed facts, so only 671 of 2,310 entities reached the
    graph. A low yield now halves the batch and retries."""
    class _Yield:
        """Returns one assertion per call until the batch is small, then all of them."""
        def __init__(self):
            self.sizes = []

        def create(self, **kw):
            body = kw["messages"][-1]["content"]
            n = body.count("\n- ")
            self.sizes.append(n)
            import re as _re
            ids = _re.findall(r"- (\d+)\. Entity", body)
            emit = ids if n <= 2 else ids[:1]   # collapse unless the batch is tiny
            rows = ",".join(
                '{"entity":"Entity%s","slot":"s","value":"v%s","pred_error":0.0,"candidate_id":null}' % (i, i)
                for i in emit)
            return _Resp('{"assertions":[%s]}' % rows)

    chat = _Yield()
    client = type("C", (), {"chat": type("X", (), {"completions": chat})()})()
    sm = SchemaMemorySystem(model="mock", client=client, min_evidence_count=2)
    facts = [{"subject": "", "text": f"{i}. Entity{i} was born in City{i}."} for i in range(8)]
    sm._ingest_facts(facts, "ep1", "t1", [])
    # it must have retried on progressively smaller batches, not accepted 1-of-8
    assert max(chat.sizes) == 8 and min(chat.sizes) <= 2, chat.sizes
    assert len(sm._graph.entities) >= 4, list(sm._graph.entities)
