"""Validated LLM prompts for SchemaMem's L1/L2 layer.

These three rules in EXTRACT_SYS were each added to fix a concrete failure
observed against a real endpoint (see method reflection / memory):
  1. do not decompose a belief into its defining parts;
  2. candidate_id must name a concrete POSITIVE value, never a negation of the
     old belief (negations let any deviation merge together, mixing exceptions
     with genuine change);
  3. pred_error == 0.0  =>  candidate_id is null.
"""

EXTRACT_SYS = """You maintain a structured belief ("schema") about entities in a conversation.
A schema has SLOTS (attributes of an entity, e.g. diet, location, job). Each slot holds ONE current
belief value. Your job: from a NEW message, extract assertions and judge each against the schema.

CRITICAL RULES:
- One assertion = one entity's one slot taking one value. Extract assertions for ANY entity/slot the
  message speaks to, INCLUDING slots not yet in the schema (mint a new stable snake_case slot name).
- Do NOT decompose a single belief into its parts. "I'm a strict vegetarian (no meat, eggs, dairy)"
  is ONE assertion: slot=diet, value="strict vegetarian". The no-meat/eggs/dairy are its DEFINITION,
  not separate violating values.
- pred_error is a 3-class label mapped to a number: 0.0 if the value matches the slot's current
  belief (consistent), 1.0 if it clearly contradicts it (conflict). If the message is irrelevant to
  the slot, emit no assertion for it (the "irrelevant" class = drop, not a number). If the slot has
  no belief yet, use 0.0 (it seeds the belief). Do NOT emit intermediate values like 0.5.
- candidate_id: a SHORT stable key naming the underlying NEW value this assertion supports.
    * matches current belief -> null
    * expresses the SAME underlying new value as an existing open candidate -> REUSE that key
      (e.g. "started fish", "salmon", "pescatarian" all support candidate "fish")
    * otherwise mint a new short key.
- A candidate_id MUST name a concrete POSITIVE value, never a negation of the old belief.
  Bad: "not_vegetarian", "no_longer_X". Good: "meat", "fish", "keto". If a message only says the
  old belief is violated without naming the new value, use the most specific value mentioned
  (e.g. "had a steak" -> candidate "meat", value "ate meat"), not a negation.
- If pred_error is 0.0 (matches or seeds the belief), candidate_id MUST be null.
Return STRICT JSON: {"assertions":[{entity,slot,value,pred_error,candidate_id}, ...]}. Empty list if nothing.
"""

# Accommodation: rewrite old belief + corroborated new evidence into a clean expectation.
REWRITE_SYS = """A user's belief about one attribute has genuinely changed. Given the OLD belief and the
new corroborating observations, write the NEW belief as a single concise value that best captures the
current state, reconciling old and new where sensible (e.g. old="strict vegetarian" + evidence about
eating fish -> "pescatarian"). Reply with ONLY the new value, no punctuation or explanation.
"""

# Query-time answering over rendered schema context.
ANSWER_SYS = """Answer the question using only the provided memory context. The context lists, per
attribute: the current belief, a superseded trail (older values with when they were replaced), and
protected exceptions (isolated past events that did not change the belief). Prefer the current belief;
use the superseded trail for "what did they used to..." questions and exceptions for one-off events.
Be concise."""
