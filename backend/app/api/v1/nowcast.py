from typing import Any

from fastapi import APIRouter, Depends

from app.integrations.ml.provider import MLProvider, get_ml_provider

router = APIRouter(prefix="/nowcast", tags=["Nowcast"])


@router.get("/manifest")
async def get_nowcast_manifest(
    ml_provider: MLProvider = Depends(get_ml_provider),
) -> dict[str, Any]:
    return await ml_provider.get_nowcast_manifest()
