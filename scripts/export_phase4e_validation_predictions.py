"""Export paired validation predictions for one Phase 4E contender."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
import yaml

from jalrakshak_ml.deep_nowcast.convlstm_v3 import ConvLSTMNowcasterV3
from jalrakshak_ml.deep_nowcast.experiments import (
    ABLATIONS,
    SOURCE_STRESS_TESTS,
    apply_declared_mask,
)
from jalrakshak_ml.deep_nowcast.final_dataset import Phase4EFinalDataset
from jalrakshak_ml.deep_nowcast.final_runner import make_dataloader
from jalrakshak_ml.deep_nowcast.final_tournament import (
    make_deep_predictor,
    make_pysteps_predictor,
    persistence_predictor,
)
from jalrakshak_ml.deep_nowcast.st_attention import STAttentionNowcasterV1
from jalrakshak_ml.deep_nowcast.unet_convgru import UNetConvGRUNowcaster
from jalrakshak_ml.nowcast.pysteps_adapter import PystepsNowcast

MODEL_CLASSES = {
    "convlstm_v3": ConvLSTMNowcasterV3,
    "unet_convgru_v1": UNetConvGRUNowcaster,
    "st_attention_nowcaster_v1": STAttentionNowcasterV1,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        required=True,
        choices=("persistence", "pysteps", *MODEL_CLASSES),
    )
    parser.add_argument("--checkpoint")
    parser.add_argument("--seed", type=int, default=26071)
    parser.add_argument("--config", default="configs/training/phase4e_final_v1.yaml")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--elevation", required=True)
    parser.add_argument("--normalization", required=True)
    parser.add_argument("--replay-audit", required=True)
    parser.add_argument("--channel-audit", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--input-policy", choices=tuple(ABLATIONS | SOURCE_STRESS_TESTS))
    args = parser.parse_args()

    dataset = Phase4EFinalDataset(
        args.dataset_root,
        args.replay_root,
        args.elevation,
        args.normalization,
        replay_audit_path=args.replay_audit,
        channel_audit_path=args.channel_audit,
        split="validation",
        seed=args.seed,
    )
    loader = make_dataloader(dataset, batch_size=4, seed=args.seed, shuffle=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.model == "persistence":
        predictor = persistence_predictor
    elif args.model == "pysteps":
        predictor = make_pysteps_predictor(PystepsNowcast())
    else:
        if not args.checkpoint:
            parser.error("Deep models require --checkpoint")
        config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
        model = MODEL_CLASSES[args.model](**config["models"][args.model]["kwargs"])
        checkpoint = torch.load(args.checkpoint, map_location=device, weights_only=False)
        if checkpoint.get("compatibility", {}).get("model_version") != model.model_version:
            raise ValueError("Checkpoint/model version mismatch")
        model.load_state_dict(checkpoint["model"])
        predictor = make_deep_predictor(model, device)

    grouped: dict[str, dict[str, list[np.ndarray]]] = {}
    sample_ids: list[str] = []
    for batch in loader:
        if args.input_policy:
            batch = apply_declared_mask(batch, args.input_policy, training_policy=False).tensors
        prediction = predictor(batch)
        if isinstance(prediction, torch.Tensor):
            prediction = prediction.detach().cpu().numpy()
        event_ids = list(batch["metadata"]["event_id"])
        issue_times = list(batch["metadata"]["issue_time"])
        sample_ids.extend(
            f"{event_id}:{issue_time}"
            for event_id, issue_time in zip(event_ids, issue_times, strict=True)
        )
        for position, event_id in enumerate(event_ids):
            record = grouped.setdefault(event_id, {"prediction": [], "target": [], "mask": []})
            record["prediction"].append(prediction[position : position + 1])
            record["target"].append(batch["target_physical"][position : position + 1].numpy())
            record["mask"].append(batch["target_mask"][position : position + 1].numpy())

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    event_records = []
    for event_id, record in sorted(grouped.items()):
        destination = output_root / f"{event_id}.npz"
        if destination.exists():
            raise FileExistsError(destination)
        part = destination.with_suffix(destination.suffix + ".part")
        with part.open("wb") as handle:
            np.savez_compressed(
                handle,
                prediction_mm_h=np.concatenate(record["prediction"]),
                target_mm_h=np.concatenate(record["target"]),
                valid_mask=np.concatenate(record["mask"]),
            )
        part.replace(destination)
        event_records.append({"event_id": event_id, "artifact": str(destination)})
    manifest = {
        "model": args.model,
        "seed": args.seed,
        "split": "validation",
        "events": event_records,
        "sample_count": len(dataset),
        "sample_ids": sample_ids,
        "input_policy": args.input_policy or "full_inputs",
        "zero_is_mask_not_measurement": bool(args.input_policy),
        "locked_test_accessed": False,
    }
    if args.checkpoint:
        manifest["checkpoint_sha256"] = hashlib.sha256(
            Path(args.checkpoint).read_bytes()
        ).hexdigest()
    manifest_path = output_root / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(manifest_path)
    part = manifest_path.with_suffix(manifest_path.suffix + ".part")
    part.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    part.replace(manifest_path)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
