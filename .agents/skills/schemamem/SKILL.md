```markdown
# schemamem Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill teaches you the core development patterns, coding conventions, and collaborative workflows used in the `schemamem` Python codebase. `schemamem` is a memory system with modular logic for schema-based memory, graph operations, and prompt engineering, with a strong emphasis on evaluation and documentation alignment. The repository is structured for iterative research, with clear commit conventions and workflow triggers for core logic, prompt rules, evaluation, performance, and conceptual documentation.

## Coding Conventions

- **File Naming:**  
  Use `snake_case` for all Python files and modules.
  ```
  # Good
  schema_memory.py
  graph_core.py

  # Bad
  SchemaMemory.py
  graphCore.py
  ```

- **Import Style:**  
  Use **relative imports** within the package.
  ```python
  # Inside src/schemamem/graph_core.py
  from .schema_memory import SchemaMemory
  ```

- **Export Style:**  
  Use **named exports** (explicit class/function definitions).
  ```python
  # src/schemamem/schema_memory.py
  class SchemaMemory:
      ...
  ```

- **Commit Messages:**  
  Follow **conventional commit** prefixes: `fix`, `feat`, `eval`, `docs`, `perf`, `chore`.
  ```
  feat: add batch processing to schema_memory for faster ingestion
  fix: correct arbitration logic in graph_core
  ```

## Workflows

### Core Logic Iteration with Tests
**Trigger:** When adding or refactoring core memory logic, or upgrading the core model  
**Command:** `/core-logic-update`

1. Edit or create a core logic file (e.g., `src/schemamem/schema_memory.py`, `src/schemamem/graph_core.py`, `src/schemamem/coupled_core.py`)
2. Update or add corresponding test files (e.g., `tests/test_system.py`, `tests/test_graph_core.py`, `tests/test_coupled_core.py`)
3. Optionally update documentation to reflect new logic
4. Run and verify all tests pass

**Example:**
```python
# src/schemamem/schema_memory.py
class SchemaMemory:
    def add(self, item):
        # new logic here
        pass
```
```python
# tests/test_system.py
def test_add():
    mem = SchemaMemory()
    mem.add('foo')
    assert 'foo' in mem
```

---

### Prompt Rule Update for Extraction or Answering
**Trigger:** When refining prompt engineering rules for extraction or answering  
**Command:** `/update-prompt-rule`

1. Edit `src/schemamem/prompts.py` to update or add new prompt rules
2. Describe reasoning and expected effect in the commit message
3. Optionally run or update tests to validate the fix

**Example:**
```python
# src/schemamem/prompts.py
EXTRACTION_PROMPT = """
Extract entities and relationships from the following text:
{text}
"""
```

---

### Evaluation Plan and Paper Alignment
**Trigger:** When updating evaluation plans, results, or aligning documentation with the current system  
**Command:** `/update-eval-docs`

1. Edit `docs/eval/evolution_comparison_plan.md` and/or `docs/design/full_paper_zh.md`
2. Optionally update `CLAUDE.md` or other documentation files
3. Describe rationale and changes in the commit message

---

### Performance Optimization in Core Logic
**Trigger:** When improving runtime performance of memory operations  
**Command:** `/perf-optimize-core`

1. Edit `src/schemamem/schema_memory.py` to add batching, concurrency, or buffer logic
2. Describe performance measurements and improvements in the commit message
3. Optionally update configuration or test files

**Example:**
```python
# src/schemamem/schema_memory.py
class SchemaMemory:
    def add_batch(self, items):
        # optimized batch processing
        pass
```

---

### Documentation Frontier or Direction Update
**Trigger:** When documenting new models, directions, or conceptual advances  
**Command:** `/doc-frontier-update`

1. Edit `CLAUDE.md` and/or `docs/design/evolving_graph.md` to reflect the new model or direction
2. Optionally update or add prototype or reference files
3. Describe the new direction and rationale in the commit message

---

## Testing Patterns

- **Framework:** Unknown (no standard Python test framework detected)
- **Test File Naming:**  
  All test files use the pattern `test_*.py` and are located in the `tests/` directory.
- **Test Example:**
  ```python
  # tests/test_graph_core.py
  def test_graph_add_node():
      g = GraphCore()
      g.add_node('A')
      assert 'A' in g.nodes
  ```

## Commands

| Command                | Purpose                                                        |
|------------------------|----------------------------------------------------------------|
| /core-logic-update     | Add or refactor core logic modules and update related tests    |
| /update-prompt-rule    | Refine or correct prompt engineering rules                     |
| /update-eval-docs      | Update evaluation plans, documentation, or paper drafts        |
| /perf-optimize-core    | Optimize performance of core memory logic                      |
| /doc-frontier-update   | Document new models, directions, or conceptual advances        |
```
