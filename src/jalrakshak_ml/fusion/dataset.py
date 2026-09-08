"""Dedicated multi-model fusion dataset builder and feature extractor.

Aligns ground-truth GPM IMERG targets with provider forecasts:
- Persistence (lag-0)
- PySTEPS (optical flow)
- ConvLSTM V2 (experimental, explicitly flagged if unavailable)
- GFS (NWP historical replay)

Strict scientific rules enforced:
- Zero target leakage: target rainfall at forecast valid time is never included in features.
- Event-isolated Train and Validation splits.
- Common valid mask across all available providers and ground-truth observations.
- Explicit provider availability flags (no silent substitution or impersonation).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import zarr

from jalrakshak_ml.deep_nowcast.dataset import RainfallSequenceDataset
from jalrakshak_ml.fusion.contracts import (
    ConvLSTMProvider,
    ForecastResult,
    GFSReplayProvider,
    PersistenceProvider,
    PystepsProvider,
    _ensure_utc,
)
from jalrakshak_ml.fusion.gating import GateFeatureBuilder, GateFeatures
from jalrakshak_ml.fusion.uncertainty import (
    compute_ensemble_spread,
    compute_forecast_confidence,
    compute_provider_disagreement,
)


@dataclass(slots=True)
class FusionSample:
    """Single aligned sample for one issue sequence across all lead times."""

    event_id: str
    split: str
    issue_time: str
    horizons_min: list[int]
    ground_truth: np.ndarray  # [H, Y, X]
    valid_mask: np.ndarray    # [H, Y, X]
    provider_forecasts: dict[str, np.ndarray]  # name -> [H, Y, X]
    provider_availability: dict[str, bool]     # name -> bool
    features_by_horizon: list[np.ndarray]      # list of 1D feature vectors for leads
    feature_names: list[str]
    metadata: dict[str, Any]


class FusionDataset:
    """Prepares and serves aligned multi-provider nowcasting + NWP datasets."""

    def __init__(
        self,
        split: str,
        gpm_dataset_dir: str | Path = "data/processed/training/gpm_imerg_v07_mumbai_monsoon_expanded_v1",
        gfs_replay_root: str | Path = "data/processed/gfs_replay/gfs_mumbai_non_test_replay_v1",
        horizons_min: Sequence[int] = (30, 60, 90, 120),
        expected_providers: Sequence[str] = ("persistence", "pysteps", "convlstm_v2", "gfs"),
    ) -> None:
        self.split = str(split).lower()
        if self.split not in ("train", "validation", "test"):
            raise ValueError(f"Invalid split: {self.split}")
        self.gpm_dir = Path(gpm_dataset_dir)
        self.gfs_root = Path(gfs_replay_root)
        self.horizons_min = list(horizons_min)
        self.expected_providers = list(expected_providers)

        # Initialize providers
        self.persistence = PersistenceProvider()
        self.pysteps = PystepsProvider()
        self.convlstm = ConvLSTMProvider()  # is_available will be False if no checkpoint
        self.gfs = GFSReplayProvider(replay_root=self.gfs_root)
        self.feature_builder = GateFeatureBuilder(expected_providers=self.expected_providers)

        self._feature_names: list[str] = self._build_feature_names()
        self.samples: list[FusionSample] = []
        self._load_and_align()

    def _build_feature_names(self) -> list[str]:
        """Generate static feature column names matching to_feature_vector()."""
        names = [
            "lead_time_min",
            "current_rainfall_mean",
            "current_rainfall_max",
            "rain_regime",
            "gfs_forecast_age_hours",
            "available_providers_count",
            "issue_hour_utc",
            "rainfall_trend",
            "recent_accumulation",
        ]
        for pname in self.expected_providers:
            names.extend([
                f"{pname}_mean",
                f"{pname}_p90",
                f"{pname}_max",
                f"{pname}_valid_frac",
                f"{pname}_confidence",
                f"{pname}_quality",
                f"{pname}_disagreement",
                f"{pname}_is_available",
            ])
        # Cross-model ensemble features
        names.extend([
            "ensemble_mean",
            "ensemble_spread",
            "disagreement_mean",
        ])
        return names

    def _load_and_align(self) -> None:
        """Scan GPM sequence dataset and align GFS + nowcasting predictions."""
        manifest_path = self.gpm_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"GPM manifest missing at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        event_records = [e for e in manifest["events"] if e["split"] == self.split]
        if not event_records:
            raise ValueError(f"No events found for split {self.split}")

        leads = len(self.horizons_min)

        for event in event_records:
            event_id = event["event_id"]
            zarr_path = self.gpm_dir / event["path"]
            store = zarr.open(str(zarr_path), mode="r")
            rainfall_all = np.asarray(store["rainfall"], dtype=np.float32)
            time_all = [str(t) for t in store["time"][:]]
            mask_all = np.asarray(store["valid_mask"], dtype=bool)

            n_frames = len(time_all)
            history_len = 4
            horizon_len = leads
            window = history_len + horizon_len

            for start in range(n_frames - window + 1):
                hist_slice = slice(start, start + history_len)
                tgt_slice = slice(start + history_len, start + window)

                hist_rain = rainfall_all[hist_slice]
                target_rain = rainfall_all[tgt_slice]
                target_mask = mask_all[tgt_slice] & np.isfinite(target_rain)

                issue_time_str = time_all[start + history_len - 1]
                issue_dt = _ensure_utc(issue_time_str)

                # Generate nowcast predictions
                res_persist = self.persistence.predict(
                    history_frames=hist_rain,
                    issue_time=issue_dt,
                    lead_times=leads,
                    event_id=event_id,
                )
                res_pysteps = self.pysteps.predict(
                    history_frames=hist_rain,
                    issue_time=issue_dt,
                    lead_times=leads,
                    event_id=event_id,
                )

                provider_results: dict[str, ForecastResult] = {
                    "persistence": res_persist,
                    "pysteps": res_pysteps,
                }

                # Try GFS replay lookup
                if self.gfs.is_available:
                    try:
                        res_gfs = self.gfs.predict(
                            issue_time=issue_dt,
                            lead_times=leads,
                            event_id=event_id,
                        )
                        provider_results["gfs"] = res_gfs
                    except KeyError:
                        pass

                # ConvLSTM V2 if available
                if self.convlstm.is_available:
                    try:
                        res_conv = self.convlstm.predict(
                            history_frames=hist_rain,
                            issue_time=issue_dt,
                            lead_times=leads,
                            event_id=event_id,
                        )
                        provider_results["convlstm_v2"] = res_conv
                    except Exception:
                        pass

                # Compute strict intersection valid mask
                common_mask = target_mask.copy()
                for res in provider_results.values():
                    common_mask &= res.valid_mask[:leads] & np.isfinite(res.rainfall_mm_h[:leads])

                # Extract features per horizon
                features_h = []
                recent_acc = float(np.sum(hist_rain[-2:])) if hist_rain.shape[0] >= 2 else 0.0
                rain_trend = float(np.mean(hist_rain[-1]) - np.mean(hist_rain[-2])) if hist_rain.shape[0] >= 2 else 0.0

                for h_idx, h_min in enumerate(self.horizons_min):
                    gf = self.feature_builder.build_features_for_horizon(
                        lead_idx=h_idx,
                        horizon_min=h_min,
                        issue_time=issue_dt,
                        provider_results=provider_results,
                        history_frames=hist_rain,
                    )
                    base_vec = [
                        float(gf.shared.lead_time_min),
                        gf.shared.current_rainfall_mean_mm_h,
                        gf.shared.current_rainfall_max_mm_h,
                        float(gf.shared.rain_regime),
                        gf.shared.gfs_forecast_age_hours,
                        float(gf.shared.available_providers_count),
                        float(gf.shared.issue_hour_utc),
                        rain_trend,
                        recent_acc,
                    ]
                    # Per-provider block
                    available_forecasts = []
                    for pname in self.expected_providers:
                        if pname in provider_results:
                            pf = gf.providers[pname]
                            base_vec.extend([
                                pf.mean_forecast_mm_h,
                                pf.p90_forecast_mm_h,
                                pf.max_forecast_mm_h,
                                pf.valid_fraction,
                                pf.model_confidence,
                                pf.quality_score,
                                pf.disagreement_from_ensemble_mean,
                                1.0,
                            ])
                            available_forecasts.append(provider_results[pname].rainfall_mm_h[h_idx])
                        else:
                            base_vec.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

                    # Ensemble summary features
                    if available_forecasts:
                        c_mask = common_mask[h_idx]
                        if np.any(c_mask):
                            valid_vals = [f[c_mask] for f in available_forecasts]
                            ens_m = float(np.mean([np.mean(v) for v in valid_vals]))
                            ens_s = float(np.std([np.mean(v) for v in valid_vals])) if len(valid_vals) > 1 else 0.0
                            dis_m = float(np.mean(np.max(np.stack(valid_vals, axis=0), axis=0) - np.min(np.stack(valid_vals, axis=0), axis=0))) if len(valid_vals) > 1 else 0.0
                        else:
                            ens_m, ens_s, dis_m = 0.0, 0.0, 0.0
                    else:
                        ens_m, ens_s, dis_m = 0.0, 0.0, 0.0

                    base_vec.extend([ens_m, ens_s, dis_m])
                    vec_clean = np.nan_to_num(np.asarray(base_vec, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
                    features_h.append(vec_clean)

                provider_forecasts = {
                    pname: res.rainfall_mm_h[:leads] for pname, res in provider_results.items()
                }
                provider_avail = {
                    pname: (pname in provider_results) for pname in self.expected_providers
                }

                sample = FusionSample(
                    event_id=event_id,
                    split=self.split,
                    issue_time=issue_time_str,
                    horizons_min=self.horizons_min,
                    ground_truth=target_rain,
                    valid_mask=common_mask,
                    provider_forecasts=provider_forecasts,
                    provider_availability=provider_avail,
                    features_by_horizon=features_h,
                    feature_names=self._feature_names,
                    metadata={
                        "event_id": event_id,
                        "split": self.split,
                        "start_frame": start,
                        "valid_cell_count": int(np.sum(common_mask)),
                    },
                )
                self.samples.append(sample)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> FusionSample:
        return self.samples[idx]

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    def get_tabular_data(self) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray, np.ndarray]:
        """Flatten dataset across samples and horizons for tabular fitting.

        Returns
        -------
        X : [N, D] feature matrix
        Y_preds : dict of pname -> [N, Y, X] or mean per sample
        Y_true : [N, Y, X] target rainfall
        Mask : [N, Y, X] common valid boolean mask
        """
        x_list = []
        y_true_list = []
        mask_list = []
        preds_dict: dict[str, list[np.ndarray]] = {p: [] for p in self.expected_providers}

        for s in self.samples:
            for h_idx in range(len(self.horizons_min)):
                x_list.append(s.features_by_horizon[h_idx])
                y_true_list.append(s.ground_truth[h_idx])
                mask_list.append(s.valid_mask[h_idx])
                for pname in self.expected_providers:
                    if s.provider_availability[pname]:
                        preds_dict[pname].append(s.provider_forecasts[pname][h_idx])
                    else:
                        preds_dict[pname].append(np.zeros_like(s.ground_truth[h_idx]))

        X = np.nan_to_num(np.stack(x_list, axis=0), nan=0.0, posinf=0.0, neginf=0.0)
        Mask = np.stack(mask_list, axis=0)
        Y_raw = np.nan_to_num(np.stack(y_true_list, axis=0), nan=0.0, posinf=0.0, neginf=0.0)
        Y_true = np.where(Mask, Y_raw, 0.0).astype(np.float32)
        Y_preds = {
            p: np.where(Mask, np.nan_to_num(np.stack(preds_dict[p], axis=0), nan=0.0, posinf=0.0, neginf=0.0), 0.0).astype(np.float32)
            for p in self.expected_providers
        }
        return X, Y_preds, Y_true, Mask

