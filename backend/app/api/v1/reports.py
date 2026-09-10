"""Field Reports API endpoints for citizen reporting, signed media uploads, and visual corroboration."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.errors import ValidationError
from app.core.security import AuthenticatedUser, UserRole, get_current_user, require_roles
from app.core.security_hardening import MIMEValidator, malware_scanner
from app.domains.audit.service import audit_service
from app.domains.reports.repository import FieldReportsRepository

router = APIRouter(prefix="/reports", tags=["Reports"])

reports_repo = FieldReportsRepository(session=None)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
FORBIDDEN_EXTENSIONS = {".exe", ".sh", ".bat", ".php", ".py", ".elf", ".dll", ".bin"}


@router.get("", status_code=status.HTTP_200_OK)
async def list_reports(
    status: str | None = Query(None, description="Filter by verification status"),
    severity: str | None = Query(None, description="Filter by severity"),
    bbox: str | None = Query(None, description="Bounding box min_lon,min_lat,max_lon,max_lat"),
    incident_id: str | None = Query(None, description="Filter by incident ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List citizen reports with optional spatial/attribute filters and pagination."""
    return await reports_repo.list_reports(
        status=status,
        severity=severity,
        bbox=bbox,
        incident_id=incident_id,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_report_direct(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Create a new citizen report (direct submission or draft)."""
    draft = await reports_repo.create_draft_report(
        citizen_id=current_user.user_id,
        latitude=float(payload.get("latitude", 19.0715)),
        longitude=float(payload.get("longitude", 72.8759)),
        description=payload.get("description"),
        incident_id=payload.get("incident_id"),
    )
    # If image or checksum provided directly, finalize immediately
    if payload.get("checksum") or payload.get("image_url") or payload.get("file_content_base64"):
        finalized = await reports_repo.finalize_upload(
            upload_id=draft["report_id"],
            sha256_checksum=payload.get("checksum"),
            file_content_base64=payload.get("file_content_base64"),
            report_id=draft["report_id"],
        )
        return {
            **draft,
            "verification_status": finalized.get("verification_status", "AI_VERIFIED"),
            "image_url": payload.get("image_url") or finalized.get("image_url"),
            "visual_corroboration": finalized.get("visual_corroboration"),
            "verification": finalized.get("verification_job", {}).get("preliminary_result"),
        }
    return draft


@router.post("/draft", status_code=status.HTTP_201_CREATED)
async def create_draft_report(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Step 1 of direct signed-upload flow: creates draft report metadata."""
    return await reports_repo.create_draft_report(
        citizen_id=current_user.user_id,
        latitude=float(payload.get("latitude", 19.0715)),
        longitude=float(payload.get("longitude", 72.8759)),
        description=payload.get("description"),
        incident_id=payload.get("incident_id"),
    )


def _validate_upload_metadata(filename: str, content_type: str, file_size_bytes: int | None):
    ct = content_type.lower().split(";")[0].strip()
    if ct not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"Invalid or forbidden MIME type '{content_type}'. Allowed: {list(ALLOWED_MIME_TYPES)}"
        )
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in FORBIDDEN_EXTENSIONS:
        raise ValidationError(f"File extension '{ext}' is prohibited for security reasons.")
    if file_size_bytes and file_size_bytes > 10 * 1024 * 1024:
        raise ValidationError("File size exceeds the 10MB upload limit.")
    return ct


@router.post("/upload-intent", status_code=status.HTTP_201_CREATED)
async def create_upload_intent(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Step 2 (canonical): generates presigned URL for direct client -> S3 upload."""
    report_id = payload.get("report_id", "rep-temp-001")
    filename = payload.get("filename", "flood_photo.jpg")
    content_type = _validate_upload_metadata(
        filename=filename,
        content_type=payload.get("content_type", "image/jpeg"),
        file_size_bytes=payload.get("file_size_bytes"),
    )
    return await reports_repo.create_upload_intent(
        report_id=report_id,
        citizen_id=current_user.user_id,
        filename=filename,
        content_type=content_type,
        file_size_bytes=payload.get("file_size_bytes"),
    )


@router.post("/{report_id}/uploads", status_code=status.HTTP_201_CREATED)
async def create_report_upload_intent(
    report_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Step 2 (RESTful path): generates presigned upload URL for a specific report."""
    filename = payload.get("filename", "flood_photo.jpg")
    content_type = _validate_upload_metadata(
        filename=filename,
        content_type=payload.get("content_type", "image/jpeg"),
        file_size_bytes=payload.get("file_size_bytes"),
    )
    return await reports_repo.create_upload_intent(
        report_id=report_id,
        citizen_id=current_user.user_id,
        filename=filename,
        content_type=content_type,
        file_size_bytes=payload.get("file_size_bytes"),
    )


async def _handle_upload_finalize_core(payload: dict[str, Any], path_report_id: str | None = None) -> dict[str, Any]:
    upload_id = payload.get("upload_id")
    sha256 = payload.get("sha256_checksum")
    file_content_base64 = payload.get("file_content_base64")
    declared_mime = payload.get("content_type", "image/jpeg")
    content_bytes: bytes | None = None

    if file_content_base64:
        try:
            content_bytes = base64.b64decode(file_content_base64)
        except Exception:
            raise ValidationError("Invalid base64 encoding for file content.")

        if not MIMEValidator.validate_content(content_bytes, declared_mime):
            raise ValidationError(
                "File spoofing detected: binary signature does not match declared MIME type."
            )

        scan_result = await malware_scanner.scan(
            content_bytes, payload.get("filename", "upload.bin")
        )
        if not scan_result["is_clean"]:
            raise ValidationError(
                f"Malicious content detected by {scan_result['scanner']}: {scan_result['threat_name']}"
            )

    return await reports_repo.finalize_upload(
        upload_id=upload_id or path_report_id or "rep-temp-001",
        sha256_checksum=sha256,
        file_content_base64=file_content_base64,
        file_bytes=content_bytes,
        report_id=path_report_id or payload.get("report_id"),
    )


@router.post("/upload-finalize", status_code=status.HTTP_200_OK)
async def finalize_upload(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Step 3 (canonical): client notifies upload completion; triggers Groq vision & ML verification."""
    return await _handle_upload_finalize_core(payload)


@router.post("/{report_id}/uploads/complete", status_code=status.HTTP_200_OK)
async def complete_report_upload(
    report_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Step 3 (RESTful path): mark report upload complete and trigger Groq visual corroboration."""
    return await _handle_upload_finalize_core(payload, path_report_id=report_id)


@router.get("/{report_id}", status_code=status.HTTP_200_OK)
async def get_report_detail(
    report_id: str, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Retrieve full report detail including verification breakdown and visual evidence."""
    report = await reports_repo.get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Citizen report '{report_id}' not found",
        )
    return report


@router.get("/{report_id}/status", status_code=status.HTTP_200_OK)
async def get_report_status(
    report_id: str, current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Lightweight status query for mobile app polling."""
    rep_status = await reports_repo.get_report_status(report_id)
    if not rep_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Citizen report '{report_id}' not found",
        )
    return rep_status


@router.post("/{report_id}/review", status_code=status.HTTP_200_OK)
async def review_report(
    report_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(
        require_roles([UserRole.ANALYST, UserRole.MUNICIPAL_OFFICER, UserRole.ADMIN])
    ),
) -> dict[str, Any]:
    """Human review override of AI/heuristic verification status."""
    new_status = payload.get("status", "HUMAN_VERIFIED")
    notes = payload.get("notes")

    audit_entry = await audit_service.record_event(
        db=None,
        actor_id=current_user.user_id,
        actor_role=current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role),
        action="REPORT_REVIEW_OVERRIDE",
        target_entity="FIELD_REPORT",
        target_id=report_id,
        before_state={"status": "AI_VERIFIED", "report_id": report_id},
        after_state={"status": new_status, "report_id": report_id, "notes": notes},
        changes={"notes": notes, "status": new_status},
    )

    return {
        "report_id": report_id,
        "reviewed_by": current_user.user_id,
        "reviewer_role": current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role),
        "status": new_status,
        "notes": notes,
        "audit_event": {
            "log_id": audit_entry["log_id"],
            "action": audit_entry["action"],
            "before_hash": audit_entry["before_hash"],
            "after_hash": audit_entry["after_hash"],
        },
    }
