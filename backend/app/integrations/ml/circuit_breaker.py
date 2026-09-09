import logging
import time
from enum import StrEnum

logger = logging.getLogger("ml.circuit_breaker")


class CircuitState(StrEnum):
    CLOSED = "CLOSED"  # Normal: requests go through
    OPEN = "OPEN"  # Tripped: requests fail fast to fallback
    HALF_OPEN = "HALF_OPEN"  # Trial: testing single probe request


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_timeout:
                logger.info("Circuit breaker transitioning to HALF_OPEN to probe ML service.")
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit breaker tripped to OPEN after {self.failure_count} consecutive failures."
            )
            self.state = CircuitState.OPEN
