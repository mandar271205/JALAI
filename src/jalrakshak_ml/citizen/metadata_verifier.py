"""Replaceable metadata verifier; no image/NLP model and no automatic truth labels."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Protocol

from .verification_v2 import CitizenReportV2


class ReportVerifier(Protocol):
    def verify(self, report: CitizenReportV2, *, now: datetime,
               neighbors: tuple[CitizenReportV2, ...] = ()) -> dict: ...


def distance_m(a: CitizenReportV2, b: CitizenReportV2) -> float:
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat, dlon = lat2 - lat1, math.radians(b.longitude - a.longitude)
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1., math.sqrt(value)))


class MetadataVerifier:
    version = 'phase11_citizen_metadata_rules_v1'

    def verify(self, report: CitizenReportV2, *, now: datetime,
               neighbors: tuple[CitizenReportV2, ...] = ()) -> dict:
        report.validate()
        if now.tzinfo is None:
            raise ValueError('Explicit timezone-aware evaluation clock required')
        if report.rainfall_context_mm_h is not None and not math.isfinite(report.rainfall_context_mm_h):
            raise ValueError('Finite rainfall context required')
        age = (now - datetime.fromisoformat(report.timestamp)).total_seconds()
        location_ok = 72.75 <= report.longitude <= 73.05 and 18.85 <= report.latitude <= 19.30
        contradictions, evidence = [], []
        if age < -300:
            contradictions.append('timestamp_in_future')
        if not location_ok:
            contradictions.append('outside_mumbai_pilot')
        duplicates, nearby = set(report.duplicate_report_ids), set()
        normalized = ' '.join(report.text.lower().split())
        for other in neighbors:
            other.validate()
            if other.report_id == report.report_id or other.event_id != report.event_id:
                continue
            dt = abs((datetime.fromisoformat(report.timestamp) - datetime.fromisoformat(other.timestamp)).total_seconds())
            if dt > 1800 or distance_m(report, other) > 500:
                continue
            media_a = (report.image_metadata or {}).get('sha256')
            media_b = (other.image_metadata or {}).get('sha256')
            if normalized == ' '.join(other.text.lower().split()) or (media_a and media_a == media_b):
                duplicates.add(other.report_id)
            else:
                nearby.add(other.report_id)
        nearby -= duplicates
        if report.rainfall_context_mm_h is not None and report.rainfall_context_mm_h < 1 and nearby:
            contradictions.append('low_current_rain_with_flood_reports; delayed_flooding_possible')
        media = report.image_metadata or {}
        media_type = media.get('mime_type', '')
        if media and media_type and not media_type.startswith(('image/', 'video/')):
            contradictions.append('unsupported_media_type')
        evidence.extend([{'rule': 'time_plausibility', 'passed': -300 <= age <= 86400, 'age_seconds': age},
                         {'rule': 'pilot_location', 'passed': location_ok},
                         {'rule': 'spatiotemporal_neighbors', 'unique_reports': len(nearby), 'radius_m': 500, 'window_s': 1800},
                         {'rule': 'duplicates', 'report_ids': sorted(duplicates)},
                         {'rule': 'media_metadata', 'present': bool(media), 'content_verified': False},
                         {'rule': 'source_history', 'available': False}])
        score = (.25 * location_ok + .25 * (-300 <= age <= 86400) + .25 * min(len(nearby) / 3, 1)
                 + .125 * (report.rainfall_context_mm_h is not None and report.rainfall_context_mm_h >= 10)
                 + .125 * (report.model_hazard_context is not None and report.model_hazard_context >= .5))
        if contradictions:
            score *= .5
        return {'report_id': report.report_id, 'version': self.version, 'verification_score': score,
                'rule_evidence': evidence, 'contradictions': contradictions, 'needs_manual_review': True,
                'confidence': None, 'confidence_semantics': 'not calibrated; score is heuristic support only',
                'verified_flood_truth': False, 'CITIZEN_ML_MODEL_AVAILABLE': False,
                'CITIZEN_VERIFICATION_RULE_BASED': True}
