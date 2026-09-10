"""JalRakshak AI — Unified System Constants.

Shared across Backend, ML, Web, and Mobile interfaces.
"""
from __future__ import annotations

# Forecast horizons in minutes
FORECAST_HORIZONS_MINUTES: tuple[int, ...] = (30, 60, 90, 120)

# Standard severity tiers
SEVERITY_LEVELS: tuple[str, ...] = ("LOW", "MODERATE", "HIGH", "SEVERE")

# Standard risk categories
RISK_LEVELS: tuple[str, ...] = ("LOW", "MODERATE", "HIGH", "SEVERE")

# Rainfall intensity thresholds (mm/h)
RAINFALL_THRESHOLD_LIGHT: float = 2.5
RAINFALL_THRESHOLD_MODERATE: float = 7.5
RAINFALL_THRESHOLD_HEAVY: float = 35.0
RAINFALL_THRESHOLD_VERY_HEAVY: float = 65.0

# Supported operational modes
OPERATIONAL_MODES: tuple[str, ...] = (
    "NUMERICAL_MODEL",
    "MODEL_PLUS_AI",
    "PROVISIONAL_AI",
    "DETERMINISTIC_FALLBACK",
    "INSUFFICIENT_EVIDENCE",
)
