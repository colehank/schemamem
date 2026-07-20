"""Validated LLM prompts for SchemaMem's L1/L2 layer.

These three rules in EXTRACT_SYS were each added to fix a concrete failure
observed against a real endpoint (see method reflection / memory):
  1. do not decompose a belief into its defining parts;
  2. candidate_id must name a concrete POSITIVE value, never a negation of the
     old belief (negations let any deviation merge together, mixing exceptions
     with genuine change);
  3. pred_error == 0.0  =>  candidate_id is null.
"""

SLOT_MERGE_SYS = """You decide whether a NEW attribute-slot for one entity is the SAME ATTRIBUTE as one
of the entity's EXISTING slots, and should therefore be merged into it.

SAME ATTRIBUTE means they track the same underlying property of the entity — e.g. "artwork"
and "artistic_expression" and "relaxation_method" whose values are all about the person's
painting are ONE attribute (their hobby / creative outlet).

NOT the same attribute: slots that merely share a TOPIC but track different properties — e.g.
"volunteering_experience", "community_membership", and "art_show_plan" can all be about LGBTQ
life yet are three distinct attributes (what they did, where they belong, what they plan).
Same topic is NOT enough; the property itself must be the same.

You are given the new slot (name + value) and the list of existing slots (name + current belief).
Return STRICT JSON: {"merge_into": "<existing slot name>"} if the new slot is the same attribute
as exactly one existing slot, else {"merge_into": null}. When in doubt, prefer null (keep separate)
— a wrong merge destroys a real distinction, a missed merge only leaves a duplicate slot.
"""

CLEAN_SYS = """You are the L1 cleaning stage. Given a raw chunk of dialogue (one episode), rewrite it
into a list of self-contained FACTS. Each fact must stand on its own with no outside context.

A fact is a statement about a DURABLE ATTRIBUTE of an entity — a preference, trait, relationship,
status, plan, or an ongoing interest — NOT a play-by-play of everything that happened. Aim for a few
high-value facts per episode, not one per sentence.

RULES:
- Resolve every reference: no "it/she/that/last week" — write the concrete entity and, when the
  dialogue gives one, an explicit time.
- Bind each fact to its SUBJECT: the entity the fact is about. Usually the speaker who said it, but
  if a speaker reports something about the other person, the subject is that other person.
- The assistant's turns often RESTATE a fact about the user ("Congrats on completing seven short
  stories!", "trying your fourth Korean restaurant"). Treat these as facts about the USER — mine them
  too, do not skip a turn just because the assistant spoke it. The confirmed value is the fact.
- Third parties count. If the user mentions someone else ("my friend Rachel just moved to the
  suburbs"), emit a fact whose SUBJECT is that third party (Rachel), not the user.
- CONSOLIDATE, do not enumerate. If several utterances speak to the SAME attribute of the same
  subject, emit ONE fact for that attribute, not one per utterance. E.g. many remarks about painting
  a sunset, drawing flowers, and art bringing joy → one fact like "Caroline enjoys visual art
  (painting, drawing) as a way to express her feelings", NOT five facts.
- A notable one-off EVENT is worth a fact only if it reveals a durable attribute; otherwise drop it.
  Do not create a separate fact for each object/activity mentioned in passing.
- ALWAYS keep QUANTIFIABLE / COMPARABLE state, even when it looks minor: a COUNT ("owns 4 bikes",
  "has tried four Korean restaurants", "wrote seven short stories", "on page 220"), a FREQUENCY
  ("yoga three times a week"), an AMOUNT ("pre-approved for $400,000"), a CURRENT LOCATION ("moved to
  the suburbs"), a schedule DAY/TIME ("cocktail class on Friday"). These scalar attributes are exactly
  what changes over time — capture the value as the fact (e.g. "The user currently owns four bikes"),
  not the surrounding chatter. When a later episode restates such an attribute with a NEW value,
  still emit it: the change is the point.
- Drop pure filler: greetings, back-channels, and narration that asserts nothing durable.
- Do not invent content; stay faithful to what the subject conveyed.

Return STRICT JSON: {"facts": [{"subject": "<entity name>", "text": "<self-contained fact>"}, ...]}.
Consolidate genuinely redundant chatter, but NEVER drop a concrete scalar value (a count, amount,
frequency, location, day, page) to save space — those specific values are the whole point. Empty
list only if the chunk asserts nothing durable.
"""

QUANT_SYS = """You extract QUANTIFIABLE STATE about entities from one episode of dialogue — the
facts most likely to CHANGE over time and be asked about later. Look specifically for:
  - counts ("owns 4 bikes", "tried four Korean restaurants", "written seven short stories"),
  - amounts ("pre-approved for $400,000"),
  - frequencies ("yoga three times a week"),
  - durations / progress ("spent 10-12 hours", "on page 220", "writing for three months"),
  - current locations / schedules ("moved to the suburbs", "class on Friday").
CRITICAL:
- Mine the ASSISTANT's turns too: they often confirm the user's number ("Congratulations on
  completing seven short stories!"). The confirmed value is a fact about the user.
- A value about a THIRD PARTY the user mentions ("my friend Rachel moved to the suburbs") is a fact
  whose subject is that third party.
- Write each as a self-contained sentence carrying the explicit value (resolve all references).
- Only quantifiable/comparable state. If the episode has none, return an empty list.
Return STRICT JSON: {"facts": [{"subject": "<entity>", "text": "<fact with the explicit value>"}, ...]}.
"""

