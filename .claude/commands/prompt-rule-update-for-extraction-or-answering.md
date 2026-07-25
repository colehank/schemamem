---
name: prompt-rule-update-for-extraction-or-answering
description: Workflow command scaffold for prompt-rule-update-for-extraction-or-answering in schemamem.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /prompt-rule-update-for-extraction-or-answering

Use this workflow when working on **prompt-rule-update-for-extraction-or-answering** in `schemamem`.

## Goal

Refines or corrects prompt engineering rules for extraction or answering, often in response to evaluation failures or observed errors, to improve information extraction or answer accuracy.

## Common Files

- `src/schemamem/prompts.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit src/schemamem/prompts.py to update or add new prompt rules
- Describe the reasoning and expected effect in the commit message
- Optionally run or update tests to validate the fix

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.