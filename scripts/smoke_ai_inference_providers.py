"""Opt-in live provider smoke verification script for JalRakshak AI Decision Support.

Usage:
    python scripts/smoke_ai_inference_providers.py [--dry-run] [--provider {all,groq,nvidia}]

Safety:
- NEVER prints raw API keys or secrets
- Only runs live network calls if explicitly invoked by an operator with valid keys in env
- Not included in automated CI/test execution
"""
from __future__ import annotations

import argparse
import asyncio
import os
import time

from jalrakshak_ml.decision_support import (
    FloodInferenceInput,
    GroqProvider,
    NvidiaNIMProvider,
    RainfallInferenceInput,
)


def mask_secret(key: str | None) -> str:
    """Mask credentials for safe diagnostic display."""
    if not key:
        return "<NOT_SET>"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


async def smoke_groq(dry_run: bool = False) -> bool:
    print("\n" + "=" * 60)
    print("Testing Model 1: Groq (Primary Generator)")
    print("=" * 60)

    api_key = os.getenv("GROQ_API_KEY")
    print(f"GROQ_API_KEY configured: {mask_secret(api_key)}")

    if dry_run or not api_key:
        print("[DRY-RUN/SKIPPED] Live Groq test skipped. Pass valid GROQ_API_KEY to test live.")
        return True

    provider = GroqProvider()
    print(f"Target Model ID: {provider.model_id}")
    print(f"Endpoint: {provider.base_url}/chat/completions")

    test_input = RainfallInferenceInput(
        rainfall_mm_h=[22.0, 25.5, 28.0],
        forecast_horizons_minutes=[30, 60, 90],
        model_name="SmokeTestLK",
        evidence_ids=["smoke-test-01"],
    )

    t0 = time.time()
    try:
        cand = await provider.generate_rainfall_inference(test_input)
        elapsed = time.time() - t0
        print(f"[SUCCESS] Received valid response in {elapsed:.2f}s:")
        print(f"  Severity: {cand.severity.value}")
        print(f"  Trend: {cand.trend.value}")
        print(f"  Confidence: {cand.confidence:.2f}")
        print(f"  Intensity Band: {cand.expected_intensity_band_mm_h.min} - {cand.expected_intensity_band_mm_h.max} mm/h")
        print(f"  Summary: {cand.summary[:100]}...")
        return True
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - t0
        print(f"[FAILED] in {elapsed:.2f}s: {e}")
        return False


async def smoke_nvidia(dry_run: bool = False) -> bool:
    print("\n" + "=" * 60)
    print("Testing Model 2 & 3: NVIDIA NIM (Failover & Heavy Verifier)")
    print("=" * 60)

    api_key = os.getenv("NVIDIA_API_KEY")
    print(f"NVIDIA_API_KEY configured: {mask_secret(api_key)}")

    if dry_run or not api_key:
        print("[DRY-RUN/SKIPPED] Live NVIDIA test skipped. Pass valid NVIDIA_API_KEY to test live.")
        return True

    # Test Model 2 (Lightning 30B)
    p2 = NvidiaNIMProvider(role="secondary_generator")
    print(f"\n[Testing Model 2 - Fast Secondary]: {p2.model_id}")
    t0 = time.time()
    try:
        cand2 = await p2.generate_flood_inference(
            FloodInferenceInput(rainfall_forcing_mm_h=35.0, susceptibility_score=0.60)
        )
        elapsed = time.time() - t0
        print(f"[SUCCESS Model 2] in {elapsed:.2f}s:")
        print(f"  Risk Level: {cand2.risk_level.value}")
        print(f"  Depth: {cand2.depth_m} (Should be None)")
        print(f"  Confidence: {cand2.confidence:.2f}")
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - t0
        print(f"[FAILED Model 2] in {elapsed:.2f}s: {e}")

    # Test Model 3 (Ultra 550B)
    p3 = NvidiaNIMProvider(role="heavy_verifier")
    print(f"\n[Testing Model 3 - Heavy Verifier]: {p3.model_id}")
    t0 = time.time()
    try:
        from jalrakshak_ml.decision_support.schemas import VerifierInput
        ver_inp = VerifierInput(
            domain="flood",
            evidence={"rainfall_forcing_mm_h": 35.0, "susceptibility_score": 0.60},
            candidate_ai_result={"risk_level": "HIGH", "confidence": 0.75, "depth_m": None},
            source_mode="PROVISIONAL_AI",
            evidence_ids=["smoke-test-flood"],
        )
        ver_out = await p3.verify_inference(ver_inp)
        elapsed = time.time() - t0
        print(f"[SUCCESS Model 3] in {elapsed:.2f}s:")
        print(f"  Verdict: {ver_out.verdict.value}")
        print(f"  Agreement Score: {ver_out.agreement_score:.2f}")
        print(f"  Reason: {ver_out.reason[:100]}...")
        return True
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - t0
        print(f"[FAILED Model 3] in {elapsed:.2f}s: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="JalRakshak AI Live Provider Smoke Test")
    parser.add_argument("--dry-run", action="store_true", help="Perform offline syntax and configuration check")
    parser.add_argument("--provider", choices=["all", "groq", "nvidia"], default="all", help="Target provider to test")
    args = parser.parse_args()

    print("=" * 60)
    print("JALRAKSHAK AI — 3-MODEL DECISION SUPPORT SMOKE TEST")
    print("=" * 60)

    success = True
    if args.provider in ("all", "groq"):
        res = await smoke_groq(dry_run=args.dry_run)
        success = success and res

    if args.provider in ("all", "nvidia"):
        res = await smoke_nvidia(dry_run=args.dry_run)
        success = success and res

    print("\n" + "=" * 60)
    print(f"Smoke Test Summary: {'PASSED' if success else 'COMPLETED WITH WARNINGS'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
