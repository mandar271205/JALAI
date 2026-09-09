from typing import Any

from fastapi import APIRouter, Depends

from app.integrations.ml.provider import MLProvider, get_ml_provider

router = APIRouter(prefix="/inundation", tags=["Inundation"])


@router.get("/manifest")
async def get_inundation_manifest(
    ml_provider: MLProvider = Depends(get_ml_provider),
) -> dict[str, Any]:
    return await ml_provider.get_inundation_manifest()
