import logging

from app.workers.celery_app import celery

logger = logging.getLogger("celery.tasks")


@celery.task(name="app.workers.tasks.health_ping")
def health_ping():
    logger.info("Celery health ping received")
    return {"status": "pong"}


@celery.task(name="app.workers.tasks.trigger_weather_ingestion")
def trigger_weather_ingestion():
    logger.info("Weather ingestion scheduled task triggered")
    return {"status": "queued"}
