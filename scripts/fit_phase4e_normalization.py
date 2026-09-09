"""Prepare or explicitly fit Phase 4E train-only normalization after real replay audits pass."""

import argparse
import json

from jalrakshak_ml.deep_nowcast.phase4e_prepare import fit_train_only_normalization


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--elevation", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--replay-version", required=True)
    parser.add_argument("--git-sha", required=True)
    args = parser.parse_args()
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "NOT_FITTED",
                    "fitted_split": "train",
                    "validation_allowed": False,
                    "locked_test_allowed": False,
                },
                indent=2,
            )
        )
        return
    result = fit_train_only_normalization(
        args.dataset_root,
        args.replay_root,
        args.elevation,
        args.output,
        dataset_version=args.dataset_version,
        replay_version=args.replay_version,
        git_sha=args.git_sha,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
