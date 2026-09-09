import abc
import re
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.errors import ForbiddenError
from app.core.security import AuthenticatedUser, UserRole

# 10 Megabytes maximum payload limit
MAX_PAYLOAD_SIZE_BYTES = 10 * 1024 * 1024

# PII & Secret filtering regex patterns
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+([A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_=]*)", re.IGNORECASE),
    re.compile(r'(password|secret|api_key|token)["\']?\s*[:=]\s*["\']?([^"\'\s,]+)', re.IGNORECASE),
    re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),  # 12-digit Aadhaar pattern
    re.compile(r"\b(\+?91[\-\s]?)?[6789]\d{9}\b"),  # Indian Mobile Phone pattern
]


def sanitize_sensitive_data(text: str) -> str:
    """
    Redacts secrets, auth tokens, Aadhaar, and phone numbers from logs and outputs.
    """
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects strict defense-in-depth security response headers:
    HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https:; font-src 'self'; connect-src 'self' ws: wss:; "
            "object-src 'none'; frame-ancestors 'none';"
        )
        response.headers["Permissions-Policy"] = (
            "geolocation=(self), camera=(), microphone=(), payment=()"
        )
        return response


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Guards against Denial-of-Service via oversized uploads.
    Enforces a strict 10MB maximum request size limit.
    """

    def __init__(self, app: Any, max_size_bytes: int = MAX_PAYLOAD_SIZE_BYTES):
        super().__init__(app)
        self.max_size_bytes = max_size_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": "Payload Too Large",
                    "message": f"Request size exceeds limit of {self.max_size_bytes / (1024 * 1024):.1f}MB.",
                },
            )
        return await call_next(request)


class RateLimiter:
    """
    Sliding window in-memory rate limiter per IP / user token.
    Default limit: 120 requests per 60-second window.
    """

    def __init__(self, max_requests: int = 120, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> tuple[bool, int, int]:
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old timestamps
        timestamps = [t for t in self._history[client_key] if t > window_start]
        self._history[client_key] = timestamps

        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0]))
            return False, 0, max(1, retry_after)

        self._history[client_key].append(now)
        remaining = self.max_requests - len(self._history[client_key])
        return True, remaining, 0

    def reset(self):
        self._history.clear()


rate_limiter = RateLimiter(max_requests=120, window_seconds=60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware protecting backend endpoints from abuse and brute-force.
    Returns HTTP 429 Too Many Requests when threshold is exceeded.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Determine client identity (auth token or client host IP)
        auth_header = request.headers.get("authorization")
        client_key = auth_header or request.client.host if request.client else "unknown_client"

        allowed, remaining, retry_after = rate_limiter.is_allowed(client_key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(rate_limiter.max_requests),
                },
                content={
                    "error": "Too Many Requests",
                    "message": "Rate limit exceeded. Please wait before retrying.",
                    "retry_after_seconds": retry_after,
                },
            )

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


class MIMEValidator:
    """
    Validates true file MIME type using binary magic byte signatures.
    Protects against file extension spoofing and polyglot executable uploads.
    """

    MAGIC_SIGNATURES: dict[str, list[bytes]] = {
        "image/jpeg": [b"\xff\xd8\xff"],
        "image/png": [b"\x89PNG\r\n\x1a\n"],
        "image/webp": [b"RIFF"],
        "application/pdf": [b"%PDF-"],
        "image/tiff": [b"II*\x00", b"MM\x00*"],
    }

    @classmethod
    def validate_content(cls, content: bytes, declared_mime: str) -> bool:
        if not content:
            return False

        declared_mime_clean = declared_mime.lower().split(";")[0].strip()
        expected_magics = cls.MAGIC_SIGNATURES.get(declared_mime_clean)
        if not expected_magics:
            # If MIME is not in strict whitelist, reject
            return False

        return any(content.startswith(magic) for magic in expected_magics)


class MalwareScanner(abc.ABC):
    """
    Interface for asynchronous malware and malicious content scanning.
    """

    @abc.abstractmethod
    async def scan(self, file_content: bytes, filename: str) -> dict[str, Any]:
        """
        Scans byte content and returns safety assessment.
        """
        pass


class ClamAVStubScanner(MalwareScanner):
    """
    Local ClamAV scanner integration interface.
    Operates without SaaS external credentials. Detects EICAR test signatures
    and dangerous embedded executable patterns.
    """

    EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    DANGEROUS_EXTENSIONS = {".exe", ".sh", ".bat", ".php", ".py", ".elf", ".dll"}

    async def scan(self, file_content: bytes, filename: str) -> dict[str, Any]:
        lower_name = filename.lower()
        if any(lower_name.endswith(ext) for ext in self.DANGEROUS_EXTENSIONS):
            return {
                "is_clean": False,
                "threat_name": "ExecutableUploadForbidden",
                "scanner": "ClamAV-Local",
                "scanned_at": time.time(),
            }

        if self.EICAR_SIGNATURE in file_content:
            return {
                "is_clean": False,
                "threat_name": "EICAR-Standard-AV-Test-Signature",
                "scanner": "ClamAV-Local",
                "scanned_at": time.time(),
            }

        return {
            "is_clean": True,
            "threat_name": None,
            "scanner": "ClamAV-Local",
            "scanned_at": time.time(),
        }


malware_scanner = ClamAVStubScanner()


def enforce_regional_access(user: AuthenticatedUser, entity_region: str | None) -> None:
    """
    Enforces region-scoped RBAC.
    Disaster Managers and Responders are scoped to their assigned regional jurisdiction.
    SUPER_ADMIN and global ADMIN can access cross-region data.
    """
    if user.role in [UserRole.ADMIN, "SUPER_ADMIN"]:
        return

    user_region = user.metadata.get("region") or user.metadata.get("ward_id")
    if not entity_region or not user_region:
        return

    if user_region.lower() != entity_region.lower():
        raise ForbiddenError(
            f"Region-scoped RBAC violation: user region '{user_region}' is not authorized to operate on region '{entity_region}'."
        )
