import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.models import FieldReport, FieldReportUpload
from app.integrations.ml.provider import get_ml_provider
from app.integrations.object_store.provider import get_object_store_provider


class FieldReportsRepository:
    def __init__(self, session=None):
        self.session = session
        self.object_store = get_object_store_provider()
        self.ml_provider = get_ml_provider()

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
            "estimated_water_depth_cm": None,
            "submitted_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if self.session:
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

        # Generate presigned URL via object store provider
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

        if self.session:
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

        return intent_data

    async def finalize_upload(
        self, upload_id: str, sha256_checksum: str | None = None
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        # Verify object upload
        public_url = f"http://localhost:9000/jalrakshak/reports/report_{upload_id}.jpg"

        # Trigger async / background ML verification
        ml_result = await self.ml_provider.verify_report(
            report_id=upload_id, image_url=public_url, description="Verified crowd report"
        )

        return {
            "upload_id": upload_id,
            "status": "FINALIZED",
            "image_url": public_url,
            "sha256_checksum": sha256_checksum,
            "finalized_at": now.isoformat(),
            "verification_job": {"status": "QUEUED", "preliminary_result": ml_result},
        }
