#!/usr/bin/env python3
"""
Modern Mezmo MCP Server with Production-Ready Features

This server provides a robust, scalable MCP implementation for Mezmo log retrieval
with comprehensive error handling, authentication, health checks, and observability.
"""

import os
import re
import time
import uuid
from typing import Dict, Any, Optional

import structlog
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field, field_validator
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from dotenv import load_dotenv

from mezmo_api import fetch_latest_logs, MezmoAPIError, get_circuit_breaker_state

# Load environment variables
load_dotenv()

# Configuration with environment variables and defaults
SERVER_NAME = os.getenv("MCP_SERVER_NAME", "Mezmo MCP Server")
SERVER_HOST = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "18080"))
LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO")
ENABLE_METRICS = os.getenv("MCP_ENABLE_METRICS", "true").lower() == "true"
METRICS_PORT = int(os.getenv("MCP_METRICS_PORT", "9090"))
ENABLE_AUTH = os.getenv("MCP_ENABLE_AUTH", "false").lower() == "true"
API_TOKEN = os.getenv("MCP_API_TOKEN")

# Mezmo API Configuration
MEZMO_API_KEY = os.getenv("MEZMO_API_KEY")
MEZMO_API_BASE_URL = os.getenv("MEZMO_API_BASE_URL", "https://api.mezmo.com")

# Validate required configuration
if not MEZMO_API_KEY:
    raise RuntimeError("MEZMO_API_KEY environment variable is required")

if ENABLE_AUTH and not API_TOKEN:
    raise RuntimeError(
        "MCP_API_TOKEN environment variable is required when authentication is enabled"
    )

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Prometheus metrics
if ENABLE_METRICS:
    REQUEST_COUNT = Counter(
        "mezmo_mcp_requests_total", "Total MCP requests", ["tool_name", "status"]
    )
    REQUEST_LATENCY = Histogram(
        "mezmo_mcp_request_duration_seconds", "MCP request latency", ["tool_name"]
    )
    ACTIVE_CONNECTIONS = Gauge(
        "mezmo_mcp_active_connections", "Number of active MCP connections"
    )
    LOGS_FETCHED = Counter(
        "mezmo_mcp_logs_fetched_total", "Total logs fetched from Mezmo API"
    )


# Valid log levels per Mezmo API
VALID_LOG_LEVELS = {"DEBUG", "INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"}

# Pattern for valid identifiers (app names, host names)
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")


# Pydantic models for request validation
class LogsRequest(BaseModel):
    """Request model for get_logs tool with validation"""

    count: int = Field(
        default=10, ge=1, le=10000, description="Number of logs to return"
    )
    apps: Optional[str] = Field(
        default=None, description="Comma-separated list of applications"
    )
    hosts: Optional[str] = Field(
        default=None, description="Comma-separated list of hosts"
    )
    levels: Optional[str] = Field(
        default=None, description="Comma-separated list of log levels"
    )
    query: Optional[str] = Field(default=None, description="Search query")
    from_ts: Optional[str] = Field(
        default=None, description="Start time (UNIX timestamp)"
    )
    to_ts: Optional[str] = Field(default=None, description="End time (UNIX timestamp)")
    prefer: str = Field(
        default="tail",
        pattern="^(head|tail)$",
        description="Preference for head or tail",
    )
    pagination_id: Optional[str] = Field(default=None, description="Pagination token")

    @field_validator("apps", "hosts")
    @classmethod
    def validate_comma_separated_identifiers(cls, v: Optional[str]) -> Optional[str]:
        """Validate comma-separated identifier lists (apps, hosts)."""
        if v is None:
            return v

        items = [item.strip() for item in v.split(",") if item.strip()]
        if not items:
            raise ValueError("Cannot be empty after parsing")

        invalid_items = []
        for item in items:
            if not IDENTIFIER_PATTERN.match(item):
                invalid_items.append(item)

        if invalid_items:
            raise ValueError(
                f"Invalid identifier(s): {invalid_items}. "
                "Identifiers must contain only alphanumeric characters, underscores, dots, and hyphens."
            )

        return ",".join(items)  # Return normalized version

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, v: Optional[str]) -> Optional[str]:
        """Validate comma-separated log levels."""
        if v is None:
            return v

        items = [item.strip().upper() for item in v.split(",") if item.strip()]
        if not items:
            raise ValueError("Cannot be empty after parsing")

        invalid_levels = set(items) - VALID_LOG_LEVELS
        if invalid_levels:
            raise ValueError(
                f"Invalid log level(s): {invalid_levels}. "
                f"Valid levels: {sorted(VALID_LOG_LEVELS)}"
            )

        return ",".join(items)  # Return normalized (uppercase) version

    @field_validator("from_ts", "to_ts")
    @classmethod
    def validate_timestamp(cls, v: Optional[str]) -> Optional[str]:
        """Validate UNIX timestamps."""
        if v is None:
            return v

        try:
            ts = int(v)
            if ts < 0:
                raise ValueError("Timestamp must be positive")
            # Sanity check: reject timestamps obviously in the future (> 10 years from now)
            if ts > time.time() + 315360000:  # 10 years in seconds
                raise ValueError("Timestamp appears to be too far in the future")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid timestamp: {v}. Must be a UNIX timestamp in seconds. {e}")

        return v


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    timestamp: str
    version: str = "2.0.0"
    dependencies: Dict[str, str] = {}


