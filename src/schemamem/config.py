"""Unified runtime configuration — one place for endpoints, keys, and models.

Historically these were ~six loose constructor arguments on ``SchemaMemorySystem``
(``model`` / ``api_base`` / ``api_key`` / ``embedding_*``) with env fallbacks scattered
inline. ``RuntimeConfig`` centralises them and aligns the vocabulary with the MemoryData
harness config (``base_url`` / ``api_key`` / ``model`` / ``embedding_*``), so a single
object flows from the YAML config through the adapter into the system.

Resolution order for each endpoint field: explicit value → environment variable → default.
The ``/v1`` suffix (the OpenAI SDK posts to ``<base_url>/chat/completions``) is normalised
here, in one place, rather than inline at the call site.

Pure stdlib; no network, no LLM. The core (``core.py`` / ``graph_core.py``) never imports this.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Optional


def _norm_v1(url: Optional[str]) -> Optional[str]:
    """Append ``/v1`` unless already present (a gateway root without it 404s silently)."""
    if not url:
        return url
    url = url.rstrip("/")
    return url if url.endswith("/v1") else url + "/v1"


@dataclass
class RuntimeConfig:
    """Endpoints, keys, and model names for the OpenAI-compatible chat + embedding services.

    ``base_url`` / ``api_key`` name the chat endpoint; the embedding endpoint defaults to the
    same credentials unless given its own. Field names mirror the MemoryData config keys.
    """

    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.0
    embedding_model: str = "Qwen3-Embedding-4B"
    embedding_base_url: Optional[str] = None
    embedding_api_key: Optional[str] = None

    def __post_init__(self):
        self.base_url = _norm_v1(self.base_url or os.environ.get("OPENAI_BASE_URL"))
        self.api_key = self.api_key or os.environ.get("OPENAI_API_KEY") or "EMPTY"
        # embedding endpoint falls back to the chat endpoint's credentials
        self.embedding_base_url = _norm_v1(self.embedding_base_url) or self.base_url
        self.embedding_api_key = self.embedding_api_key or self.api_key

    # -- constructors --------------------------------------------------------
    @classmethod
    def from_env(cls, model: Optional[str] = None, **overrides) -> "RuntimeConfig":
        """Read OPENAI_* from the environment; ``model`` and any field can be overridden."""
        if model is not None:
            overrides["model"] = model
        return cls(**overrides)

    @classmethod
    def from_mapping(cls, cfg: dict) -> "RuntimeConfig":
        """Build from a MemoryData-style config mapping. Accepts both the plain keys
        (``base_url`` / ``api_key_env`` / ``model`` / ``embedding_*``) and the
        ``schemamem_``-prefixed variants, preferring the prefixed ones."""
        def env(*names):
            for n in names:
                v = cfg.get(n)
                if v and os.environ.get(v):
                    return os.environ[v]
            return None

        def pick(*names, default=None):
            for n in names:
                if cfg.get(n) is not None:
                    return cfg[n]
            return default

        return cls(
            model=pick("schemamem_model", "model", default="gpt-4o-mini"),
            base_url=pick("schemamem_base_url", "base_url"),
            api_key=env("schemamem_api_key_env", "api_key_env") or pick("api_key"),
            temperature=float(pick("temperature", default=0.0)),
            embedding_model=pick("schemamem_embedding_model", "embedding_model",
                                 default="Qwen3-Embedding-4B"),
            embedding_base_url=pick("schemamem_embedding_base_url", "embedding_base_url"),
            embedding_api_key=env("schemamem_embedding_api_key_env", "embedding_api_key_env"),
        )

    def merged(self, **overrides) -> "RuntimeConfig":
        """Return a copy with the given non-None overrides applied (explicit args win)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean) if clean else self
