"""Optional classical baseline for genuinely labeled citizen reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def inspect_training_readiness(manifest_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    eligible = [row for row in payload.get("samples", []) if row.get("supervised_eligible")]
    splits = {row.get("split") for row in eligible}
    genuine = bool(eligible) and all(
        row.get("label_provenance", {}).get("method")
        not in {"heuristic", "pseudo_label", "model_prediction"}
        for row in eligible
    )
    ready = (
        genuine
        and {"train", "validation"}.issubset(splits)
        and len({row["label"] for row in eligible}) >= 2
    )
    return {
        "CITIZEN_GENUINE_LABELS_AVAILABLE": genuine,
        "CITIZEN_ML_TRAINING_READY": ready,
        "CITIZEN_ML_TRAINING_STARTED": False,
        "eligible_samples": len(eligible),
        "reason": None if ready else "genuine multi-class train/validation samples are unavailable",
    }


def train_classical_baseline(manifest_path: str | Path) -> dict[str, Any]:
    """Train TF-IDF + structured logistic regression only after readiness checks."""
    readiness = inspect_training_readiness(manifest_path)
    if not readiness["CITIZEN_ML_TRAINING_READY"]:
        raise RuntimeError(readiness["reason"])
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows = [r for r in payload["samples"] if r["supervised_eligible"]]
    try:
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import (
            average_precision_score,
            brier_score_loss,
            confusion_matrix,
            precision_recall_fscore_support,
        )
        from sklearn.pipeline import FeatureUnion, Pipeline
        from sklearn.preprocessing import FunctionTransformer
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install the 'ml' optional dependencies") from exc
    x = [{"text": row["text"], "structured": row["structured_features"]} for row in rows]
    y = [row["label"] for row in rows]
    train = [i for i, row in enumerate(rows) if row["split"] == "train"]
    valid = [i for i, row in enumerate(rows) if row["split"] == "validation"]
    transformer = FeatureUnion(
        [
            (
                "text",
                Pipeline(
                    [
                        (
                            "select",
                            FunctionTransformer(
                                lambda values: [item["text"] for item in values], validate=False
                            ),
                        ),
                        ("tfidf", TfidfVectorizer(min_df=1)),
                    ]
                ),
            ),
            (
                "structured",
                Pipeline(
                    [
                        (
                            "select",
                            FunctionTransformer(
                                lambda values: [item["structured"] for item in values],
                                validate=False,
                            ),
                        ),
                        ("vectorize", DictVectorizer()),
                    ]
                ),
            ),
        ]
    )
    model = Pipeline([("features", transformer), ("classifier", LogisticRegression(max_iter=500))])
    model.fit([x[i] for i in train], [y[i] for i in train])
    prediction = model.predict([x[i] for i in valid])
    probabilities = model.predict_proba([x[i] for i in valid])
    precision, recall, f1, _ = precision_recall_fscore_support(
        [y[i] for i in valid], prediction, average="macro", zero_division=0
    )
    labels = sorted(set(y))
    result = {
        "model": "TFIDF_STRUCTURED_LOGISTIC_REGRESSION",
        "precision_macro": precision,
        "recall_macro": recall,
        "f1_macro": f1,
        "confusion_matrix": confusion_matrix(
            [y[i] for i in valid], prediction, labels=labels
        ).tolist(),
        "labels": labels,
        "pr_auc": "NOT_EVALUABLE_MULTICLASS_OR_SAMPLE_LIMIT",
        "calibration": "NOT_EVALUABLE_MULTICLASS_OR_SAMPLE_LIMIT",
    }
    if len(labels) == 2 and len(valid) >= 2:
        positive = labels[1]
        truth = [int(y[i] == positive) for i in valid]
        positive_probability = probabilities[:, list(model.classes_).index(positive)]
        result["pr_auc"] = float(average_precision_score(truth, positive_probability))
        result["calibration"] = {
            "brier_score": float(brier_score_loss(truth, positive_probability)),
            "positive_class": positive,
            "calibrated_probability_claim_allowed": False,
        }
    return result
