"""Small JSON-recovery helper shared by the L1/L2 stages."""
import json


def _extract_json(text: str, key: str = "assertions") -> dict:
    """Parse a JSON object from an LLM reply, tolerating truncation.

    On a clean parse, return it. If the reply was cut off mid-array (common when
    max_tokens is hit), salvage every COMPLETE {...} object inside the first array
    under `key` rather than silently dropping the whole reply."""
    start = text.find("{")
    if start == -1:
        return {}
    try:
        return json.loads(text[start:text.rfind("}") + 1])
    except json.JSONDecodeError:
        pass
    # recovery: pull complete top-level objects out of the (possibly truncated) list
    objs, depth, buf, in_str, esc = [], 0, [], False, False
    for ch in text[start + 1:]:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            buf.append(ch)
        elif ch == "{":
            depth += 1
            buf.append(ch)
        elif ch == "}":
            depth -= 1
            buf.append(ch)
            if depth == 0:
                try:
                    objs.append(json.loads("".join(buf)))
                except json.JSONDecodeError:
                    pass
                buf = []
        elif depth > 0:
            buf.append(ch)
    return {key: objs}
