"""JalRakshak AI Decision Support package: Unified Model-First + Backend AI Fallback Inference Layer."""

from jalrakshak_ml.decision_support.flood_inference import infer_flood
from jalrakshak_ml.decision_support.groq_provider import GroqProvider
from jalrakshak_ml.decision_support.nvidia_provider import NvidiaNIMProvider
from jalrakshak_ml.decision_support.provenance import (
    create_provenance,
    sanitize_provenance_for_frontend,
)
from jalrakshak_ml.decision_support.provider_router import ProviderRouter
from jalrakshak_ml.decision_support.rainfall_inference import infer_rainfall
from jalrakshak_ml.decision_support.schemas import (
    DecisionSupportStatusResponse,
    FloodCandidateResult,
    FloodInferenceInput,
    FloodInferenceOutput,
    InferenceMode,
    InferenceProvenance,
    IntensityBand,
    RainfallCandidateResult,
    RainfallInferenceInput,
    RainfallInferenceOutput,
    SeverityLevel,
    TrendDirection,
    VerifierInput,
    VerifierOutput,
    VerifierVerdict,
)

__all__ = [
    "DecisionSupportStatusResponse",
    "FloodCandidateResult",
    "FloodInferenceInput",
    "FloodInferenceOutput",
    "GroqProvider",
    "InferenceMode",
    "InferenceProvenance",
    "IntensityBand",
    "NvidiaNIMProvider",
    "ProviderRouter",
    "RainfallCandidateResult",
    "RainfallInferenceInput",
    "RainfallInferenceOutput",
    "SeverityLevel",
    "TrendDirection",
    "VerifierInput",
    "VerifierOutput",
    "VerifierVerdict",
    "create_provenance",
    "infer_flood",
    "infer_rainfall",
    "sanitize_provenance_for_frontend",
]
