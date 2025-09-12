import os
import asyncio
import time
import random
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

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
    ):
        self.message = message
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


async def fetch_latest_logs(
    count: int = 50,
    apps: Optional[str] = None,
    hosts: Optional[str] = None,
    levels: Optional[str] = None,
    query: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    prefer: Optional[str] = "tail",
    pagination_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch logs from Mezmo Export API v2 with enhanced error handling and retry logic.

    Args:
        count: Number of logs to return (max 10,000)
        apps: Comma-separated list of applications
        hosts: Comma-separated list of hosts
        levels: Comma-separated list of log levels
        query: Search query
        from_ts: Start time (UNIX timestamp)
        to_ts: End time (UNIX timestamp)
        prefer: 'head' or 'tail' (default: 'tail')
        pagination_id: Token for paginated results

    Returns:
        List of log lines as dictionaries

    Raises:
        MezmoAPIError: When API request fails after retries
        ValueError: When parameters are invalid
    """
    # Validate parameters
    if count < 1 or count > 10000:
        raise ValueError(f"Count must be between 1 and 10000, got {count}")

    if prefer not in ["head", "tail"]:
        raise ValueError(f"Prefer must be 'head' or 'tail', got {prefer}")

    # Build request parameters
    url = f"{MEZMO_API_BASE_URL}/v2/export"

    # Mezmo API requires both from and to timestamps
    # Provide sensible defaults if not specified
    now = int(time.time())
    if from_ts is None:
        # Default to 4 hours ago for "latest" logs - useful for debugging production issues
        from_ts = str(now - 14400)  # 4 hours * 3600 seconds
    if to_ts is None:
        # Default to now
        to_ts = str(now)

    params = {
        "size": count,
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
    if query:
        params["query"] = query
    if pagination_id:
        params["pagination_id"] = pagination_id

    headers = {"servicekey": MEZMO_API_KEY}

    # Log the request
    logger.info(
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

                logger.info(
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

                        logger.info(
                            "Successfully retrieved logs from Mezmo",
                            logs_retrieved=len(logs),
                            total_duration=round(request_duration, 3),
                        )

                        return logs

                    except Exception as e:
                        logger.error(
                            "Failed to parse Mezmo API response",
                            error=str(e),
                            response_text=response.text[:500],
                        )
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

                    logger.warning(
                        "Mezmo API request failed",
                        status_code=response.status_code,
                        response_text=response_text,
                        attempt=attempt + 1,
                    )

                    # Handle rate limiting (429) with longer backoff
                    if response.status_code == 429:
                        last_exception = MezmoAPIError(
                            f"{error_msg}: {response_text}",
                            status_code=response.status_code,
                            response_text=response_text,
                        )
                        # Use longer delay for rate limiting
                        if attempt < MAX_RETRIES - 1:
                            rate_limit_delay = RETRY_DELAY * (
                                3**attempt
                            ) + random.uniform(1, 5)
                            logger.info(
                                "Rate limited, using extended backoff",
                                delay_seconds=rate_limit_delay,
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
            logger.warning(
                "Mezmo API request timeout",
                timeout_seconds=REQUEST_TIMEOUT,
                attempt=attempt + 1,
                error=str(e),
            )
            last_exception = MezmoAPIError(error_msg)

        except httpx.ConnectError as e:
            error_msg = f"Failed to connect to Mezmo API: {e}"
            logger.warning(
                "Mezmo API connection error", attempt=attempt + 1, error=str(e)
            )
            last_exception = MezmoAPIError(error_msg)

        except Exception as e:
            error_msg = f"Unexpected error calling Mezmo API: {e}"
            logger.error(
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
            delay = RETRY_DELAY * (2**attempt) + random.uniform(0.1, 0.5)
            logger.info(
                "Retrying Mezmo API request",
                attempt=attempt + 1,
                max_retries=MAX_RETRIES,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

    # All retries exhausted
    logger.error(
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
        logs = await fetch_latest_logs(count=1)

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


# Cleanup function for graceful shutdown
async def cleanup():
    """Clean up resources"""
    await close_http_client()
    logger.info("Mezmo API client cleanup completed")
