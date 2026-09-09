"""Build a leakage-resistant dataset manifest from explicitly labeled reports."""

import argparse
import json
from pathlib import Path

from jalrakshak_ml.citizen.dataset import CitizenDatasetBuilder, CitizenLabel, LabeledCitizenSample


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", help="Object with samples and event_splits")
    parser.add_argument("output_json", help="New immutable manifest path")
    args = parser.parse_args()
    source = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    samples = []
    for row in source["samples"]:
        row["label"] = CitizenLabel(row["label"])
        samples.append(LabeledCitizenSample(**row))
    print(
        json.dumps(CitizenDatasetBuilder().build(samples, source["event_splits"], args.output_json))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