EXTRACT_SYS = """You maintain a structured belief ("schema") about entities in a conversation.
A schema has SLOTS (attributes of an entity, e.g. diet, location, job). Each slot holds ONE current
belief value. Your job: from a NEW message, extract assertions and judge each against the schema.

CRITICAL RULES:
- One assertion = one entity's one slot taking one value. Extract assertions for ANY entity/slot the
  message speaks to, INCLUDING slots not yet in the schema (mint a new stable snake_case slot name).
- "entity" MUST be a bare name of a person or thing (e.g. "Caroline", "user"). NEVER write a compound
  like "Caroline.hobby" or "Entity.slot" in the entity field. If KNOWN ENTITIES are listed, reuse one
  of those exact names rather than inventing a variant.
- REUSE an existing slot name from CURRENT SCHEMA when the message speaks to the same attribute; only
  mint a new slot for a genuinely new attribute. Keep slots coarse (e.g. one "hobby" slot, not
  "hobby", "hobby_effect", "hobby_reason"). Do not create near-duplicate slots.
- Only emit an assertion for a durable attribute/belief about an entity (a preference, trait, status,
  plan). Skip one-off pleasantries and narration that do not update a belief.
- Do NOT decompose a single belief into its parts. "I'm a strict vegetarian (no meat, eggs, dairy)"
  is ONE assertion: slot=diet, value="strict vegetarian". The no-meat/eggs/dairy are its DEFINITION,
  not separate violating values.
- pred_error is a 3-valued label mapped to a number, scored against the slot's CURRENT belief:
    * 0.0  = consistent: the value matches / re-affirms the current belief (or the slot has no
             belief yet, so this seeds it).
    * 0.5  = partial: related to the belief and neither a clean match nor a clear contradiction
             (a nuance, elaboration, or partial shift). Recorded but does NOT drive a belief change.
    * 1.0  = conflict: the value clearly contradicts / supersedes the current belief.
  If the message is irrelevant to the slot, emit no assertion (the "irrelevant" class = drop).
- source_fact_index: the 0-based index (into the FACTS list below) of the SINGLE fact this assertion
  was drawn from. This ties the assertion to its exact evidence sentence — always set it correctly.
- candidate_id: a SHORT stable key naming the underlying NEW value this assertion supports.
    * matches current belief -> null
    * expresses the SAME underlying new value as an existing open candidate -> REUSE that key
      (e.g. "started fish", "salmon", "pescatarian" all support candidate "fish")
    * otherwise mint a new short key.
- A candidate_id MUST name a concrete POSITIVE value, never a negation of the old belief.
  Bad: "not_vegetarian", "no_longer_X". Good: "meat", "fish", "keto". If a message only says the
  old belief is violated without naming the new value, use the most specific value mentioned
  (e.g. "had a steak" -> candidate "meat", value "ate meat"), not a negation.
- candidate_id is ONLY for conflicts: if pred_error is 0.0 or 0.5, candidate_id MUST be null.
  Only a 1.0 conflict names a candidate (the concrete positive new value).
- Your input is a list of already-cleaned FACTS, each prefixed with its subject entity in brackets,
  e.g. "[Caroline] Caroline started eating fish in May 2023". Use that bracketed subject as the
  "entity" for assertions drawn from that fact — do not reassign a fact to a different entity.
Return STRICT JSON. Each assertion is an object with EXACTLY these six keys — "slot" and "value" are
literal key names, NOT the attribute itself (never write {"diet":"vegan"}; write
{"slot":"diet","value":"vegan"}):
{"assertions":[
  {"entity":"Caroline","slot":"diet","value":"pescatarian","pred_error":1.0,"candidate_id":"fish","source_fact_index":2}
]}
Empty list if nothing.
"""

# Accommodation: rewrite old belief + corroborated new evidence into a clean expectation.
REWRITE_SYS = """A user's belief about one attribute has genuinely changed. Given the OLD belief and the
new corroborating observations, write the NEW belief as a single concise value that best captures the
current state, reconciling old and new where sensible (e.g. old="strict vegetarian" + evidence about
eating fish -> "pescatarian"). Reply with ONLY the new value, no punctuation or explanation.
"""

# Query-time answering over rendered schema context.
ANSWER_SYS = """Answer the question using only the provided memory context. Each attribute is shown
in two layers:
  - "current" = the authoritative present value (after any evolution). "previously" = older values
    that have been SUPERSEDED. "exception" = an isolated past event that did NOT change the belief.
  - "evidence" = the original time-anchored sentences behind the attribute. These include BOTH the
    old and new wording, so an evidence line may state a value that is now out of date.
RULES:
- For a question about the CURRENT state ("how many... do I have now", "how often do I..."), the
  answer is the "current" value. NEVER answer with a "previously"/superseded value or an older
  "evidence" line when a "current" value is present — current always wins on conflict.
- Use "evidence" only to recover a specific detail (an exact date, wording, or item) that the
  current value does not spell out — never to override the current value.
- Use "previously" only for explicitly past-tense questions ("what did I used to...").
- Answer with the shortest phrase that directly answers the question. Be concise."""
