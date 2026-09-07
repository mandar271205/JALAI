from __future__ import annotations

from datetime import datetime, timedelta, timezone
import numpy as np
import xarray as xr

from .base import WeatherAdapter


class SyntheticRainAdapter(WeatherAdapter):
    source_name = "synthetic_demo"

    def fetch(
        self,
        bbox_wgs84: list[float],
        steps: int = 4,
        minutes_per_step: int = 10,
        height: int = 128,
        width: int = 128,
        seed: int = 71,
    ) -> xr.Dataset:
        west, south, east, north = bbox_wgs84
        rng = np.random.default_rng(seed)

        lon = np.linspace(west, east, width)
        lat = np.linspace(north, south, height)  # north -> south for raster row order
        yy, xx = np.mgrid[0:height, 0:width]

        frames = []
        for t in range(steps):
            cx = width * (0.25 + 0.12 * t)
            cy = height * (0.45 + 0.04 * t)
            sigma = width * 0.12
            storm = 55.0 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma**2))
            background = rng.gamma(shape=1.2, scale=0.35, size=(height, width))
            rain = np.clip(storm + background - 0.3, 0.0, None).astype("float32")
            frames.append(rain)

        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        start = now - timedelta(minutes=minutes_per_step * (steps - 1))
        times = [start + timedelta(minutes=minutes_per_step * i) for i in range(steps)]

        ds = xr.Dataset(
            data_vars={
                "rainfall_rate": (("time", "lat", "lon"), np.stack(frames))
            },
            coords={
                "time": np.array([np.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
                "lat": lat,
                "lon": lon,
            },
            attrs={
                "source": self.source_name,
                "crs": "EPSG:4326",
                "units": "mm/h",
                "timezone": "UTC",
            },
        )
        ds["rainfall_rate"].attrs["units"] = "mm/h"
        return ds
