"""Create an immutable Phase 4E winner manifest only after every validation gate passes."""
import argparse
import json

from jalrakshak_ml.deep_nowcast.phase4e_prepare import freeze_winner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection")
    parser.add_argument("--prerequisites")
    parser.add_argument("--output", default="models/phase4e/winner_manifest.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("MODEL_SELECTION_FROZEN=false")
        print("LOCKED_TEST_ALLOWED_FOR_SINGLE_FINAL_EVALUATION=false")
        return
    if not args.selection or not args.prerequisites:
        parser.error("--execute requires --selection and --prerequisites")
    with open(args.selection, encoding="utf-8") as stream:
        selection = json.load(stream)
    with open(args.prerequisites, encoding="utf-8") as stream:
        prerequisites = json.load(stream)
    result = freeze_winner(selection, prerequisites, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
