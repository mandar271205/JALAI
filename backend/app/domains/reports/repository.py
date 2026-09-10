"""Field Reports repository for citizen report persistence and verification."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.models import FieldReport, FieldReportUpload
from app.integrations.ai.vision_service import get_vision_service
from app.integrations.ml.provider import get_ml_provider
from app.integrations.object_store.provider import get_object_store_provider

logger = logging.getLogger("jalrakshak.domains.reports.repository")

# Shared storage for stateful mock/unit testing when session is None
_MEMORY_REPORTS: dict[str, dict[str, Any]] = {}
_MEMORY_UPLOADS: dict[str, dict[str, Any]] = {}


class FieldReportsRepository:
    def __init__(self, session=None):
        self.session = session
        self.object_store = get_object_store_provider()
        self.ml_provider = get_ml_provider()
        self.vision_service = get_vision_service()

    async def create_draft_report(
        self,
        citizen_id: str,
        latitude: float,
        longitude: float,
        description: str | None = None,
        incident_id: str | None = None,
    ) -> dict[str, Any]:
        report_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        report = {
            "report_id": report_id,
            "incident_id": incident_id,
            "citizen_id": citizen_id,
            "latitude": latitude,
            "longitude": longitude,
            "description": description,
            "image_url": None,
            "verification_status": "DRAFT",
            "ai_confidence": None,
            "estimated_water_depth_cm": None,  # Strictly None - never fabricated
            "visual_corroboration": None,
            "submitted_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        _MEMORY_REPORTS[report_id] = report

        if self.session:
            try:
                db_report = FieldReport(
                    report_id=report_id,
                    incident_id=incident_id,
                    citizen_id=citizen_id,
                    latitude=latitude,
                    longitude=longitude,
                    description=description,
                    verification_status="DRAFT",
                    submitted_at=now,
                    updated_at=now,
                )
                self.session.add(db_report)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB persist failed for draft report %s: %s", report_id, exc)

        return report

    async def create_upload_intent(
        self,
        report_id: str,
        citizen_id: str,
        filename: str,
        content_type: str = "image/jpeg",
        file_size_bytes: int | None = None,
    ) -> dict[str, Any]:
        upload_id = str(uuid.uuid4())
        safe_filename = filename.replace("/", "_").replace(" ", "_")
        object_key = f"reports/{report_id}/{upload_id}_{safe_filename}"
        expires_seconds = 900  # 15 minutes
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=expires_seconds)

        presigned_url = await self.object_store.get_presigned_url(
            object_key, expires_seconds=expires_seconds
        )

        intent_data = {
            "upload_id": upload_id,
            "report_id": report_id,
            "citizen_id": citizen_id,
            "object_key": object_key,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
            "presigned_url": presigned_url,
            "expires_at": expires_at.isoformat(),
            "status": "PENDING",
        }

        _MEMORY_UPLOADS[upload_id] = intent_data
        if report_id in _MEMORY_REPORTS:
            _MEMORY_REPORTS[report_id]["upload_id"] = upload_id

        if self.session:
            try:
                db_upload = FieldReportUpload(
                    upload_id=upload_id,
                    citizen_id=citizen_id,
                    report_id=report_id,
                    object_key=object_key,
                    content_type=content_type,
                    file_size_bytes=file_size_bytes,
                    presigned_url=presigned_url,
                    expires_at=expires_at,
                    status="PENDING",
                    created_at=now,
                )
                self.session.add(db_upload)
                await self.session.commit()
            except Exception as exc:
                logger.warning("DB persist failed for upload intent %s: %s", upload_id, exc)

        return intent_data

    async def finalize_upload(
        self,
        upload_id: str,
        sha256_checksum: str | None = None,
        file_content_base64: str | None = None,
        file_bytes: bytes | None = None,
        report_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        public_url = f"http://localhost:9000/jalrakshak/reports/report_{upload_id}.jpg"

        target_report_id = report_id
        if not target_report_id and upload_id in _MEMORY_UPLOADS:
            target_report_id = _MEMORY_UPLOADS[upload_id].get("report_id")

        # 1. Trigger ML verification
        ml_result = await self.ml_provider.verify_report(
            report_id=upload_id, image_url=public_url, description="Verified crowd report"
        )

        # 2. Trigger Groq Vision Corroboration
        vision_result: dict[str, Any] | None = None
        try:
            if file_content_base64 or file_bytes:
                vision_result = await self.vision_service.analyze_image(
                    image_bytes=file_bytes,
                    image_b64=file_content_base64,
                    user_context="Citizen field report upload",
                )
            else:
                # Corroborate with public image url
                vision_result = await self.vision_service.analyze_image(
                    image_url=public_url,
                    user_context="Citizen field report upload",
                )
        except Exception as exc:
            logger.warning("Vision corroboration failed for upload %s: %s", upload_id, exc)
            vision_result = self.vision_service._fallback_result(str(exc))

        # Enforce scientific sanctity: exact_depth_m MUST BE None
        if vision_result:
            vision_result["exact_depth_m"] = None

        # Update in-memory record if report is tracked
        if target_report_id and target_report_id in _MEMORY_REPORTS:
            rep = _MEMORY_REPORTS[target_report_id]
            rep["image_url"] = public_url
            rep["verification_status"] = "AI_VERIFIED"
            rep["ai_confidence"] = vision_result.get("confidence", 0.75) if vision_result else 0.50
            rep["estimated_water_depth_cm"] = None  # Strictly None
            rep["visual_corroboration"] = vision_result
            rep["updated_at"] = now.isoformat()

        if upload_id in _MEMORY_UPLOADS:
            _MEMORY_UPLOADS[upload_id]["status"] = "FINALIZED"
            _MEMORY_UPLOADS[upload_id]["sha256_checksum"] = sha256_checksum

        if self.session and target_report_id:
            try:
                from sqlalchemy import select

                stmt = select(FieldReport).where(FieldReport.report_id == target_report_id)
                res = await self.session.execute(stmt)
                db_rep = res.scalars().first()
                if db_rep:
                    db_rep.image_url = public_url
                    db_rep.verification_status = "AI_VERIFIED"
                    db_rep.ai_confidence = vision_result.get("confidence", 0.75) if vision_result else 0.50
                    db_rep.updated_at = now
                    await self.session.commit()
            except Exception as exc:
                logger.warning("DB update failed during finalize for %s: %s", target_report_id, exc)

        return {
            "upload_id": upload_id,
            "report_id": target_report_id or upload_id,
            "status": "FINALIZED",
            "image_url": public_url,
            "sha256_checksum": sha256_checksum,
            "finalized_at": now.isoformat(),
            "verification_status": "AI_VERIFIED",
            "visual_corroboration": vision_result,
            "verification_job": {
                "status": "QUEUED",
                "preliminary_result": ml_result,
                "visual_corroboration": vision_result,
            },
        }

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        """Fetch full report detail by report_id."""
        if self.session:
            try:
                from sqlalchemy import select

                stmt = select(FieldReport).where(FieldReport.report_id == report_id)
                res = await self.session.execute(stmt)
                row = res.scalars().first()
                if row:
                    cached = _MEMORY_REPORTS.get(report_id, {})
                    return {
                        "report_id": row.report_id,
                        "incident_id": row.incident_id,
                        "citizen_id": row.citizen_id,
                        "latitude": row.latitude,
                        "longitude": row.longitude,
                        "description": row.description,
                        "image_url": row.image_url,
                        "verification_status": row.verification_status,
                        "ai_confidence": row.ai_confidence,
                        "estimated_water_depth_cm": row.estimated_water_depth_cm,
                        "visual_corroboration": cached.get("visual_corroboration"),
                        "verified_by": row.verified_by,
                        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
            except Exception as exc:
                logger.warning("DB lookup failed for report %s: %s", report_id, exc)

        return _MEMORY_REPORTS.get(report_id)

    async def list_reports(
        self,
        status: str | None = None,
        severity: str | None = None,
        bbox: str | None = None,
        incident_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List reports with filtering and pagination."""
        all_reports: list[dict[str, Any]] = []

        if self.session:
            try:
                from sqlalchemy import select

                stmt = select(FieldReport)
                if status:
                    stmt = stmt.where(FieldReport.verification_status == status)
                if incident_id:
                    stmt = stmt.where(FieldReport.incident_id == incident_id)
                res = await self.session.execute(stmt.limit(limit).offset(offset))
                rows = res.scalars().all()
                for row in rows:
                    cached = _MEMORY_REPORTS.get(row.report_id, {})
                    all_reports.append(
                        {
                            "report_id": row.report_id,
                            "incident_id": row.incident_id,
                            "citizen_id": row.citizen_id,
                            "latitude": row.latitude,
                            "longitude": row.longitude,
                            "description": row.description,
                            "image_url": row.image_url,
                            "verification_status": row.verification_status,
                            "ai_confidence": row.ai_confidence,
                            "estimated_water_depth_cm": row.estimated_water_depth_cm,
                            "visual_corroboration": cached.get("visual_corroboration"),
                            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
                            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                        }
                    )
                if all_reports:
                    return all_reports
            except Exception as exc:
                logger.warning("DB query failed in list_reports: %s", exc)

        # Fallback to in-memory store
        reports = list(_MEMORY_REPORTS.values())

        if status:
            reports = [r for r in reports if r.get("verification_status") == status]
        if incident_id:
            reports = [r for r in reports if r.get("incident_id") == incident_id]

        if bbox:
            try:
                parts = [float(x.strip()) for x in bbox.split(",")]
                if len(parts) == 4:
                    min_lon, min_lat, max_lon, max_lat = parts
                    reports = [
                        r
                        for r in reports
                        if min_lon <= r["longitude"] <= max_lon
                        and min_lat <= r["latitude"] <= max_lat
                    ]
            except Exception as exc:
                logger.warning("Failed to parse bbox '%s': %s", bbox, exc)

        return reports[offset : offset + limit]

    async def get_report_status(self, report_id: str) -> dict[str, Any] | None:
        """Lightweight status query for mobile app polling."""
        rep = await self.get_report(report_id)
        if not rep:
            return None
        return {
            "report_id": rep["report_id"],
            "verification_status": rep["verification_status"],
            "ai_confidence": rep.get("ai_confidence"),
            "image_url": rep.get("image_url"),
            "updated_at": rep.get("updated_at"),
        }
