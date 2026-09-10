from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    assets,
    audit,
    dashboard,
    devices,
    incidents,
    inundation,
    mobile,
    models,
    notifications,
    nowcast,
    optimization,
    replay,
    reports,
    responders,
    risk,
    routes,
    sync,
    tiles,
    watch_locations,
    weather,
)
from app.api.v1 import (
    map as map_router,
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(weather.router)
api_v1_router.include_router(models.router)
api_v1_router.include_router(nowcast.router)
api_v1_router.include_router(inundation.router)
api_v1_router.include_router(risk.router)
api_v1_router.include_router(incidents.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(routes.router)
api_v1_router.include_router(alerts.router)
api_v1_router.include_router(assets.router)
api_v1_router.include_router(tiles.router)
api_v1_router.include_router(watch_locations.router)
api_v1_router.include_router(notifications.router)
api_v1_router.include_router(responders.router)
api_v1_router.include_router(sync.router)
api_v1_router.include_router(replay.router)
api_v1_router.include_router(optimization.router)
api_v1_router.include_router(audit.router)
api_v1_router.include_router(mobile.router)
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(map_router.router)
api_v1_router.include_router(devices.router)
