---
name: core-logic-iteration-with-tests
description: Workflow command scaffold for core-logic-iteration-with-tests in schemamem.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /core-logic-iteration-with-tests

Use this workflow when working on **core-logic-iteration-with-tests** in `schemamem`.

## Goal

Implements or refactors core memory logic modules (e.g., schema_memory.py, graph_core.py, coupled_core.py), with corresponding updates or additions to test files to validate new or changed behaviors.

## Common Files

- `src/schemamem/schema_memory.py`
- `src/schemamem/graph_core.py`
- `src/schemamem/coupled_core.py`
- `tests/test_system.py`
- `tests/test_graph_core.py`
- `tests/test_coupled_core.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit or create core logic file (e.g., src/schemamem/schema_memory.py, src/schemamem/graph_core.py, src/schemamem/coupled_core.py)
- Update or add corresponding test file (e.g., tests/test_system.py, tests/test_graph_core.py, tests/test_coupled_core.py)
- Optionally update documentation to reflect new logic
- Run and verify all tests pass

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.