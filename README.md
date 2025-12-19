# Mezmo MCP Server

A Model Context Protocol (MCP) server for retrieving logs from Mezmo. Quota-conscious design with intelligent defaults - just add your API key and run!

## ⚡ Smart Defaults

- **Time Range**: Last 6 hours (when not specified) - balances quota with finding actual logs
- **Log Count**: 10 logs per request
- **Log Levels**: All levels (you control filtering)

**Recommended Workflow**:
1. First, fetch 3-5 logs to discover available apps and log shape
2. Then, filter by specific app(s) you're debugging
3. Add level filtering for ERROR/WARNING to reduce noise
4. Increase count only after filters are in place (e.g., 20-50)
5. This approach minimizes quota usage significantly!

## 🚀 Quick Start

### 1. Get Your API Key

Get your Mezmo Service API key from the Mezmo dashboard.

### 2. Run with Docker

```bash
# Clone the repository
# (replace with your fork/clone URL)
git clone <your-repo-url>
cd <your-repo-dir>

# Create your local .env (never commit it)
cp env.example .env
# then edit .env and set MEZMO_API_KEY

# Build and run
docker-compose up -d
```

### 3. Configure Your MCP Client

**For Cursor** (add to `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "mezmo": {
      "url": "http://localhost:18080/mcp",
      "transport": "streamable-http",
      "description": "Mezmo log retrieval"
    }
  }
}
```

**For Claude Desktop** (add to MCP settings):

```json
{
  "mcpServers": {
    "mezmo": {
      "command": "docker",
      "args": ["exec", "mezmo-mcp-server", "python", "server.py"]
    }
  }
}
```

### 4. Start Using

Restart your MCP client and you'll have access to the `get_logs` tool!

## 📋 Usage

The `get_logs` tool automatically retrieves logs from the **last 6 hours** when no time range is specified - perfect for debugging while conserving quota.

**Step 1: Discover available apps (3-5 logs):**

```json
{
  "count": 3,
  "levels": "ERROR,WARNING"
}
```

**Step 2: Filter by specific app:**

```json
{
  "count": 10,
  "apps": "app-a",
  "levels": "ERROR,WARNING"
}
```

**Advanced filtering (scale up only after filters work):**

```json
{
  "count": 50,
  "apps": "app-a,app-b",
  "levels": "ERROR,WARNING",
  "query": "database connection"
}
```

**Custom time range (use sparingly - impacts quota):**

```json
{
  "count": 50,
  "apps": "app-a",
  "from_ts": "1640995200",
  "to_ts": "1640998800"
}
```

### 💡 Quota-Conscious Tips

1. **Always filter by app** when possible - this drastically reduces results
2. **Start tiny** - use count=3-5 for discovery, then increase if needed
3. **Add level filtering** - specify levels="ERROR,WARNING" to reduce noise
4. **Use default 6-hour window** unless you need wider historical data

### 🔐 Security / Secrets

- **Never commit `.env`** (it contains your `MEZMO_API_KEY`).
- Prefer using `.env.example` as a template and keep your real values local.
- If you enable MCP authentication (`MCP_ENABLE_AUTH=true`), keep `MCP_API_TOKEN` secret as well.

## 🛠️ Commands

```bash
docker-compose up -d     # Start the server
docker-compose down      # Stop the server
docker-compose logs -f   # View logs
```

## 🐛 Troubleshooting

**Container won't start?**

- Check your `.env` file has `MEZMO_API_KEY=your_actual_key`
- View logs: `docker-compose logs`

**Can't connect from MCP client?**

- Ensure container is running: `docker-compose ps`
- Restart your MCP client after configuration changes

That's it! The server runs on port 18080 and automatically handles time windows, retries, and error handling.