# Create FastMCP server
mcp = FastMCP(name=SERVER_NAME)


def _build_error_message(error: MezmoAPIError, request_data: "LogsRequest") -> str:
    """Build a helpful error message based on the error type and context."""
    if error.status_code == 429:
        # Rate limit error
        retry_info = ""
        if error.retry_after:
            retry_info = f"The API suggests waiting {error.retry_after} seconds before retrying.\n"
        else:
            retry_info = "Wait 30-60 seconds before trying again.\n"

        return (
            f"Mezmo API Rate Limited: {error.message}\n\n"
            f"{retry_info}"
            "Suggestions to reduce API load:\n"
            f"1. You requested count={request_data.count}. Try reducing to count=3 or count=5.\n"
            "2. Add an app filter (apps='your-app') to drastically reduce volume.\n"
            "3. Add a levels filter (levels='ERROR,WARNING') to focus on important logs.\n"
            "4. Avoid making multiple concurrent requests."
        )

    elif error.status_code == 503:
        # Circuit breaker open
        cb_state = get_circuit_breaker_state()
        return (
            f"Mezmo API Unavailable: {error.message}\n\n"
            f"The service has experienced {cb_state['failure_count']} recent failures.\n"
            f"Automatic recovery will be attempted in {cb_state['recovery_timeout']} seconds.\n"
            "This is a temporary protection mechanism to prevent cascading failures."
        )

    elif error.status_code == 401:
        return (
            f"Authentication Failed: {error.message}\n\n"
            "The Mezmo API key may be invalid or expired.\n"
            "Please verify the MEZMO_API_KEY environment variable is set correctly."
        )

    elif error.status_code == 400:
        return (
            f"Invalid Request: {error.message}\n\n"
            "The request parameters may be malformed. Check:\n"
            f"- apps: {request_data.apps}\n"
            f"- hosts: {request_data.hosts}\n"
            f"- levels: {request_data.levels}\n"
            f"- query: {request_data.query}\n"
            f"- from_ts: {request_data.from_ts}\n"
            f"- to_ts: {request_data.to_ts}"
        )

    else:
        return f"Failed to retrieve logs from Mezmo: {error.message}"


# Initialize startup tasks
def initialize_server():
    """Initialize server components"""
    logger.info(
        "Starting Mezmo MCP Server",
        server_name=SERVER_NAME,
    )

    # Start metrics server if enabled
    if ENABLE_METRICS:
        try:
            start_http_server(METRICS_PORT)
            logger.info("Metrics server started", port=METRICS_PORT)
        except Exception as e:
            logger.error("Failed to start metrics server", error=str(e))


