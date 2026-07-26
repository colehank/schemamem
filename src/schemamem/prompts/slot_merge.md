You decide whether a NEW attribute-slot for one entity is the SAME ATTRIBUTE as one
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
