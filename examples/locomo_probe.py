"""Build a SchemaMem memory from one real LoCoMo conversation and print the
resulting schema — a small qualitative probe of "what memory does the method
produce on real data".

Unlike examples/diet_dialogue.py (offline, scripted), this hits a real LLM, so it
needs an OpenAI-compatible endpoint configured (see docs/CONFIGURATION.md):

    export OPENAI_BASE_URL=...   # gateway root or .../v1 (both work)
    export OPENAI_API_KEY=...

Get the data (not bundled):
    curl -sSL -o locomo10.json \\
      https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json

Run:
    uv run examples/locomo_probe.py locomo10.json --sample 0
"""
import argparse
import json

from schemamem import SchemaMemorySystem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("locomo_json", help="path to locomo10.json")
    ap.add_argument("--sample", type=int, default=0, help="which conversation (0-9)")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--k", type=int, default=2, help="min independent episodes to accommodate")
    args = ap.parse_args()

    conv = json.load(open(args.locomo_json))[args.sample]["conversation"]
    speakers = [conv["speaker_a"], conv["speaker_b"]]
    sessions = [k for k in conv if k.startswith("session") and "date" not in k]

    # model / api_base / api_key default to OPENAI_* env vars inside the system.
    mem = SchemaMemorySystem(model=args.model, min_evidence_count=args.k)

    for k in sessions:
        text = "\n".join(f"{t['speaker']}: {t['text']}" for t in conv[k])
        mem.add_chunk(text, timestamp=conv.get(k + "_date_time", k), speakers=speakers)
    mem.finalize()

    for entity, schema in mem._graph.entities.items():
        print(f"\n=== {entity} :: {len(schema.slots)} slots ===")
        for name, slot in schema.slots.items():
            tags = []
            if slot.superseded:
                tags.append(f"CHANGED from {slot.superseded[0][0]!r}")
            if slot.exceptions:
                tags.append(f"{len(slot.exceptions)} exception(s)")
            tag = ("  <- " + "; ".join(tags)) if tags else ""
            print(f"  {name}: {slot.belief}  ({len(slot.ledger)} obs){tag}")


if __name__ == "__main__":
    main()