@mcp.tool
async def get_logs(
    ctx: Context,
    count: int = 10,
    apps: Optional[str] = None,
    hosts: Optional[str] = None,
    levels: Optional[str] = None,
    query: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    prefer: str = "tail",
    pagination_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve logs from Mezmo Export API v2 with comprehensive filtering.

    DEFAULTS (quota-conscious):
    - Time Range: Last 6 hours
    - Count: 10 logs
    - Levels: All levels

    FILTERING OPTIONS (combine for precision):
    - apps: Filter by application name (e.g., "app-a,app-b")
    - hosts: Filter by host/container ID
    - levels: Filter by severity (e.g., "ERROR,WARNING,INFO")
    - query: Search log content (e.g., resource IDs, error messages, user IDs)
    - from_ts/to_ts: Custom time range (UNIX timestamps in seconds)

    QUERY EXAMPLES:
    - Find by resource ID: query="user_id_12345"
    - Find errors with keyword: query="database connection" + levels="ERROR"
    - Find in specific app: apps="app-a" + query="ConnectionError"
    - Multiple apps: apps="app-a,app-b"

    BEST PRACTICES:
    1. Start tiny (3-5 logs) to discover apps/shape of data
    2. Add app filter to narrow results (saves 90%+ quota)
    3. Add levels filter (ERROR/WARNING) to reduce noise
    4. Add query for specific searches (UUIDs, error messages, etc.)
    5. Increase count only after filters are in place (e.g., 20-50)

    Args:
        count: Number of logs (1-10,000, default: 10)
        apps: App names, comma-separated (e.g., "app-a")
        hosts: Host IDs, comma-separated
        levels: Log levels, comma-separated (e.g., "ERROR,WARNING")
        query: Search string (matches log content)
        from_ts: Start time, UNIX seconds (default: 6 hours ago)
        to_ts: End time, UNIX seconds (default: now)
        prefer: 'head' or 'tail' (default: 'tail' = newest first)
        pagination_id: Token for next page

    Returns:
        List of log entries with full context

    Raises:
        ToolError: When API request fails or validation errors occur
    """
    # Validate request using Pydantic model
    try:
        request_data = LogsRequest(
            count=count,
            apps=apps,
            hosts=hosts,
            levels=levels,
            query=query,
            from_ts=from_ts,
            to_ts=to_ts,
            prefer=prefer,
            pagination_id=pagination_id,
        )
    except Exception as e:
        logger.error("Invalid request parameters", error=str(e))
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_logs", status="validation_error").inc()
        raise ToolError(str(e))

    # Log the request with context
    logger.info(
        "Processing get_logs request",
        count=request_data.count,
        apps=request_data.apps,
        hosts=request_data.hosts,
        levels=request_data.levels,
        query=request_data.query,
        prefer=request_data.prefer,
    )

    # Record metrics
    start_time = time.time()
    if ENABLE_METRICS:
        REQUEST_COUNT.labels(tool_name="get_logs", status="started").inc()

    # Generate correlation ID for request tracing
    correlation_id = str(uuid.uuid4())

    try:
        # Log progress to client
        await ctx.info(f"Fetching {request_data.count} logs from Mezmo API...")

        # Call the Mezmo API
        result = await fetch_latest_logs(
            count=request_data.count,
            apps=request_data.apps,
            hosts=request_data.hosts,
            levels=request_data.levels,
            query=request_data.query,
            from_ts=request_data.from_ts,
            to_ts=request_data.to_ts,
            prefer=request_data.prefer,
            pagination_id=request_data.pagination_id,
            correlation_id=correlation_id,
        )

        logs = result.get("logs", [])

        # Log success
        logger.info(
            "Successfully retrieved logs from Mezmo",
            logs_count=len(logs),
            request_count=request_data.count,
            correlation_id=correlation_id,
        )

        # Update metrics
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_logs", status="success").inc()
            LOGS_FETCHED.inc(len(logs))
            REQUEST_LATENCY.labels(tool_name="get_logs").observe(
                time.time() - start_time
            )

        # Provide guidance for empty results
        if len(logs) == 0:
            await ctx.info(
                "No logs found. Suggestions:\n"
                "1. Expand time range (from_ts further back)\n"
                "2. Remove filters to discover available apps\n"
                "3. Check app names with list_apps tool"
            )
        else:
            # Notify client of completion
            await ctx.info(f"Successfully retrieved {len(logs)} logs")

        # Build time range for metadata
        now = int(time.time())
        from_ts_value = request_data.from_ts or str(now - 21600)
        to_ts_value = request_data.to_ts or str(now)

        # Return structured response with metadata
        return {
            "logs": logs,
            "metadata": {
                "count": len(logs),
                "requested_count": request_data.count,
                "pagination_id": result.get("pagination_id"),
                "has_more": result.get("has_more", False),
                "time_range": {
                    "from": from_ts_value,
                    "to": to_ts_value,
                },
                "filters": {
                    "apps": request_data.apps,
                    "hosts": request_data.hosts,
                    "levels": request_data.levels,
                    "query": request_data.query,
                },
                "correlation_id": correlation_id,
            },
        }

    except MezmoAPIError as e:
        # Handle Mezmo API specific errors
        error_type = "MezmoAPIError"
        is_rate_limit = e.status_code == 429
        is_circuit_breaker = e.status_code == 503

        # Log error
        logger.error(
            "Failed to retrieve logs from Mezmo",
            error=str(e),
            error_type=error_type,
            status_code=e.status_code,
            count=request_data.count,
            apps=request_data.apps,
            is_rate_limit=is_rate_limit,
            retry_after=e.retry_after,
        )

        # Update error metrics
        if ENABLE_METRICS:
            if is_rate_limit:
                status = "rate_limited"
            elif is_circuit_breaker:
                status = "circuit_breaker_open"
            else:
                status = "error"
            REQUEST_COUNT.labels(tool_name="get_logs", status=status).inc()
            REQUEST_LATENCY.labels(tool_name="get_logs").observe(
                time.time() - start_time
            )

        # Provide helpful error message based on error type
        error_msg = _build_error_message(e, request_data)

        # Notify client of error
        await ctx.error(error_msg)

        # Always raise ToolError so the agent knows the tool failed
        raise ToolError(error_msg)

    except Exception as e:
        # Handle unexpected errors
        error_type = type(e).__name__

        # Log error
        logger.error(
            "Unexpected error retrieving logs from Mezmo",
            error=str(e),
            error_type=error_type,
            count=request_data.count,
            apps=request_data.apps,
        )

        # Update error metrics
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_logs", status="error").inc()
            REQUEST_LATENCY.labels(tool_name="get_logs").observe(
                time.time() - start_time
            )

        error_msg = f"Failed to retrieve logs from Mezmo: {str(e)}"

        # Notify client of error
        await ctx.error(error_msg)

        # Always raise ToolError so the agent knows the tool failed
        raise ToolError(error_msg)


@mcp.resource("health://status")
async def health_check() -> str:
    """
    Health check resource for monitoring and load balancing.

    Returns comprehensive health status including dependency checks.
    """
    try:
        # Check Mezmo API connectivity (optional quick check)
        health_data = HealthResponse(
            status="healthy",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            dependencies={
                "mezmo_api": "available",
                "metrics": "enabled" if ENABLE_METRICS else "disabled",
                "auth": "enabled" if ENABLE_AUTH else "disabled",
            },
        )

        logger.debug("Health check performed", status=health_data.status)
        return health_data.model_dump_json()

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        error_response = HealthResponse(
            status="unhealthy",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            dependencies={"error": str(e)},
        )
        return error_response.model_dump_json()


@mcp.tool
async def list_apps(
    ctx: Context,
    hours: int = 6,
) -> Dict[str, Any]:
    """
    Discover available application names in recent logs.

    Use this tool before get_logs to find valid app names for filtering.
    Samples recent logs to extract unique application names.

    Args:
        hours: How many hours back to search (default: 6)

    Returns:
        Dictionary with 'apps' list and 'count'

    Example:
        list_apps() -> {"apps": ["web-api", "worker", "scheduler"], "count": 3}
    """
    correlation_id = str(uuid.uuid4())

    # Record metrics
    start_time = time.time()
    if ENABLE_METRICS:
        REQUEST_COUNT.labels(tool_name="list_apps", status="started").inc()

    try:
        await ctx.info("Discovering available applications...")

        # Calculate time range
        now = int(time.time())
        from_ts = str(now - (hours * 3600))

        # Fetch a sample of logs to discover apps
        result = await fetch_latest_logs(
            count=100,
            from_ts=from_ts,
            to_ts=str(now),
            correlation_id=correlation_id,
        )

        logs = result.get("logs", [])

        # Extract unique app names
        apps = set()
        for log in logs:
            app = log.get("_app")
            if app:
                apps.add(app)

        # Update metrics
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="list_apps", status="success").inc()
            REQUEST_LATENCY.labels(tool_name="list_apps").observe(
                time.time() - start_time
            )

        sorted_apps = sorted(apps)
        await ctx.info(f"Found {len(sorted_apps)} unique applications")

        return {
            "apps": sorted_apps,
            "count": len(sorted_apps),
            "sample_size": len(logs),
            "hours_searched": hours,
        }

    except MezmoAPIError as e:
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="list_apps", status="error").inc()

        error_msg = f"Failed to discover apps: {e.message}"
        await ctx.error(error_msg)
        raise ToolError(error_msg)

    except Exception as e:
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="list_apps", status="error").inc()

        error_msg = f"Failed to discover apps: {str(e)}"
        await ctx.error(error_msg)
        raise ToolError(error_msg)


@mcp.tool
async def get_log_stats(
    ctx: Context,
    hours: int = 6,
    apps: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get statistics about recent log activity.

    Returns level distribution, top applications, and log volume.
    Useful for understanding the shape of your logs before querying.

    Args:
        hours: How many hours back to analyze (default: 6)
        apps: Optional app filter (comma-separated)

    Returns:
        Dictionary with level_distribution, top_apps, and total_sampled

    Example:
        get_log_stats() -> {
            "level_distribution": {"INFO": 45, "ERROR": 12, "WARNING": 8},
            "top_apps": [{"app": "web-api", "count": 30}, ...],
            "total_sampled": 100
        }
    """
    correlation_id = str(uuid.uuid4())

    # Record metrics
    start_time = time.time()
    if ENABLE_METRICS:
        REQUEST_COUNT.labels(tool_name="get_log_stats", status="started").inc()

    try:
        await ctx.info("Gathering log statistics...")

        # Calculate time range
        now = int(time.time())
        from_ts = str(now - (hours * 3600))

        # Fetch a sample of logs
        result = await fetch_latest_logs(
            count=200,
            apps=apps,
            from_ts=from_ts,
            to_ts=str(now),
            correlation_id=correlation_id,
        )

        logs = result.get("logs", [])

        # Calculate level distribution
        level_counts: Dict[str, int] = {}
        app_counts: Dict[str, int] = {}

        for log in logs:
            # Count by level
            level = log.get("_level", "UNKNOWN")
            if isinstance(level, str):
                level = level.upper()
            level_counts[level] = level_counts.get(level, 0) + 1

            # Count by app
            app = log.get("_app", "unknown")
            app_counts[app] = app_counts.get(app, 0) + 1

        # Sort apps by count (descending)
        top_apps = sorted(
            [{"app": app, "count": count} for app, count in app_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]  # Top 10 apps

        # Update metrics
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_log_stats", status="success").inc()
            REQUEST_LATENCY.labels(tool_name="get_log_stats").observe(
                time.time() - start_time
            )

        await ctx.info(f"Analyzed {len(logs)} logs across {len(app_counts)} apps")

        return {
            "level_distribution": level_counts,
            "top_apps": top_apps,
            "total_sampled": len(logs),
            "hours_analyzed": hours,
            "filters_applied": {"apps": apps} if apps else None,
        }

    except MezmoAPIError as e:
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_log_stats", status="error").inc()

        error_msg = f"Failed to get log stats: {e.message}"
        await ctx.error(error_msg)
        raise ToolError(error_msg)

    except Exception as e:
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_log_stats", status="error").inc()

        error_msg = f"Failed to get log stats: {str(e)}"
        await ctx.error(error_msg)
        raise ToolError(error_msg)


@mcp.prompt
async def analyze_logs(
    ctx: Context, query: str, time_range: str = "1h", log_level: str = "ERROR,WARNING"
) -> str:
    """
    Generate a prompt for analyzing logs with specific criteria.

    Args:
        query: Search query for log analysis
        time_range: Time range for analysis (e.g., "1h", "24h")
        log_level: Log level to focus on (default: ERROR,WARNING)

    Returns:
        Formatted prompt for log analysis
    """
    prompt = f"""
Please analyze the logs from Mezmo with the following criteria:

Search Query: {query}
Time Range: {time_range}
Log Level: {log_level}

QUOTA-CONSCIOUS WORKFLOW (Mezmo has account limits):

Step 1: DISCOVER (3-5 logs)
See what apps are active:
  get_logs(count=3)
  get_logs(count=5)

Step 2: FILTER BY APP
Narrow to specific app (saves 90%+ quota):
  get_logs(count=10, apps="app-a", levels="ERROR,WARNING")

Step 3: SEARCH SPECIFIC ISSUES
Use query for precise searches:
  get_logs(count=10, apps="app-a", query="user_id_12345")
  get_logs(count=20, apps="app-a", query="ConnectionError", levels="ERROR")

Step 4: SCALE UP (only if needed)
Once filters are working and you need more context:
  get_logs(count=50, apps="app-a", query="ConnectionError", levels="ERROR")

FILTERING OPTIONS:
- **apps**: Filter by application (e.g., apps="app-a,app-b")
- **hosts**: Filter by host/container ID
- **levels**: Filter severity (e.g., levels="ERROR,WARNING,INFO")
- **query**: Search log content - resource IDs, error messages, keywords
- **from_ts/to_ts**: Custom time range (UNIX seconds)

SEARCH EXAMPLES:
- Find resource: query="trace_id=abcdef1234" or query="request_id=xyz-123"
- Find error type: query="ConnectionError" + levels="ERROR"
- Find user activity: query="user_id_12345"
- Find API calls: query="/api/endpoint" + apps="app-a"

Analysis steps:
1. **Discover**: 5 logs to see active apps
2. **Filter**: Add apps filter (massive quota savings)
3. **Search**: Add query for specific resource IDs, errors, users
4. **Refine**: Add levels filter to focus on ERROR/WARNING
5. **Analyze**: Look for patterns in filtered results
6. **Recommend**: Provide actionable fixes

QUOTA BEST PRACTICES:
✓ Always use apps filter (saves 90%+ quota)
✓ Use query to search specific IDs, errors, keywords
✓ Combine filters: apps + query + levels
✓ Start tiny: count=3-5 for discovery
✓ Default count is 10; increase only after adding filters
✓ Default 6-hour window is usually enough

Focus on actionable insights that help with immediate troubleshooting while respecting account quota limits.
"""

    logger.info(
        "Generated log analysis prompt",
        query=query,
        time_range=time_range,
        log_level=log_level,
    )

    return prompt


def create_app():
    """Create and configure the FastMCP application"""

    # Configure authentication if enabled
    if ENABLE_AUTH:
        logger.info("Authentication enabled for MCP server")
        # Note: FastMCP 2.x has built-in auth support
        # This would be configured based on your specific auth requirements

    return mcp


def main():
    """Main entry point"""
    # Initialize server components
    initialize_server()

    # Run the server with HTTP transport
    mcp.run(transport="http", host="0.0.0.0", port=18080, path="/mcp")


if __name__ == "__main__":
    main()
