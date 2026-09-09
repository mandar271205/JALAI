import logging
import os
import re
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

logger = logging.getLogger(__name__)

# Sensitive patterns to scrub
SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|secret|token|authorization|cookie|key|credential)", re.IGNORECASE
)
AADHAAR_PATTERN = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
PHONE_PATTERN = re.compile(r"\b(\+?91[\-\s]?)?[6789]\d{9}\b")


def scrub_sensitive_value(val: Any) -> Any:
    if isinstance(val, str):
        if "data:image" in val:
            return "[IMAGE_DATA_REDACTED]"
        if len(val) > 200 and ("base64" in val or val.endswith("==")):
            return "[BASE64_PAYLOAD_REDACTED]"
        scrubbed = AADHAAR_PATTERN.sub("[AADHAAR_REDACTED]", val)
        scrubbed = PHONE_PATTERN.sub("[PHONE_REDACTED]", scrubbed)
        return scrubbed
    elif isinstance(val, dict):
        return {
            k: (
                "[SECRET_REDACTED]"
                if SENSITIVE_KEY_PATTERNS.search(str(k))
                else scrub_sensitive_value(v)
            )
            for k, v in val.items()
        }
    elif isinstance(val, list):
        return [scrub_sensitive_value(item) for item in val]
    return val


def sentry_before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """
    Strips citizen PII, auth headers, passwords, and raw image blobs from error reports.
    """
    request_data = event.get("request", {})
    if "headers" in request_data:
        headers = request_data["headers"]
        for header_name in ["authorization", "cookie", "x-api-key"]:
            if header_name in headers:
                headers[header_name] = "[REDACTED]"

    if "data" in request_data:
        request_data["data"] = scrub_sensitive_value(request_data["data"])

    # Scrub extra contexts and breadcrumbs
    if "extra" in event:
        event["extra"] = scrub_sensitive_value(event["extra"])

    return event


def sentry_before_breadcrumb(
    breadcrumb: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Sanitizes breadcrumb messages and payload metadata.
    """
    if "message" in breadcrumb and breadcrumb["message"]:
        breadcrumb["message"] = scrub_sensitive_value(breadcrumb["message"])
    if "data" in breadcrumb and breadcrumb["data"]:
        breadcrumb["data"] = scrub_sensitive_value(breadcrumb["data"])
    return breadcrumb


def init_sentry(dsn: str | None = None, environment: str = "development") -> bool:
    """
    Initializes Sentry error tracking strictly from environment DSN.
    Returns True if initialized, False if disabled.
    """
    sentry_dsn = dsn or os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        logger.info("Sentry DSN not provided; crash reporting running in disabled mode.")
        return False

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=environment,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.2,
        send_default_pii=False,  # Strict PII protection
        before_send=sentry_before_send,
        before_breadcrumb=sentry_before_breadcrumb,
    )
    logger.info("Sentry error tracking successfully initialized with PII scrubbing.")
    return True
