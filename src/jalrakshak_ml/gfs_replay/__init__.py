"""Standalone Phase 4A GFS preparation; never reads the legacy weather cube."""

from .core import select_gfs_forecast_as_of

__all__ = ["select_gfs_forecast_as_of"]
