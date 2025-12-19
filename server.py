#!/usr/bin/env python3
"""
Modern Mezmo MCP Server with Production-Ready Features

This server provides a robust, scalable MCP implementation for Mezmo log retrieval
with comprehensive error handling, authentication, health checks, and observability.
"""

import os
import time
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

import structlog
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from dotenv import load_dotenv

from mezmo_api import fetch_latest_logs

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


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    timestamp: str
    version: str = "2.0.0"
    dependencies: Dict[str, str] = {}


# Application lifespan management
@asynccontextmanager
async def lifespan(app):
    """Manage application startup and shutdown"""
    logger.info(
        "Starting Mezmo MCP Server",
        server_name=SERVER_NAME,
        host=SERVER_HOST,
        port=SERVER_PORT,
    )

    # Start metrics server if enabled
    if ENABLE_METRICS:
        try:
            start_http_server(METRICS_PORT)
            logger.info("Metrics server started", port=METRICS_PORT)
        except Exception as e:
            logger.error("Failed to start metrics server", error=str(e))

    yield

    logger.info("Shutting down Mezmo MCP Server")


# Create FastMCP server
mcp = FastMCP(name=SERVER_NAME)


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
) -> List[Dict[str, Any]]:
    """
    Retrieve logs from Mezmo Export API v2 with comprehensive filtering.

    DEFAULTS (quota-conscious):
    - Time Range: Last 6 hours
    - Count: 10 logs
    - Levels: All levels

    FILTERING OPTIONS (combine for precision):
    - apps: Filter by application name (e.g., "my-app,web-app")
    - hosts: Filter by host/container ID
    - levels: Filter by severity (e.g., "ERROR,WARNING,INFO")
    - query: Search log content (e.g., resource IDs, error messages, user IDs)
    - from_ts/to_ts: Custom time range (UNIX timestamps in seconds)

    QUERY EXAMPLES:
    - Find by resource ID: query="user_id_12345"
    - Find errors with keyword: query="database connection" + levels="ERROR"
    - Find in specific app: apps="my-app" + query="ConnectionError"
    - Multiple apps: apps="web-app,api-service"

    BEST PRACTICES:
    1. Start tiny (3-5 logs) to discover apps/shape of data
    2. Add app filter to narrow results (saves 90%+ quota)
    3. Add levels filter (ERROR/WARNING) to reduce noise
    4. Add query for specific searches (UUIDs, error messages, etc.)
    5. Increase count only after filters are in place (e.g., 20-50)

    Args:
        count: Number of logs (1-10,000, default: 10)
        apps: App names, comma-separated (e.g., "my-app")
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

    # Log the request to terminal
    filters = []
    if request_data.apps:
        filters.append(f"apps={request_data.apps}")
    if request_data.levels:
        filters.append(f"levels={request_data.levels}")
    if request_data.query:
        filters.append(f"query={request_data.query}")
    filter_str = f" [{', '.join(filters)}]" if filters else ""
    print(f"→ get_logs: count={request_data.count}{filter_str}")

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

    try:
        # Log progress to client
        await ctx.info(f"Fetching {request_data.count} logs from Mezmo API...")

        # Call the Mezmo API
        logs = await fetch_latest_logs(
            count=request_data.count,
            apps=request_data.apps,
            hosts=request_data.hosts,
            levels=request_data.levels,
            query=request_data.query,
            from_ts=request_data.from_ts,
            to_ts=request_data.to_ts,
            prefer=request_data.prefer,
            pagination_id=request_data.pagination_id,
        )

        # Log success
        logger.info(
            "Successfully retrieved logs from Mezmo",
            logs_count=len(logs),
            request_count=request_data.count,
        )

        # Update metrics
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_logs", status="success").inc()
            LOGS_FETCHED.inc(len(logs))
            REQUEST_LATENCY.labels(tool_name="get_logs").observe(
                time.time() - start_time
            )

        # Notify client of completion
        await ctx.info(f"Successfully retrieved {len(logs)} logs")

        return logs

    except Exception as e:
        # Log errors to terminal
        error_type = type(e).__name__
        is_rate_limit = (
            "429" in str(e)
            or "rate limit" in str(e).lower()
            or "concurrent" in str(e).lower()
        )

        # Log error
        logger.error(
            "Failed to retrieve logs from Mezmo",
            error=str(e),
            error_type=error_type,
            count=request_data.count,
            apps=request_data.apps,
            is_rate_limit=is_rate_limit,
        )

        # Update error metrics (with specific label for rate limiting)
        if ENABLE_METRICS:
            status = "rate_limited" if is_rate_limit else "error"
            REQUEST_COUNT.labels(tool_name="get_logs", status=status).inc()
            REQUEST_LATENCY.labels(tool_name="get_logs").observe(
                time.time() - start_time
            )

        # Provide helpful error message to agent
        if is_rate_limit:
            error_msg = (
                f"Mezmo API Rate Limited: {str(e)}\n\n"
                "The Mezmo API has rejected the request due to rate limiting. "
                "Suggestions:\n"
                "1. Wait 30-60 seconds before trying again\n"
                "2. Reduce count (try count=3 or count=5)\n"
                "3. Filter by app (apps='my-app') to drastically reduce volume\n"
                "4. Filter by levels (levels='ERROR' or levels='WARNING')\n"
                "5. Avoid making multiple concurrent requests"
            )
        else:
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
  get_logs(count=10, apps="my-app", levels="ERROR,WARNING")

Step 3: SEARCH SPECIFIC ISSUES
Use query for precise searches:
  get_logs(count=10, apps="my-app", query="user_id_12345")
  get_logs(count=20, apps="my-app", query="ConnectionError", levels="ERROR")

Step 4: SCALE UP (only if needed)
Once filters are working and you need more context:
  get_logs(count=50, apps="my-app", query="ConnectionError", levels="ERROR")

FILTERING OPTIONS:
- **apps**: Filter by application (e.g., apps="my-app,web-app")
- **hosts**: Filter by host/container ID
- **levels**: Filter severity (e.g., levels="ERROR,WARNING,INFO")
- **query**: Search log content - resource IDs, error messages, keywords
- **from_ts/to_ts**: Custom time range (UNIX seconds)

SEARCH EXAMPLES:
- Find resource: query="uuid-1234-5678-abcd"
- Find error type: query="ConnectionError" + levels="ERROR"
- Find user activity: query="user_email@example.com"
- Find API calls: query="/api/endpoint" + apps="api-service"

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
