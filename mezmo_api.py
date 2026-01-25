import os
import asyncio
import time
import random
import uuid
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from enum import Enum

import httpx
import structlog
from dotenv import load_dotenv

load_dotenv()

# Configure structured logging
logger = structlog.get_logger(__name__)

# Configuration
MEZMO_API_KEY = os.getenv("MEZMO_API_KEY")
MEZMO_API_BASE_URL = os.getenv("MEZMO_API_BASE_URL", "https://api.mezmo.com")
REQUEST_TIMEOUT = int(os.getenv("MEZMO_REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MEZMO_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("MEZMO_RETRY_DELAY", "1.0"))
MAX_RETRY_DELAY = 30.0  # Cap retry delay at 30 seconds

# Circuit breaker configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = float(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "60.0"))

if not MEZMO_API_KEY:
    raise RuntimeError("MEZMO_API_KEY is not set in environment variables.")

# Connection pool for efficient HTTP connections
_http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def get_http_client():
    """Get or create a shared HTTP client with connection pooling"""
    global _http_client

    if _http_client is None:
        # Configure client with connection pooling and timeouts
        limits = httpx.Limits(
            max_keepalive_connections=10, max_connections=20, keepalive_expiry=30.0
        )

        timeout = httpx.Timeout(connect=5.0, read=REQUEST_TIMEOUT, write=5.0, pool=2.0)

        _http_client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            headers={
                "User-Agent": "Mezmo-MCP-Server/2.0.0",
                "Accept": "application/json",
            },
        )

        logger.info("Created new HTTP client with connection pooling")

    try:
        yield _http_client
    except Exception as e:
        logger.error("HTTP client error", error=str(e))
        # Close and recreate client on error
        if _http_client:
            await _http_client.aclose()
            _http_client = None
        raise


async def close_http_client():
    """Close the shared HTTP client"""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
        logger.info("Closed HTTP client")


class MezmoAPIError(Exception):
    """Custom exception for Mezmo API errors"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        retry_after: Optional[int] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.response_text = response_text
        self.retry_after = retry_after
        super().__init__(message)


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failures exceeded threshold, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for Mezmo API.

    Prevents cascading failures by stopping requests when the API is failing.
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are rejected immediately
    - HALF_OPEN: Testing recovery, allows one request through
    """

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    async def can_proceed(self) -> bool:
        """Check if a request can proceed based on circuit state."""
        async with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True

            if self.state == CircuitBreakerState.OPEN:
                # Check if recovery timeout has elapsed
                if self.last_failure_time and (time.time() - self.last_failure_time) >= self.recovery_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    logger.info(
                        "Circuit breaker transitioning to HALF_OPEN",
                        recovery_timeout=self.recovery_timeout,
                    )
                    return True
                return False

            # HALF_OPEN: allow one request through to test recovery
            return True

    async def record_success(self) -> None:
        """Record a successful request."""
        async with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                logger.info("Circuit breaker closing after successful recovery test")
            self.failure_count = 0
            self.state = CircuitBreakerState.CLOSED

    async def record_failure(self) -> None:
        """Record a failed request."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitBreakerState.HALF_OPEN:
                # Recovery test failed, go back to OPEN
                self.state = CircuitBreakerState.OPEN
                logger.warning(
                    "Circuit breaker reopening after failed recovery test",
                    failure_count=self.failure_count,
                )
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(
                    "Circuit breaker opening due to failures",
                    failure_count=self.failure_count,
                    threshold=self.failure_threshold,
                )

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state for monitoring."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_timeout": self.recovery_timeout,
        }


# Global circuit breaker instance
_circuit_breaker = CircuitBreaker()


async def fetch_latest_logs(
    count: int = 10,
    apps: Optional[str] = None,
    hosts: Optional[str] = None,
    levels: Optional[str] = None,
    query: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    prefer: Optional[str] = "tail",
    pagination_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch logs from Mezmo Export API v2 with enhanced error handling and retry logic.

    Args:
        count: Number of logs to return (max 10,000, default: 10)
        apps: Comma-separated list of applications
        hosts: Comma-separated list of hosts
        levels: Comma-separated list of log levels
        query: Search query
        from_ts: Start time (UNIX timestamp)
        to_ts: End time (UNIX timestamp)
        prefer: 'head' or 'tail' (default: 'tail')
        pagination_id: Token for paginated results
        correlation_id: Request correlation ID for tracing

    Returns:
        Dictionary with 'logs', 'pagination_id', and 'has_more' keys

    Raises:
        MezmoAPIError: When API request fails after retries
        ValueError: When parameters are invalid
    """
    # Generate correlation ID if not provided
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    log = logger.bind(correlation_id=correlation_id)

    # Check circuit breaker before proceeding
    if not await _circuit_breaker.can_proceed():
        cb_state = _circuit_breaker.get_state()
        log.warning(
            "Circuit breaker is OPEN, rejecting request",
            circuit_breaker_state=cb_state,
        )
        raise MezmoAPIError(
            "Circuit breaker OPEN - Mezmo API unavailable. "
            f"Service will retry automatically after {CIRCUIT_BREAKER_RECOVERY_TIMEOUT}s. "
            "Too many recent failures indicate the API is experiencing issues.",
            status_code=503,
        )
    # Validate parameters per Mezmo Export API v2 spec
    if count < 1 or count > 10000:
        raise ValueError(f"Count must be between 1 and 10,000 per API spec, got {count}")

    if prefer not in ["head", "tail"]:
        raise ValueError(f"Prefer must be 'head' or 'tail', got {prefer}")

    # Build request parameters
    url = f"{MEZMO_API_BASE_URL}/v2/export"

    # Mezmo API requires both from and to timestamps IN SECONDS
    # Provide sensible defaults if not specified
    now = int(time.time())
    if from_ts is None:
        # Default to 6 hours ago - balance between quota and finding actual logs
        from_ts = str(now - 21600)  # 6 hours in seconds
    if to_ts is None:
        # Default to now
        to_ts = str(now)  # UNIX timestamp in seconds

    # Map to Mezmo API v2 parameters
    params = {
        "size": count,  # API uses 'size', we expose as 'count'
        "prefer": prefer,
        "from": from_ts,
        "to": to_ts,
    }

    # Add optional parameters
    if apps:
        params["apps"] = apps
    if hosts:
        params["hosts"] = hosts
    if levels:
        params["levels"] = levels
    # NOTE: Do not set default levels - let Mezmo return all levels if not specified
    if query:
        params["query"] = query
    if pagination_id:
        params["pagination_id"] = pagination_id

    headers = {"servicekey": MEZMO_API_KEY}

    # Log the request
    log.info(
        "Making request to Mezmo API",
        url=url,
        params={k: v for k, v in params.items() if k != "servicekey"},
        count=count,
        prefer=prefer,
    )

    # Retry logic with exponential backoff
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            async with get_http_client() as client:
                start_time = time.time()

                response = await client.get(url, headers=headers, params=params)

                request_duration = time.time() - start_time

                log.info(
                    "Mezmo API request completed",
                    status_code=response.status_code,
                    duration_seconds=round(request_duration, 3),
                    attempt=attempt + 1,
                )

                # Handle successful response
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logs = data.get("lines", [])

                        log.info(
                            "Successfully retrieved logs from Mezmo",
                            logs_retrieved=len(logs),
                            total_duration=round(request_duration, 3),
                        )

                        # Record success for circuit breaker
                        await _circuit_breaker.record_success()

                        # Return structured response with metadata
                        return {
                            "logs": logs,
                            "pagination_id": data.get("pagination_id"),
                            "has_more": len(logs) == count,
                        }

                    except Exception as e:
                        log.error(
                            "Failed to parse Mezmo API response",
                            error=str(e),
                            response_text=response.text[:500],
                        )
                        await _circuit_breaker.record_failure()
                        raise MezmoAPIError(
                            f"Failed to parse Mezmo API response: {e}",
                            status_code=response.status_code,
                            response_text=response.text[:500],
                        )

                # Handle HTTP errors
                else:
                    error_msg = f"Mezmo API returned status {response.status_code}"
                    response_text = (
                        response.text[:500] if response.text else "No response body"
                    )

                    log.warning(
                        "Mezmo API request failed",
                        status_code=response.status_code,
                        response_text=response_text,
                        attempt=attempt + 1,
                    )

                    # Handle rate limiting (429) with Retry-After header
                    if response.status_code == 429:
                        # Extract Retry-After header if present
                        retry_after_header = response.headers.get("Retry-After")
                        retry_after_seconds = None
                        if retry_after_header:
                            try:
                                retry_after_seconds = int(retry_after_header)
                            except ValueError:
                                retry_after_seconds = None

                        last_exception = MezmoAPIError(
                            f"{error_msg}: {response_text}",
                            status_code=response.status_code,
                            response_text=response_text,
                            retry_after=retry_after_seconds,
                        )

                        # Use Retry-After if provided, otherwise use exponential backoff
                        if attempt < MAX_RETRIES - 1:
                            if retry_after_seconds is not None:
                                rate_limit_delay = retry_after_seconds + random.uniform(0.5, 2.0)
                            else:
                                # Capped exponential backoff: 2^attempt instead of 3^attempt
                                rate_limit_delay = min(
                                    RETRY_DELAY * (2 ** attempt) + random.uniform(1, 3),
                                    MAX_RETRY_DELAY
                                )

                            log.info(
                                "Rate limited, waiting before retry",
                                delay_seconds=round(rate_limit_delay, 1),
                                retry_after_header=retry_after_header,
                                attempt=attempt + 1,
                            )
                            await asyncio.sleep(rate_limit_delay)
                            continue

                    # Don't retry on other client errors (4xx except 429)
                    elif 400 <= response.status_code < 500:
                        raise MezmoAPIError(
                            f"{error_msg}: {response_text}",
                            status_code=response.status_code,
                            response_text=response_text,
                        )

                    # Retry on server errors (5xx) and other issues
                    else:
                        last_exception = MezmoAPIError(
                            f"{error_msg}: {response_text}",
                            status_code=response.status_code,
                            response_text=response_text,
                        )

        except httpx.TimeoutException as e:
            error_msg = f"Request to Mezmo API timed out after {REQUEST_TIMEOUT}s"
            log.warning(
                "Mezmo API request timeout",
                timeout_seconds=REQUEST_TIMEOUT,
                attempt=attempt + 1,
                error=str(e),
            )
            last_exception = MezmoAPIError(error_msg)

        except httpx.ConnectError as e:
            error_msg = f"Failed to connect to Mezmo API: {e}"
            log.warning(
                "Mezmo API connection error",
                attempt=attempt + 1,
                error=str(e),
            )
            last_exception = MezmoAPIError(error_msg)

        except MezmoAPIError:
            # Re-raise MezmoAPIError without wrapping
            raise

        except Exception as e:
            error_msg = f"Unexpected error calling Mezmo API: {e}"
            log.error(
                "Unexpected error in Mezmo API call",
                attempt=attempt + 1,
                error=str(e),
                error_type=type(e).__name__,
            )
            last_exception = MezmoAPIError(error_msg)

        # Wait before retrying (with exponential backoff) - skip if 429 already handled
        if attempt < MAX_RETRIES - 1 and (
            not last_exception or last_exception.status_code != 429
        ):
            delay = min(RETRY_DELAY * (2 ** attempt) + random.uniform(0.1, 0.5), MAX_RETRY_DELAY)
            log.info(
                "Retrying Mezmo API request",
                attempt=attempt + 1,
                max_retries=MAX_RETRIES,
                delay_seconds=round(delay, 1),
            )
            await asyncio.sleep(delay)

    # All retries exhausted - record failure for circuit breaker
    await _circuit_breaker.record_failure()

    log.error(
        "All Mezmo API retry attempts failed",
        max_retries=MAX_RETRIES,
        last_error=str(last_exception),
    )

    if last_exception:
        raise last_exception
    else:
        raise MezmoAPIError("Failed to fetch logs from Mezmo after all retry attempts")


async def test_mezmo_connection() -> Dict[str, Any]:
    """
    Test connectivity to the Mezmo API.

    Returns:
        Dictionary with connection test results
    """
    try:
        logger.info("Testing Mezmo API connectivity")

        # Try to fetch a small number of logs to test the connection
        # The function now provides default timestamps automatically
        result_data = await fetch_latest_logs(count=1)
        logs = result_data.get("logs", [])

        result = {
            "status": "success",
            "message": "Successfully connected to Mezmo API",
            "logs_available": len(logs) > 0,
        }

        logger.info("Mezmo API connectivity test successful", result=result)
        return result

    except Exception as e:
        result = {
            "status": "error",
            "message": f"Failed to connect to Mezmo API: {e}",
            "error_type": type(e).__name__,
        }

        logger.error("Mezmo API connectivity test failed", result=result)
        return result


def get_circuit_breaker_state() -> Dict[str, Any]:
    """Get current circuit breaker state for monitoring."""
    return _circuit_breaker.get_state()


# Cleanup function for graceful shutdown
async def cleanup():
    """Clean up resources"""
    await close_http_client()
    logger.info("Mezmo API client cleanup completed")
