"""Run gated Phase 4E data/model smoke checks or train one architecture/seed."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import torch
import yaml

from jalrakshak_ml.deep_nowcast.convlstm_v3 import ConvLSTMNowcasterV3
from jalrakshak_ml.deep_nowcast.experiments import ABLATIONS, apply_declared_mask
from jalrakshak_ml.deep_nowcast.final_contracts import SEEDS
from jalrakshak_ml.deep_nowcast.final_dataset import Phase4EFinalDataset, SourceDropoutPolicy
from jalrakshak_ml.deep_nowcast.final_runner import (
    FinalValidationRunner,
    RunnerConfig,
    make_dataloader,
)
from jalrakshak_ml.deep_nowcast.st_attention import STAttentionNowcasterV1
from jalrakshak_ml.deep_nowcast.unet_convgru import UNetConvGRUNowcaster

MODEL_CLASSES = {
    "convlstm_v3": ConvLSTMNowcasterV3,
    "unet_convgru_v1": UNetConvGRUNowcaster,
    "st_attention_nowcaster_v1": STAttentionNowcasterV1,
}


class MaskedLoader:
    def __init__(self, loader, policy_name: str):
        self.loader = loader
        self.dataset = loader.dataset
        self.policy_name = policy_name

    def __iter__(self):
        for batch in self.loader:
            yield apply_declared_mask(batch, self.policy_name, training_policy=True).tensors

    def __len__(self):
        return len(self.loader)


def _run_config_hash(path: Path, experiment_id: str) -> str:
    digest = hashlib.sha256(path.read_bytes())
    digest.update(experiment_id.encode("utf-8"))
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("data-smoke", "batch-smoke", "model-smoke", "train"), required=True
    )
    parser.add_argument("--model", choices=tuple(MODEL_CLASSES))
    parser.add_argument("--seed", type=int, choices=SEEDS, default=26071)
    parser.add_argument("--config", default="configs/training/phase4e_final_v1.yaml")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--elevation", required=True)
    parser.add_argument("--normalization", required=True)
    parser.add_argument("--replay-audit", required=True)
    parser.add_argument("--channel-audit", required=True)
    parser.add_argument("--checkpoint-root", required=True)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--ablation", choices=tuple(ABLATIONS))
    parser.add_argument("--source-dropout", choices=("observation", "nwp", "terrain"))
    parser.add_argument("--source-dropout-probability", type=float, default=0.1)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("TRAINING_STARTED=false")
        print("Pass --execute only in the prepared Colab environment.")
        return

    config_path = Path(args.config)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    probability = args.source_dropout_probability if args.source_dropout else 0.0
    dropout = SourceDropoutPolicy(
        observation_probability=probability if args.source_dropout == "observation" else 0.0,
        nwp_probability=probability if args.source_dropout == "nwp" else 0.0,
        terrain_probability=probability if args.source_dropout == "terrain" else 0.0,
        trained_with_source_dropout=bool(args.source_dropout),
    )
    train = Phase4EFinalDataset(
        args.dataset_root,
        args.replay_root,
        args.elevation,
        args.normalization,
        replay_audit_path=args.replay_audit,
        channel_audit_path=args.channel_audit,
        split="train",
        seed=args.seed,
        source_dropout=dropout,
    )
    validation = Phase4EFinalDataset(
        args.dataset_root,
        args.replay_root,
        args.elevation,
        args.normalization,
        replay_audit_path=args.replay_audit,
        channel_audit_path=args.channel_audit,
        split="validation",
        seed=args.seed,
    )
    if args.mode == "data-smoke":
        print(json.dumps({"train": len(train), "validation": len(validation), "locked_test": 0}))
        return
    train_loader = make_dataloader(train, batch_size=4, seed=args.seed, shuffle=True)
    validation_loader = make_dataloader(validation, batch_size=4, seed=args.seed, shuffle=False)
    if args.ablation:
        train_loader = MaskedLoader(train_loader, args.ablation)
        validation_loader = MaskedLoader(validation_loader, args.ablation)
    if args.mode == "batch-smoke":
        batch = next(iter(train_loader))
        print(
            json.dumps(
                {
                    key: list(value.shape)
                    for key, value in batch.items()
                    if isinstance(value, torch.Tensor)
                }
            )
        )
        return
    if not args.model:
        parser.error("--model is required for model-smoke/train")
    model_config = config["models"][args.model]
    factory = lambda: MODEL_CLASSES[args.model](**model_config["kwargs"])
    if args.mode == "model-smoke":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = factory().to(device).eval()
        batch = next(iter(validation_loader))
        with torch.no_grad():
            output = FinalValidationRunner._call(model, batch, device)
        print(json.dumps({"output_shape": list(output.shape), "device": str(device)}))
        return

    git_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    experiment_id = (
        args.ablation
        or (
            f"source_dropout_{args.source_dropout}_{args.source_dropout_probability:g}"
            if args.source_dropout
            else None
        )
        or "full_inputs"
    )
    runner_config = RunnerConfig(
        checkpoint_root=Path(args.checkpoint_root) / experiment_id,
        epochs=args.epochs or int(config["training"]["epochs"]),
        batch_size=int(config["training"]["batch_size"]),
    )
    runner = FinalValidationRunner(
        runner_config,
        git_sha=git_sha,
        config_hash=_run_config_hash(config_path, experiment_id),
        normalization_hash=train.normalization_hash,
        replay_manifest_hash=train.replay_manifest_hash,
    )
    report = runner.train(
        factory,
        train_loader,
        validation_loader,
        architecture=args.model,
        seed=args.seed,
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
