"""Benchmark-specific adapters that reshape raw benchmark data into a form
SchemaMem's `add_chunk` can consume cleanly.

Rationale (2026-07-21). SchemaMem's L1 extraction was designed for dialogue,
where the SUBJECT of a fact is normally the speaker (or someone the speaker
talks about). Some benchmarks are not dialogue at all — MemoryAgentBench's
FactConsolidation, for example, is a flat list of encyclopedic assertions like

    "3. Hines Ward plays the position of wide receiver."

There is no speaker to bind to; the fact's grammatical subject IS the entity.
CLEAN_SYS already has a rule for this case, but the caller still has to know
what to pass as `speakers`. That rule is: pass the sentence's grammatical
subject as a `speakers` hint of size 1. This module ships the small regex
helper (`fc_subject`) and a one-line convenience (`add_fc_fact`) that do that.

New benchmark of the same shape? Add a new subject parser here and route to
`add_chunk` the same way — keep the core library dialogue-first.
"""
from __future__ import annotations
import re
from typing import Optional

# Verb pivots that separate a "SUBJ ... VERB ... OBJ." predicate in FC lines.
# Order matters: more specific patterns first.
_FC_SUBJECT_PATTERNS = [
    # "The chairperson/director/capital/... of X is/was Y"  --> subject = X
    re.compile(
        r"^The (?:chairperson|director|university|univeristy|capital|headquarters|"
        r"current head|official language|name of[^ ]*) of ([^.]+?) (?:is|was|are)\b"
    ),
    # "SUBJ is|was born|located|associated|married|a citizen|the ..."
    re.compile(r"^([A-Z][^.]+?) (?:is|was) (?:born|located|associated|married|a citizen|the)"),
    # "SUBJ plays|died|works|lives ..."
    re.compile(r"^([A-Z][^.]+?) (?:plays|died|works|lives) "),
    # Generic fallback: "SUBJ is|was|plays|died|works|has ..."
    re.compile(r"^([A-Z][A-Za-zÀ-ÿ0-9 .'’&-]+?) (?:is|was|plays|died|works|has)\b"),
]


def fc_subject(fact_line: str) -> Optional[str]:
    """Extract the SUBJECT entity from a MAB-FactConsolidation-style fact.

    The FC format is "<N>. <declarative sentence about a world fact>." — e.g.

        >>> fc_subject("3. Hines Ward plays the position of wide receiver.")
        'Hines Ward'
        >>> fc_subject("1. The chairperson of Fatah is Mahmoud Abbas.")
        'Fatah'

    Returns None when no known pattern matches (~12% of FC lines on the SH-6k
    slice; those lines are skipped rather than force-fed to the extractor).
    """
    m = re.match(r"\d+\.\s+(.*)", fact_line)
    if not m:
        # Not numbered; still try — caller passed a bare sentence.
        txt = fact_line.strip()
    else:
        txt = m.group(1)
    for pat in _FC_SUBJECT_PATTERNS:
        mm = pat.match(txt)
        if mm:
            return mm.group(1).strip()
    return None


def add_fc_fact(system, fact_line: str, timestamp: Optional[str] = None) -> bool:
    """Ingest one FactConsolidation-style fact into `system` (a SchemaMemorySystem).

    Parses the subject with `fc_subject` and passes it as a single-entry
    `speakers` hint so L1 extraction binds the fact to the right entity.
    Returns True on ingest, False when the subject cannot be parsed.
    """
    subj = fc_subject(fact_line)
    if not subj:
        return False
    system.add_chunk(fact_line, timestamp=timestamp, speakers=[subj])
    return True
