# Mezmo MCP Server

This project provides a Model Context Protocol (MCP) server that exposes Mezmo log retrieval as a tool for LLM agents and other MCP clients.

## Features

- **get_logs**: Retrieve logs from Mezmo directly via the Export API v2.
- Supports filtering by application, host, log level, query, time range, and pagination.
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

### 4. MCP Server Configuration

Create a `.mcp.json` file in your project root (example below):

```json
{
  "mcpServers": {
    "mezmo": {
      "command": "uv",
      "args": ["--directory", "/path/to/mezmo-mcp", "run", "server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

Replace `/path/to/mezmo-mcp` with your actual project directory.

### 5. Running the Server

```bash
mcp dev server.py
```

### 6. Testing

- Use the MCP Inspector or Claude Desktop to call the `get_logs` tool.
- Example tool call parameters:
  - `count`: Number of logs to retrieve (default: 50)
  - `apps`: (Optional) Comma-separated list of applications
  - `hosts`: (Optional) Comma-separated list of hosts
  - `levels`: (Optional) Comma-separated list of log levels (e.g., `ERROR`, `INFO`, `WARNING`)
  - `query`: (Optional) Search query string
  - `from_ts`: (Optional) Start time (UNIX timestamp, seconds or ms)
  - `to_ts`: (Optional) End time (UNIX timestamp, seconds or ms)
  - `prefer`: (Optional) 'head' or 'tail' (default: 'tail')
  - `pagination_id`: (Optional) Token for paginated results

#### Example Tool Call (JSON):

```json
{
  "count": 10,
  "apps": "twin-platform",
  "levels": "ERROR"
}
```

#### Example: Using `query`, `levels`, and `apps` together

You can use the `query` parameter to filter logs for specific keywords, error codes, or environment tags (like `production` or `staging`).

If your logs include an `environment` field (e.g., `"environment": "production"`), you can filter for production or staging logs by setting `query` to `production` or `staging` respectively. This is a common pattern for differentiating between environments.

Below are some practical examples:

**Find error logs from the `twin-platform` app in the staging environment:**

```json
{
  "count": 5,
  "apps": "twin-platform",
  "levels": "ERROR",
  "query": "staging"
}
```

**Find error logs from the `twin-platform` app in the production environment:**

```json
{
  "count": 5,
  "apps": "twin-platform",
  "levels": "ERROR",
  "query": "production"
}
```

**Find logs mentioning a specific feature or service (e.g., Bedrock):**

```json
{
  "count": 5,
  "apps": "twin-platform",
  "query": "bedrock"
}
```

This will return the 5 most recent logs from the `twin-platform` app that contain the word "bedrock" anywhere in the log line.

## Tool: get_logs

- **Description:** Retrieve logs from Mezmo Export API v2.
- **Parameters:**
  - `count` (int, default 50): Number of logs to return (max 10,000)
  - `apps` (str, optional): Comma-separated list of applications
  - `hosts` (str, optional): Comma-separated list of hosts
  - `levels` (str, optional): Comma-separated list of log levels
  - `query` (str, optional): Search query
  - `from_ts` (str, optional): Start time (UNIX timestamp, seconds or ms)
  - `to_ts` (str, optional): End time (UNIX timestamp, seconds or ms)
  - `prefer` (str, optional): 'head' or 'tail' (default: 'tail')
  - `pagination_id` (str, optional): Token for paginated results
- **Returns:** List of log lines (raw format)

> **Note:**
>
> - These parameters are pulled directly from the [Mezmo Log Analysis Export API documentation](https://docs.mezmo.com/log-analysis-api#export).
> - For large exports (>10,000 logs), pagination is supported by the Mezmo API and can be accessed via the `pagination_id` parameter.
> - All API/network errors are handled gracefully with user-friendly messages.

## References

- [Mezmo Log Analysis API](https://docs.mezmo.com/log-analysis-api#export)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
