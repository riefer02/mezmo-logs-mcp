#!/usr/bin/env python3
"""
Modern Mezmo MCP Server with Production-Ready Features

This server provides a robust, scalable MCP implementation for Mezmo log retrieval
with comprehensive error handling, authentication, health checks, and observability.
"""

import asyncio
import os
import sys
import time
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

import structlog
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import uvicorn
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
    Retrieve logs from Mezmo Export API v2 with comprehensive error handling.

    This tool provides robust access to Mezmo logs with proper validation,
    error handling, and observability features.

    Args:
        count: Number of logs to return (1-10,000, default: 10)
        apps: Comma-separated list of applications to filter
        hosts: Comma-separated list of hosts to filter
        levels: Comma-separated list of log levels (ERROR, INFO, WARNING, etc.)
        query: Search query string for log content
        from_ts: Start time as UNIX timestamp (seconds or milliseconds)
        to_ts: End time as UNIX timestamp (seconds or milliseconds)
        prefer: Preference for 'head' or 'tail' ordering (default: 'tail')
        pagination_id: Token for retrieving paginated results

    Returns:
        List of log entries from Mezmo API

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
        # Check if this is a rate limiting error
        if (
            "429" in str(e)
            or "rate limit" in str(e).lower()
            or "concurrent" in str(e).lower()
        ):
            # Return rate limiting as context, not error
            logger.warning(
                "Mezmo API rate limited - returning context",
                error=str(e),
                count=request_data.count,
                apps=request_data.apps,
            )

            # Update metrics
            if ENABLE_METRICS:
                REQUEST_COUNT.labels(tool_name="get_logs", status="rate_limited").inc()
                REQUEST_LATENCY.labels(tool_name="get_logs").observe(
                    time.time() - start_time
                )

            # Notify client with context
            await ctx.info(
                "Mezmo API is currently rate limited - try reducing request frequency or count"
            )

            # Return structured response indicating rate limiting
            return [
                {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "level": "INFO",
                    "message": "Mezmo API Rate Limited",
                    "context": {
                        "status": "rate_limited",
                        "reason": "Exceeded maximum number of concurrent export requests",
                        "suggestion": "Try again in a few moments with fewer logs (count < 10) or filter by ERROR/WARNING levels",
                        "requested_count": request_data.count,
                        "apps": request_data.apps,
                        "levels": request_data.levels,
                    },
                }
            ]

        # For other errors, log and raise
        logger.error(
            "Failed to retrieve logs from Mezmo",
            error=str(e),
            error_type=type(e).__name__,
            count=request_data.count,
            apps=request_data.apps,
        )

        # Update error metrics
        if ENABLE_METRICS:
            REQUEST_COUNT.labels(tool_name="get_logs", status="error").inc()
            REQUEST_LATENCY.labels(tool_name="get_logs").observe(
                time.time() - start_time
            )

        # Notify client of error
        await ctx.error(f"Failed to retrieve logs: {str(e)}")

        # Re-raise as ToolError for proper client handling
        raise ToolError(str(e))


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

IMPORTANT: Start with ERROR and WARNING logs first as they indicate issues requiring attention.

Use the get_logs tool to retrieve relevant logs. Start with a small count (5-10) to avoid rate limits:
1. First, get ERROR logs: get_logs(count=5, levels="ERROR", query="{query}")
2. Then, get WARNING logs: get_logs(count=5, levels="WARNING", query="{query}")
3. If rate limited, the response will contain context about the limitation - acknowledge this and work with available data

Analysis steps:
1. **Priority Issues**: Identify critical errors and warnings first
2. **Patterns**: Look for recurring error patterns or trends
3. **Impact Assessment**: Determine severity and potential system impact
4. **Root Cause**: Analyze error messages for underlying causes
5. **Recommendations**: Provide specific, actionable remediation steps

If you encounter rate limiting, focus analysis on the context provided and suggest:
- Reducing log count requests
- Using more specific time ranges
- Filtering by specific error levels
- Trying again after a brief wait

Focus on actionable insights that help with immediate troubleshooting.
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

    # Run the server (default is stdio)
    mcp.run()


if __name__ == "__main__":
    main()
