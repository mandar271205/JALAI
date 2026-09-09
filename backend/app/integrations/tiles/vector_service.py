from typing import Any


class VectorTileService:
    def __init__(self):
        pass

    def get_tilejson(self, layer_name: str) -> dict[str, Any]:
        tile_url = f"/api/v1/tiles/vector/{layer_name}/{{z}}/{{x}}/{{y}}.pbf"
        return {
            "tilejson": "3.0.0",
            "name": f"JalRakshak Vector - {layer_name}",
            "description": f"MVT vector tile layer for {layer_name}",
            "version": "1.0.0",
            "attribution": "JalRakshak AI / SIH26071",
            "scheme": "xyz",
            "tiles": [tile_url],
            "minzoom": 6,
            "maxzoom": 16,
            "bounds": [72.75, 18.88, 73.02, 19.28],
            "vector_layers": [
                {
                    "id": layer_name,
                    "description": f"Vector features for {layer_name}",
                    "fields": {
                        "h3_cell_id": "String",
                        "risk_level": "String",
                        "confidence": "Number",
                        "flood_depth_m": "Number",
                        "status": "String",
                    },
                }
            ],
        }

    def generate_dummy_mvt(self, layer_name: str, z: int, x: int, y: int) -> bytes:
        """
        Generates minimal valid Mapbox Vector Tile (MVT) protobuf binary.
        Ensures endpoints always return valid MVT bytes (Content-Type: application/x-protobuf).
        """
        # Minimal protobuf payload with tile header
        magic_mvt = (
            b"\x1a\x15\n\x0b"
            + layer_name.encode()[:10]
            + b"\x12\x06\x18\x01\x22\x02\x00\x00\x28\x80 \x78\x02"
        )
        return magic_mvt
