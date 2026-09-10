import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class MLProvider(ABC):
    @abstractmethod
    async def get_nowcast_manifest(self) -> dict[str, Any]:
        """Fetch the latest precipitation nowcast manifest."""
        pass

    @abstractmethod
    async def get_inundation_manifest(self) -> dict[str, Any]:
        """Fetch the latest hydrodynamic flood depth map manifest."""
        pass

    @abstractmethod
    async def get_risk_cells(
        self, bbox: str | None = None, valid_time: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch scored H3 risk cells within bbox / time."""
        pass

    @abstractmethod
    async def verify_report(
        self, report_id: str, image_url: str | None, description: str | None
    ) -> dict[str, Any]:
        """Vision AI verification for a citizen field report."""
        pass


class StubMLProvider(MLProvider):
    """
    Deterministic stub implementation using contract fixtures.
    Guarantees backend development and testing never blocks on ML service availability.
    """

    def __init__(self, fixtures_path: str | None = None):
        if not fixtures_path:
            # Locate contracts/fixtures/demo-event relative to backend package or workspace
            base = Path(__file__).resolve().parents[3]
            p = base / "contracts" / "fixtures" / "demo-event"
            if not p.exists():
                p = Path(__file__).resolve().parents[4] / "backend" / "contracts" / "fixtures" / "demo-event"
            self.fixtures_path = p
        else:
            self.fixtures_path = Path(fixtures_path)

    def _read_fixture(self, filename: str) -> Any:
        file_path = self.fixtures_path / filename
        if file_path.exists():
            with open(file_path) as f:
                return json.load(f)
        # Fallback inline fixtures if path not found
        fallback_fixtures = {
            "nowcast-manifest.json": {
                "manifest_id": "stub-nowcast-001",
                "run_id": "stub-nowcast-001",
                "generated_at": "2026-09-08T09:30:00Z",
                "valid_from": "2026-09-08T09:30:00Z",
                "valid_to": "2026-09-08T11:30:00Z",
                "lead_time_minutes": 120,
                "cog_url": "http://localhost:9000/jalrakshak/rasters/nowcast_latest.tif",
                "bounds": [72.75, 18.88, 73.02, 19.28],
                "model_version": "precip-nowcast-unet-v2",
                "data_version": "imd-mumbai-radar-20260908",
                "operational_real_data": False,
                "is_fallback": True,
                "is_degraded": True,
                "warnings": ["STUB FALLBACK DATA: Static offline fixture, not live ML output."],
            },
            "inundation-manifest.json": {
                "manifest_id": "stub-inundation-001",
                "run_id": "stub-inundation-001",
                "generated_at": "2026-09-08T09:30:00Z",
                "valid_time": "2026-09-08T10:00:00Z",
                "depth_cog_url": "http://localhost:9000/jalrakshak/rasters/flood_depth_latest.tif",
                "velocity_cog_url": "http://localhost:9000/jalrakshak/rasters/flood_velocity_latest.tif",
                "max_depth_meters": None,  # Physical depth uncalibrated
                "relative_inundation_index": 0.65,
                "is_physically_calibrated": False,
                "depth_unit": "relative_inundation_index",
                "model_version": "hydro-2d-shallow-water-v3",
                "data_version": "cwc-elevation-srtm30",
                "is_fallback": True,
                "is_degraded": True,
                "warnings": ["STUB FALLBACK DATA: Uncalibrated relative susceptibility index."],
            },
            "risk-cells.json": [
                {
                    "h3_cell_id": "8860145b53fffff",
                    "valid_time": "2026-09-08T09:30:00Z",
                    "risk_level": "SEVERE",
                    "confidence": 0.50,
                    "flood_depth_m": None,  # Physical depth uncalibrated
                    "rainfall_rate_mm_h": 68.5,
                    "inundation_susceptibility_score": 0.85,
                    "ward_id": "WARD-12-DHARAVI",
                    "model_version": "v1.2.0-hydro",
                    "data_version": "imd-wrf-20260908",
                    "is_fallback": True,
                }
            ],
        }
        return fallback_fixtures.get(filename, {})

    async def get_nowcast_manifest(self) -> dict[str, Any]:
        data = self._read_fixture("nowcast-manifest.json")
        if isinstance(data, dict):
            data["is_fallback"] = True
            data["operational_real_data"] = False
        return data

    async def get_inundation_manifest(self) -> dict[str, Any]:
        data = self._read_fixture("inundation-manifest.json")
        if isinstance(data, dict):
            data["is_fallback"] = True
            data["is_physically_calibrated"] = False
            data["max_depth_meters"] = None
        return data

    async def get_risk_cells(
        self, bbox: str | None = None, valid_time: str | None = None
    ) -> list[dict[str, Any]]:
        cells = self._read_fixture("risk-cells.json")
        if isinstance(cells, list):
            for cell in cells:
                if isinstance(cell, dict):
                    cell["is_fallback"] = True
                    cell["flood_depth_m"] = None
        return cells

    async def verify_report(
        self, report_id: str, image_url: str | None, description: str | None
    ) -> dict[str, Any]:
        return {
            "report_id": report_id,
            "verification_status": "AI_VERIFIED",
            "verification_state": "HEURISTIC",
            "ai_confidence": 0.5,
            "detected_water_level_cm": None,  # Physical water depth unsupported
            "is_flood_related": True,
            "is_calibrated": False,
            "is_fallback": True,
            "model_version": "stub-vision-flood-classifier-v1.4",
            "warnings": [
                "STUB FALLBACK DATA: Heuristic stub verification. Not scientifically calibrated. Physical water depth is unsupported (null). Final verification mandates human analyst authorization."
            ],
            "provenance": {
                "method": "stub_fallback",
                "is_fallback": True,
                "requires_human_analyst_review": True,
            },
        }


def get_ml_provider() -> MLProvider:
    from app.core.config import get_settings

    settings = get_settings()
    if getattr(settings, "ML_PROVIDER", "stub").lower() == "service":
        from app.integrations.ml.http_provider import HttpMLProvider

        return HttpMLProvider(
            base_url=settings.ML_SERVICE_URL,
            auth_token=settings.ML_SERVICE_TOKEN,
            fallback_stub=StubMLProvider(),
        )
    return StubMLProvider()
