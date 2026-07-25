"""Loader for SchemaMem's L1/L2 prompts, externalised to ``prompts.yaml``.

The prompt text now lives in ``prompts.yaml`` (readable block scalars, with the rationale for
each hard-won rule kept in the comments beside it) instead of inline Python strings. This module
loads them and re-exports the SAME constant names the rest of the package imports —
``SLOT_MERGE_SYS`` / ``CLEAN_SYS`` / ``QUANT_SYS`` / ``EXTRACT_SYS`` / ``REWRITE_SYS`` /
``ANSWER_SYS`` — so nothing downstream changes.

Editing a prompt = editing ``prompts.yaml``; do not paste prompt text back into this file. If you
change ``EXTRACT_SYS``, re-run ``tests/test_system.py`` (its invariants are load-bearing).
"""
from pathlib import Path

import yaml

_PROMPTS = yaml.safe_load((Path(__file__).with_name("prompts.yaml")).read_text(encoding="utf-8"))


def _p(key: str) -> str:
    return _PROMPTS[key].rstrip("\n")


SLOT_MERGE_SYS = _p("slot_merge")
CLEAN_SYS = _p("clean")
QUANT_SYS = _p("quant")
EXTRACT_SYS = _p("extract")
REWRITE_SYS = _p("rewrite")
ANSWER_SYS = _p("answer")

__all__ = [
    "SLOT_MERGE_SYS", "CLEAN_SYS", "QUANT_SYS", "EXTRACT_SYS", "REWRITE_SYS", "ANSWER_SYS",
]
