# Mezmo MCP Server

A Model Context Protocol (MCP) server for retrieving logs from Mezmo. Works out-of-the-box with automatic 4-hour time windows - just add your API key and run!

## 🚀 Quick Start

### 1. Get Your API Key

Get your Mezmo Service API key from the Mezmo dashboard.

### 2. Run with Docker

```bash
# Clone the repository
git clone https://github.com/riefer02/mezmo-logs-mcp
cd mezmo-mcp

# Create .env file with your API key
echo "MEZMO_API_KEY=your_service_key_here" > .env

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

The `get_logs` tool automatically retrieves logs from the **last 4 hours** when no time range is specified - perfect for debugging.

**Simple usage:**

```json
{
  "count": 50
}
```

**With filters:**

```json
{
  "count": 100,
  "apps": "web-app,api-service",
  "levels": "ERROR,WARNING",
  "query": "database connection"
}
```

**Custom time range:**

```json
{
  "count": 100,
  "from_ts": "1640995200",
  "to_ts": "1640998800"
}
```

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
