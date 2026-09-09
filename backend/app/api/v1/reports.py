from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.errors import ValidationError
from app.core.security import AuthenticatedUser, UserRole, get_current_user, require_roles
from app.core.security_hardening import MIMEValidator, malware_scanner
from app.domains.audit.service import audit_service
from app.domains.reports.repository import FieldReportsRepository

router = APIRouter(prefix="/reports", tags=["Reports"])

reports_repo = FieldReportsRepository(session=None)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_report_direct(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    # Convenience endpoint for all-in-one or legacy report submission
    draft = await reports_repo.create_draft_report(
        citizen_id=current_user.user_id,
        latitude=float(payload.get("latitude", 19.0715)),
        longitude=float(payload.get("longitude", 72.8759)),
        description=payload.get("description"),
        incident_id=payload.get("incident_id"),
    )
    finalized = await reports_repo.finalize_upload(
        upload_id=draft["report_id"], sha256_checksum=payload.get("checksum")
    )
    return {
        **draft,
        "verification_status": "AI_VERIFIED",
        "image_url": payload.get("image_url") or finalized.get("image_url"),
        "verification": finalized.get("verification_job", {}).get("preliminary_result"),
    }


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


ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
FORBIDDEN_EXTENSIONS = {".exe", ".sh", ".bat", ".php", ".py", ".elf", ".dll", ".bin"}


@router.post("/upload-intent", status_code=status.HTTP_201_CREATED)
async def create_upload_intent(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Step 2 of direct signed-upload flow: generates presigned URL for direct client -> S3 upload."""
    report_id = payload.get("report_id", "rep-temp-001")
    filename = payload.get("filename", "flood_photo.jpg")
    content_type = payload.get("content_type", "image/jpeg").lower().split(";")[0].strip()
    file_size_bytes = payload.get("file_size_bytes")

    # Security validation
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"Invalid or forbidden MIME type '{content_type}'. Allowed: {list(ALLOWED_MIME_TYPES)}"
        )

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in FORBIDDEN_EXTENSIONS:
        raise ValidationError(f"File extension '{ext}' is prohibited for security reasons.")

    if file_size_bytes and file_size_bytes > 10 * 1024 * 1024:
        raise ValidationError("File size exceeds the 10MB upload limit.")

    return await reports_repo.create_upload_intent(
        report_id=report_id,
        citizen_id=current_user.user_id,
        filename=filename,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
    )


@router.post("/upload-finalize")
async def finalize_upload(
    payload: dict[str, Any], current_user: AuthenticatedUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Step 3 of direct signed-upload flow: client notifies upload completion; triggers ML vision verification."""
    import base64

    upload_id = payload.get("upload_id")
    sha256 = payload.get("sha256_checksum")
    file_content_base64 = payload.get("file_content_base64")
    declared_mime = payload.get("content_type", "image/jpeg")

    # If binary content payload is provided for inspection
    if file_content_base64:
        try:
            content_bytes = base64.b64decode(file_content_base64)
        except Exception:
            raise ValidationError("Invalid base64 encoding for file content.")

        # 1. MIME magic byte validation
        if not MIMEValidator.validate_content(content_bytes, declared_mime):
            raise ValidationError(
                "File spoofing detected: binary signature does not match declared MIME type."
            )

        # 2. Malware scanning integration
        scan_result = await malware_scanner.scan(
            content_bytes, payload.get("filename", "upload.bin")
        )
        if not scan_result["is_clean"]:
            raise ValidationError(
                f"Malicious content detected by {scan_result['scanner']}: {scan_result['threat_name']}"
            )

    return await reports_repo.finalize_upload(upload_id=upload_id, sha256_checksum=sha256)


@router.post("/{report_id}/review")
async def review_report(
    report_id: str,
    payload: dict[str, Any],
    current_user: AuthenticatedUser = Depends(
        require_roles([UserRole.ANALYST, UserRole.MUNICIPAL_OFFICER, UserRole.ADMIN])
    ),
) -> dict[str, Any]:
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
