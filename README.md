# Mezmo MCP Server

This project provides a Model Context Protocol (MCP) server that exposes Mezmo log retrieval as a tool for LLM agents and other MCP clients.

## Features

- **get_latest_logs**: Retrieve the latest logs from Mezmo directly via the Export API v2.
- Supports filtering by application and search query.
- Returns logs directly in the response (no email required).

## Setup

### 1. Prerequisites

- Python 3.10+
- [uv](https://astral.sh/uv/) for environment and dependency management
- Mezmo Service API Key

### 2. Installation

```bash
uv venv
source .venv/bin/activate
uv add "mcp[cli]" httpx python-dotenv
```

### 3. Configuration

Copy `.env.example` to `.env` and fill in your Mezmo API key:

```
cp .env.example .env
```

Edit `.env`:

```
MEZMO_API_KEY=your_service_key_here
# Optionally override the base URL
# MEZMO_API_BASE_URL=https://api.mezmo.com
```

### 4. Running the Server

```bash
mcp dev server.py
```

### 5. Testing

- Use the MCP Inspector or Claude Desktop to call the `get_latest_logs` tool.
- Example tool call parameters:
  - `count`: Number of logs to retrieve (default: 50)
  - `app_name`: (Optional) Application name to filter logs
  - `query`: (Optional) Search query string

## Project Structure

```
mezmo-mcp/
  .env
  .env.example
  server.py
  memo_api.py
  tools.py
  README.md
```

## Tool: get_latest_logs

- **Description:** Retrieve the latest N logs from Mezmo.
- **Parameters:**
  - `count` (int, default 50): Number of logs to return (max 10,000)
  - `app_name` (str, optional): Filter logs by application
  - `query` (str, optional): Search query
- **Returns:** List of log lines (raw format)

## Notes

- For large exports (>10,000 logs), pagination is supported by the Mezmo API but not yet exposed in this tool.
- All API/network errors are handled gracefully with user-friendly messages.

## References

- [Mezmo Log Analysis API](https://docs.mezmo.com/log-analysis-api#export)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
