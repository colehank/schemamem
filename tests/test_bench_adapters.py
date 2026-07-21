"""Regression tests for bench_adapters — pure-Python, no LLM."""
from schemamem.bench_adapters import fc_subject


def test_fc_subject_direct_predicate():
    # "SUBJ plays/died/... OBJ"
    assert fc_subject("3. Hines Ward plays the position of wide receiver.") == "Hines Ward"
    assert fc_subject("2. Amy Winehouse died in the city of Camden Town.") == "Amy Winehouse"


def test_fc_subject_of_construction():
    # "The X of Y is Z" — subject is Y, not the person named as the value
    assert fc_subject("1. The chairperson of Fatah is Mahmoud Abbas.") == "Fatah"
    assert (
        fc_subject("7. The director of British Broadcasting Corporation is Tony Hall, Baron Hall of Birkenhead.")
        == "British Broadcasting Corporation"
    )


def test_fc_subject_is_predicate():
    # "SUBJ is <adj-clause>"
    assert fc_subject("0. Thomas Kyd was born in the city of London.") == "Thomas Kyd"
    assert fc_subject("4. Bengaluru is located in the continent of Asia.") == "Bengaluru"
    assert fc_subject("8. Victoria Beckham is married to David Beckham.") == "Victoria Beckham"


def test_fc_subject_returns_none_when_no_match():
    # Lines with no known verb pivot don't parse.
    assert fc_subject("some random line") is None
    assert fc_subject("42. Just a fragment") is None


def test_fc_subject_common_noun_subject():
    # A capitalized "The X is/was ..." construction — the extractor takes the
    # noun phrase as-is; downstream entity dedup will merge it if it's spurious.
    assert (
        fc_subject("31. The quarterback is associated with the sport of American football.")
        == "The quarterback"
    )
