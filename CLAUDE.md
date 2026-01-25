# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Mezmo MCP Server - A Model Context Protocol server for retrieving logs from Mezmo. Built with Python 3.11 and FastMCP.

## Commands

```bash
# Install dependencies (uses uv if available, otherwise pip)
make install

# Create .env file from template
make env

# Run development server (HTTP transport)
make dev-http

# Run server in debug mode
make dev-debug

# Test Mezmo API connection
make test-api

# Test server health
make health

# Docker
docker-compose up -d        # Start server
docker-compose down         # Stop server
docker-compose logs -f      # View logs

# With monitoring stack (Prometheus + Grafana)
make monitor
```

## Architecture

**Two-file core:**
- `server.py` - FastMCP server exposing MCP tools/resources/prompts. Handles request validation via Pydantic models, Prometheus metrics, structured logging.
- `mezmo_api.py` - Mezmo Export API v2 client. Async HTTP with connection pooling, retry logic with exponential backoff, rate limit handling.

**Key MCP Components:**
- `get_logs` tool - Main tool for log retrieval with filtering (apps, hosts, levels, query, timestamps)
- `health://status` resource - Health check endpoint
- `analyze_logs` prompt - Template for quota-conscious log analysis workflow

**Request Flow:**
1. MCP client calls `get_logs` tool
2. `server.py` validates parameters with Pydantic `LogsRequest` model
3. Calls `fetch_latest_logs()` in `mezmo_api.py`
4. API client makes authenticated request to Mezmo Export API v2
5. Results returned with metrics recorded

## Configuration

Environment variables loaded from `.env`:
- `MEZMO_API_KEY` (required) - Service API key from Mezmo dashboard
- `MEZMO_API_BASE_URL` - Default: `https://api.mezmo.com`
- `MCP_SERVER_PORT` - Default: 18080
- `MCP_ENABLE_METRICS` - Default: true (port 9090)
- `MCP_ENABLE_AUTH` / `MCP_API_TOKEN` - Optional authentication

## API Defaults

Default behavior for `get_logs` (quota-conscious):
- Time range: Last 6 hours
- Count: 10 logs
- Levels: All (no filter)
- Prefer: tail (newest first)

## MCP Client Configuration

For Cursor, add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "mezmo": {
      "url": "http://localhost:18080/mcp",
      "transport": "streamable-http"
    }
  }
}
```
