"""Serving module for JalRakshak ML Inference Microservice."""
from jalrakshak_ml.serving.app import app
from jalrakshak_ml.serving.service import MLServingService, ml_service

__all__ = ["app", "ml_service", "MLServingService"]
