You extract QUANTIFIABLE STATE about entities from one episode of dialogue — the
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
- Capture values stated in RECALL or QUESTION form, not just fresh declarations. A number wrapped in
  "remember when I got pre-approved for $400,000?", "as I mentioned, I now have four bikes", or
  "you know my 25:50 5K time" still asserts the value — extract it ("The user was pre-approved for
  $400,000"). People restate a changed number casually, and that restatement is often the update, so
  never skip a number just because it appears in a reminiscing or rhetorical sentence.
- Write each as a self-contained sentence carrying the explicit value (resolve all references).
- Only quantifiable/comparable state. If the episode has none, return an empty list.
Return STRICT JSON: {"facts": [{"subject": "<entity>", "text": "<fact with the explicit value>"}, ...]}.
