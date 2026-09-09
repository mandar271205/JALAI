from abc import ABC, abstractmethod
from typing import Any


class RoutingProvider(ABC):
    @abstractmethod
    async def compute_lower_risk_route(
        self, origin: dict[str, float], destination: dict[str, float], risk_aversion: float = 1.0
    ) -> dict[str, Any]:
        """Compute safe, flood-averse route between origin and destination."""
        pass


class StubRoutingProvider(RoutingProvider):
    async def compute_lower_risk_route(
        self, origin: dict[str, float], destination: dict[str, float], risk_aversion: float = 1.0
    ) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [origin.get("longitude", 72.85), origin.get("latitude", 19.05)],
                            [72.86, 19.06],
                            [
                                destination.get("longitude", 72.87),
                                destination.get("latitude", 19.07),
                            ],
                        ],
                    },
                    "properties": {
                        "distance_meters": 3420.5,
                        "duration_seconds": 650.0,
                        "max_flood_depth_m": 0.05,
                        "risk_score": "LOW",
                        "route_mode": "evacuation_safe",
                    },
                }
            ],
        }


def get_routing_provider() -> RoutingProvider:
    return StubRoutingProvider()
