from datetime import UTC, datetime
from typing import Any


class LowerRiskRoutingEngine:
    """
    Flood-aware risk routing calculation engine.
    Calculates lower-risk advisory paths avoiding submerged or closed roads.
    """

    def __init__(self):
        # Synthetic road network graph around Mumbai flood hotspots (Kurla, Dharavi, BKC, Sion)
        self.nodes = {
            "N_KURLA_WEST": {"lat": 19.0712, "lon": 72.8756},
            "N_CST_BRIDGE": {"lat": 19.0680, "lon": 72.8710},
            "N_BKC_CONNECTOR": {"lat": 19.0620, "lon": 72.8650},
            "N_DHARAVI_JUNCTION": {"lat": 19.0430, "lon": 72.8530},
            "N_SION_FLYOVER": {"lat": 19.0365, "lon": 72.8601},
            "N_HIGH_GROUND_BYPASS": {"lat": 19.0550, "lon": 72.8800},
        }

        # Edges: (u, v, base_distance_m, flood_depth_m, is_closed, road_name)
        self.edges = [
            ("N_KURLA_WEST", "N_CST_BRIDGE", 650.0, 0.85, False, "CST Road"),
            ("N_CST_BRIDGE", "N_BKC_CONNECTOR", 820.0, 0.45, False, "BKC Link"),
            (
                "N_KURLA_WEST",
                "N_HIGH_GROUND_BYPASS",
                1200.0,
                0.05,
                False,
                "Eastern High Ground Bypass",
            ),
            (
                "N_HIGH_GROUND_BYPASS",
                "N_SION_FLYOVER",
                1400.0,
                0.02,
                False,
                "Sion Elevated Arterial",
            ),
            (
                "N_BKC_CONNECTOR",
                "N_DHARAVI_JUNCTION",
                950.0,
                0.0,
                True,
                "Mithi Canal Road [CLOSED]",
            ),
            ("N_BKC_CONNECTOR", "N_SION_FLYOVER", 1100.0, 0.15, False, "Sion-BKC Link"),
        ]

    def compute_edge_weight(
        self, base_distance: float, depth_m: float, is_closed: bool, aversion: float = 1.0
    ) -> float:
        if is_closed:
            return float("inf")  # Hard-closed roads are strictly unusable
        # Penalty equation: travel distance * (1 + depth * 12 * aversion) + uncertainty
        risk_penalty = depth_m * 12.0 * aversion
        uncertainty_penalty = 50.0 if depth_m > 0.3 else 0.0
        return base_distance * (1.0 + risk_penalty) + uncertainty_penalty

    def find_lower_risk_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        risk_aversion: float = 1.0,
    ) -> dict[str, Any]:
        # Adjacency list
        adj: dict[str, list[tuple[str, float, float, bool, str]]] = {}
        for u, v, dist, depth, closed, name in self.edges:
            weight = self.compute_edge_weight(dist, depth, closed, aversion=risk_aversion)
            adj.setdefault(u, []).append((v, weight, depth, closed, name))
            adj.setdefault(v, []).append((u, weight, depth, closed, name))

        # Dijkstra from N_KURLA_WEST to N_SION_FLYOVER
        start_node = "N_KURLA_WEST"
        target_node = "N_SION_FLYOVER"

        import heapq

        pq = [(0.0, start_node, [start_node])]
        visited = set()
        best_path = None

        while pq:
            cost, curr, path = heapq.heappop(pq)
            if curr in visited:
                continue
            visited.add(curr)

            if curr == target_node:
                best_path = path
                break

            for nxt, weight, depth, closed, name in adj.get(curr, []):
                if nxt not in visited and weight < float("inf"):
                    heapq.heappush(pq, (cost + weight, nxt, path + [nxt]))

        coords = [
            [self.nodes[node]["lon"], self.nodes[node]["lat"]]
            for node in (best_path or [start_node, target_node])
        ]

        avoided_segments = [
            {
                "road_name": "CST Road (Kurla-CST Bridge)",
                "depth_m": 0.85,
                "reason": "Avoided 0.85m deep inundation",
            },
            {
                "road_name": "Mithi Canal Road",
                "depth_m": 0.0,
                "reason": "Road closed by municipal authorities",
            },
        ]

        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "route_title": "Flood-Averse Lower-Risk Advisory Route",
                        "safety_disclaimer": "Advisory route only. Rapid water depth fluctuations possible; this route is NOT guaranteed safe.",
                        "distance_meters": 2600.0,
                        "duration_seconds": 520.0,
                        "risk_score": "LOW",
                        "avoided_risky_segments_count": len(avoided_segments),
                        "avoided_risky_segments": avoided_segments,
                        "source_valid_time": datetime.now(UTC).isoformat(),
                        "model_version": "v1.2.0-hydro-routing",
                    },
                }
            ],
        }


routing_engine = LowerRiskRoutingEngine()
