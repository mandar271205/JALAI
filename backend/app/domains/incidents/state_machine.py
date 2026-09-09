from enum import StrEnum

from app.core.errors import ValidationError


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    MITIGATING = "MITIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    DISMISSED = "DISMISSED"


# Permitted state transition map
ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DETECTED: {IncidentStatus.OPEN, IncidentStatus.DISMISSED},
    IncidentStatus.OPEN: {IncidentStatus.ACKNOWLEDGED, IncidentStatus.DISMISSED},
    IncidentStatus.ACKNOWLEDGED: {IncidentStatus.MITIGATING, IncidentStatus.DISMISSED},
    IncidentStatus.MITIGATING: {IncidentStatus.RESOLVED, IncidentStatus.DISMISSED},
    IncidentStatus.RESOLVED: {IncidentStatus.CLOSED, IncidentStatus.OPEN},
    IncidentStatus.CLOSED: set(),
    IncidentStatus.DISMISSED: set(),
}


def validate_transition(current_status: str, target_status: str, reason: str | None = None):
    try:
        curr = IncidentStatus(current_status.upper())
        tgt = IncidentStatus(target_status.upper())
    except ValueError as e:
        raise ValidationError(f"Invalid incident status: {e}")

    if tgt == IncidentStatus.DISMISSED and (not reason or not reason.strip()):
        raise ValidationError("Transition to DISMISSED requires a mandatory non-empty reason.")

    allowed = ALLOWED_TRANSITIONS.get(curr, set())
    if tgt not in allowed:
        raise ValidationError(
            f"Illegal incident transition from '{curr.value}' to '{tgt.value}'. "
            f"Permitted next states: {[s.value for s in allowed]}"
        )
    return tgt
