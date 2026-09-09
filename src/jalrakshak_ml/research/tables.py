"""Research result exporters that preserve missingness."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

TABLE_TYPES = {
    "rainfall_model_tournament",
    "ablation_results",
    "source_dropout_results",
    "probabilistic_calibration",
    "physics_benchmark",
    "fno_benchmark",
    "risk_benchmark",
    "citizen_verification_benchmark",
    "source_capability_matrix",
    "claim_readiness_matrix",
}


def _normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: ("NA" if value is None else value) for key, value in row.items()} for row in rows]


def export_research_table(table_type: str, rows: list[dict[str, Any]], path: str | Path) -> Path:
    if table_type not in TABLE_TYPES:
        raise ValueError("Unsupported research table type")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize(rows)
    if destination.suffix == ".json":
        destination.write_text(
            json.dumps({"table_type": table_type, "rows": normalized}, indent=2), encoding="utf-8"
        )
    elif destination.suffix == ".csv":
        fields = sorted({key for row in normalized for key in row})
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fields)
            writer.writeheader()
            writer.writerows(normalized)
    elif destination.suffix == ".md":
        fields = sorted({key for row in normalized for key in row})
        lines = [
            f"# {table_type}",
            "",
            "| " + " | ".join(fields) + " |",
            "| " + " | ".join("---" for _ in fields) + " |",
        ]
        lines.extend(
            "| " + " | ".join(str(row.get(key, "NA")) for key in fields) + " |"
            for row in normalized
        )
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        raise ValueError("Table output must be .json, .csv, or .md")
    return destination
