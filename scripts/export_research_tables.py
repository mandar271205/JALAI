"""Export CSV, JSON, or Markdown research tables without filling missing values."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.research.tables import TABLE_TYPES, export_research_table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table_type", choices=sorted(TABLE_TYPES))
    parser.add_argument("input_json", help="JSON list of row objects")
    parser.add_argument("output", help=".csv, .json, or .md output")
    args = parser.parse_args()
    rows = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    print(export_research_table(args.table_type, rows, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
