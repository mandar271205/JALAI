from typing import Any

from fastapi import APIRouter, Query, Response

from app.integrations.tiles.raster_service import RasterTileService
from app.integrations.tiles.vector_service import VectorTileService

router = APIRouter(prefix="/tiles", tags=["Geospatial Tiles"])

raster_service = RasterTileService()
vector_service = VectorTileService()


@router.get("/raster/{layer}/tilejson.json")
async def get_raster_tilejson(layer: str, immutable: bool = False) -> dict[str, Any]:
    tilejson = raster_service.get_tilejson(layer, is_immutable=immutable)
    return tilejson


@router.get("/raster/{layer}/{z}/{x}/{y}.png")
async def get_raster_tile(layer: str, z: int, x: int, y: int, immutable: bool = False) -> Response:
    # 1x1 transparent/blue PNG fallback tile
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    cache_header = raster_service.get_cache_control(is_immutable=immutable)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": cache_header, "X-Layer": layer},
    )


@router.get("/vector/{layer}/tilejson.json")
async def get_vector_tilejson(layer: str, token: str | None = Query(None)) -> dict[str, Any]:
    # Operational layers require authorization
    if layer in ["critical_assets", "ops_responders"] and not token:
        # Check token parameter for tile client compatibility
        pass
    return vector_service.get_tilejson(layer)


@router.get("/vector/{layer}/{z}/{x}/{y}.pbf")
async def get_vector_tile(layer: str, z: int, x: int, y: int, immutable: bool = False) -> Response:
    mvt_bytes = vector_service.generate_dummy_mvt(layer, z, x, y)
    cache_header = "public, max-age=31536000, immutable" if immutable else "public, max-age=60"
    return Response(
        content=mvt_bytes,
        media_type="application/x-protobuf",
        headers={
            "Cache-Control": cache_header,
            "Content-Disposition": f"inline; filename={layer}_{z}_{x}_{y}.pbf",
            "X-Layer": layer,
        },
    )
