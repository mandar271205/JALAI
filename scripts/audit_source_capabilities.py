"""Print the evidence-backed offline/online source capability matrix."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.research.sources import default_source_capabilities


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional JSON output")
    args = parser.parse_args()
    payload = [item.to_dict() for item in default_source_capabilities()]
    text = json.dumps(payload, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
