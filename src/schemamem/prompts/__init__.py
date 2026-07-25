"""SchemaMem's L1/L2 prompts — one file per prompt in this directory.

Each prompt is a plain ``.md`` file whose entire content *is* the prompt text (no frontmatter to
strip, so what you read is exactly what the model sees). This loader reads them and re-exports the
same constant names the rest of the package imports — ``SLOT_MERGE_SYS`` / ``CLEAN_SYS`` /
``QUANT_SYS`` / ``EXTRACT_SYS`` / ``REWRITE_SYS`` / ``ANSWER_SYS`` — so nothing downstream changes.

Editing a prompt = editing its ``.md`` file. The rationale for each hard-won rule lives in
``README.md`` next to the prompts. If you change ``extract.md``, re-run ``tests/test_system.py``
(its invariants are load-bearing).
"""
from pathlib import Path

_DIR = Path(__file__).parent


def _load(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


SLOT_MERGE_SYS = _load("slot_merge")
CLEAN_SYS = _load("clean")
QUANT_SYS = _load("quant")
EXTRACT_SYS = _load("extract")
REWRITE_SYS = _load("rewrite")
ANSWER_SYS = _load("answer")

__all__ = [
    "SLOT_MERGE_SYS", "CLEAN_SYS", "QUANT_SYS", "EXTRACT_SYS", "REWRITE_SYS", "ANSWER_SYS",
]
