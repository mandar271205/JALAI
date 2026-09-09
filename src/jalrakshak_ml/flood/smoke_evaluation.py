"""CPU checkpoint diagnostics and scenario-level statistics, without skill promotion."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch

from .fno import FloodFNO
from .forensic import read_json, safe_path, sha


def depth_metrics(predicted: np.ndarray, target: np.ndarray, mask: np.ndarray) -> dict:
    if predicted.shape != target.shape or mask.shape != target.shape or mask.dtype != bool:
        raise ValueError('Aligned predictions, targets and boolean masks required')
    if not mask.any() or not np.isfinite(predicted[mask]).all() or not np.isfinite(target[mask]).all():
        raise ValueError('Finite supported depth required')
    if (target[mask] < 0).any() or (predicted[mask] < 0).any():
        raise ValueError('Depth cannot be negative')
    p, y = predicted[mask].astype(float), target[mask].astype(float)
    error = p - y
    output = {'mae_m': float(np.abs(error).mean()), 'rmse_m': float(np.sqrt((error ** 2).mean())),
              'bias_m': float(error.mean()), 'valid_cells': len(y), 'thresholds': {}}
    for threshold in (.01, .05, .10, .30):
        a, b = p >= threshold, y >= threshold
        tp, fp, fn, tn = [int(v.sum()) for v in (a & b, a & ~b, ~a & b, ~a & ~b)]
        def ratio(n, d):
            return n / d if d else None
        output['thresholds'][str(threshold)] = {
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, 'positive_support': tp + fn,
            'status': 'SUPPORTED' if tp + fn else 'NO_REFERENCE_POSITIVES',
            'iou': ratio(tp, tp + fp + fn), 'csi': ratio(tp, tp + fp + fn),
            'f1': ratio(2 * tp, 2 * tp + fp + fn), 'precision': ratio(tp, tp + fp),
            'recall': ratio(tp, tp + fn)}
    return output


def scenario_summary(metrics: dict[str, dict], baseline: dict[str, dict] | None = None,
                     *, seed: int = 26071, min_bootstrap_scenarios: int = 5) -> dict:
    if not metrics:
        raise ValueError('Scenario metrics required')
    macro = {key: float(np.mean([m[key] for m in metrics.values()]))
             for key in ('mae_m', 'rmse_m', 'bias_m')}
    interval = None
    if baseline is not None and set(baseline) != set(metrics):
        raise ValueError('Paired bootstrap needs identical scenario IDs')
    enough = len(metrics) >= max(5, min_bootstrap_scenarios)
    if enough and baseline is not None:
        differences = np.asarray([m['mae_m'] - baseline[s]['mae_m'] for s, m in metrics.items()])
        draws = np.random.default_rng(seed).choice(differences, (2000, len(differences))).mean(axis=1)
        interval = np.quantile(draws, [.025, .975]).tolist()
    return {'scenario_count': len(metrics), 'per_scenario': metrics, 'macro': macro,
            'paired_mae_difference_interval_95': interval,
            'bootstrap_status': 'PAIRED_SCENARIO_BOOTSTRAP' if interval else 'INSUFFICIENT_SUPPORT_OR_NO_PAIRED_BASELINE',
            'independent_pixel_bootstrap': False}


def evaluate_checkpoint(root: Path, *, dataset_dir: str = 'data/processed/flood/dataset',
                        checkpoint_path: str = 'models/flood_fno_smoke.pt', repeats: int = 3) -> dict:
    """Evaluate known local smoke evidence; old head zero is peak-depth diagnostic only."""
    ds = safe_path(root, dataset_dir)
    checkpoint = safe_path(root, checkpoint_path)
    payload = torch.load(checkpoint, map_location='cpu', weights_only=True)
    physics_path = ds / 'physics_reference_manifest.json'
    norm_path = ds / 'fno_train_only_normalization.json'
    if payload['physics_dataset_manifest_sha256'] != sha(physics_path) or payload['normalization_sha256'] != sha(norm_path):
        raise ValueError('Checkpoint dataset/normalization hash mismatch')
    manifest, norm = read_json(physics_path), read_json(norm_path)
    ids = [r['scenario_id'] for r in manifest['records'] if r['split'] == 'validation']
    train_ids = {r['scenario_id'] for r in manifest['records'] if r['split'] == 'train'}
    if train_ids & set(ids) or set(norm['fitted_scenario_ids']) != train_ids:
        raise ValueError('Scenario split/normalization leakage')
    x = np.load(ds / 'val_inputs.npy', allow_pickle=False)
    y = np.load(ds / 'val_targets.npy', allow_pickle=False)
    if x.shape[0] != len(ids) or y.shape[0] != len(ids):
        raise ValueError('Validation membership mismatch')
    state = payload['model']
    width = state['lift.weight'].shape[0]
    modes = state['spectral.0.weight'].shape[-1]
    model = FloodFNO(x.shape[1], width=width, modes=modes,
                     output_horizons=payload['model_config']['output_horizons'])
    model.load_state_dict(state, strict=True)
    model.eval()
    torch.set_num_threads(2)
    means = np.asarray([norm['input_statistics'][ch]['mean'] for ch in norm['channel_order']])
    stds = np.asarray([norm['input_statistics'][ch]['std'] for ch in norm['channel_order']])
    inputs = torch.tensor((x - means[None, :, None, None]) / stds[None, :, None, None], dtype=torch.float32)
    if not np.isfinite(y).all() or not torch.isfinite(inputs).all():
        raise ValueError('Nonfinite evaluation arrays')
    with torch.inference_mode():
        model(inputs)  # warm-up excluded
        latencies = []
        for _ in range(max(1, repeats)):
            start = time.perf_counter()
            predictions = model(inputs).numpy()
            latencies.append(time.perf_counter() - start)
        single = []
        for sample in inputs:
            start = time.perf_counter()
            model(sample[None])
            single.append(time.perf_counter() - start)
    repeated = y.shape[1] > 1 and bool(np.all(y == y[:, :1]))
    metrics = {sid: depth_metrics(predictions[i, 0], y[i, 0], np.ones_like(y[i, 0], dtype=bool))
               for i, sid in enumerate(ids)}
    return {**scenario_summary(metrics), 'status': 'SMOKE_ONLY_QUARANTINED_SPATIAL_SEMANTICS' if repeated else 'SMOKE_ONLY',
            'target_semantics': 'head_zero_vs_maximum_depth; no forecast-horizon skill claimed' if repeated else manifest.get('target_semantics'),
            'checkpoint_sha256': sha(checkpoint), 'checkpoint_epoch': payload['epoch'],
            'checkpoint_git_commit': payload['git_commit'], 'dataset_sha256': sha(physics_path),
            'normalization_sha256': sha(norm_path), 'latency': {'device': 'cpu', 'threads': 2,
            'batch_size': len(ids), 'batch_seconds': latencies, 'per_sample_seconds': single,
            'gpu_latency': None, 'measured_speedup': None},
            'FNO_SCIENTIFICALLY_VALIDATED': False, 'FNO_CALIBRATED': False, 'FNO_OPERATIONAL': False,
            'limitations': ['One validation scenario supports descriptive smoke metrics only.',
                            'Legacy spatial/forcing defects invalidate Mumbai predictive skill claims.',
                            'Original Phase 10 latency constants were not measurements; replaced by timed CPU inference.']}
