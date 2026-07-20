"""SchemaMem: schema-memory-inspired long-term memory for LLM agents.

A per-entity schema (named slots + evidence ledger) distinguishes a *genuine
change* from an *isolated exception* using a single criterion — the prediction
residual of a new observation against the current belief — read along two axes
(magnitude x cross-episode recurrence). See README for the full model.
"""
from .core import (
    Action,
    Observation,
    Candidate,
    Slot,
    Schema,
    SchemaGraph,
)
from .schema_memory import SchemaMemorySystem

__version__ = "0.1.0"
__all__ = [
    "Action",
    "Observation",
    "Candidate",
    "Slot",
    "Schema",
    "SchemaGraph",
    "SchemaMemorySystem",
]
