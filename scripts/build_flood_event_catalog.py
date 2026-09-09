"""Build an immutable evidence-gated Mumbai flood event catalog."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.evidence.catalog import EventCatalog, EventState, FloodEvent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", help="JSON list of event objects")
    parser.add_argument("output_json", help="New immutable catalog path")
    args = parser.parse_args()
    events = []
    for row in json.loads(Path(args.input_json).read_text(encoding="utf-8")):
        row["state"] = EventState(row["state"])
        for key in tuple(row):
            if key.endswith("_refs") or key == "caveats":
                row[key] = tuple(row[key])
        events.append(FloodEvent(**row))
    print(json.dumps(EventCatalog(events).write_atomic(args.output_json)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
