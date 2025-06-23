# Modern Mezmo MCP Server

A production-ready Model Context Protocol (MCP) server that provides robust access to Mezmo log retrieval with comprehensive error handling, authentication, observability, and scalability features.

## 🚀 Features

### Core Functionality

- **get_logs**: Retrieve logs from Mezmo Export API v2 with advanced filtering
- **analyze_logs**: AI-powered log analysis prompt templates
- **health_check**: Comprehensive health monitoring and dependency checking

### Production-Ready Features

- ✅ **Multiple Transport Protocols**: stdio, HTTP, and SSE support
- ✅ **Structured Logging**: JSON-formatted logs with correlation IDs
- ✅ **Prometheus Metrics**: Request counters, latency histograms, and gauges
- ✅ **Authentication**: Optional token-based API security
- ✅ **Connection Pooling**: Efficient HTTP client with automatic retry logic
- ✅ **Error Handling**: Comprehensive error handling with graceful degradation
- ✅ **Request Validation**: Pydantic models for input validation
- ✅ **Configurable Timeouts**: Customizable request and connection timeouts
- ✅ **Docker Support**: Production-ready containerization
- ✅ **Smart Defaults**: Works out-of-the-box with sensible 4-hour log window

## 📋 Prerequisites

- Python 3.11+
- [uv](https://astral.sh/uv/) for environment management (recommended)
- Mezmo Service API Key
- Docker (for containerized deployment)

## 🛠️ Installation

### Local Development

```bash
# Clone the repository
git clone <repository-url>
cd mezmo-mcp

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

### Docker Installation

```bash
# Build the Docker image
docker build -t mezmo-mcp:latest .

# Or pull from registry (if published)
docker pull mezmo-mcp:latest
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with the following configuration:

```bash
# Required: Mezmo API Configuration
MEZMO_API_KEY=your_service_key_here
MEZMO_API_BASE_URL=https://api.mezmo.com

# Server Configuration
MCP_SERVER_NAME="Mezmo MCP Server"
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=18080
MCP_LOG_LEVEL=INFO

# Optional: Authentication
MCP_ENABLE_AUTH=false
MCP_API_TOKEN=your_secure_token_here

# Optional: Metrics and Monitoring
MCP_ENABLE_METRICS=true
MCP_METRICS_PORT=9090

# Optional: API Client Configuration
MEZMO_REQUEST_TIMEOUT=30
MEZMO_MAX_RETRIES=3
MEZMO_RETRY_DELAY=1.0
```

### MCP Client Configuration

For MCP clients like Claude Desktop, Cursor, or other tools:

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

For HTTP-based clients (like Cursor):

```json
{
  "mcpServers": {
    "mezmo": {
      "url": "http://localhost:18080/mcp",
      "transport": "streamable-http",
      "description": "Mezmo log retrieval MCP server - provides access to Mezmo logs and analysis"
    }
  }
}
```

**Note:** Make sure to include `/mcp` in the URL path for HTTP transport.

## 🚀 Quick Start with Docker + Cursor

The easiest way to get started is using Docker with Cursor:

### 1. Setup and Run with Docker

```bash
# Clone and setup
git clone <repository-url>
cd mezmo-mcp

# Create environment file and add your API key
make env
# Edit .env file and add your MEZMO_API_KEY

# Run with Docker (persistent container)
make docker-run
```

### 2. Configure Cursor

Add this to your `.cursor/mcp.json` file:

```json
{
  "mcpServers": {
    "mezmo": {
      "url": "http://localhost:18080/mcp",
      "transport": "streamable-http",
      "description": "Mezmo log retrieval MCP server"
    }
  }
}
```

### 3. Restart Cursor and Use

After restarting Cursor, you'll have access to the `get_logs` tool for retrieving and analyzing your Mezmo logs!

### Available Make Commands

```bash
make env            # Create .env file from example
make install        # Install dependencies
make dev            # Run in stdio mode for Claude Desktop
make dev-http       # Run in HTTP mode for Cursor
make docker-build   # Build Docker image
make docker-run     # Run Docker container (persistent)
make docker-stop    # Stop Docker container
make docker-logs    # View Docker container logs
make health         # Check server health
make test-api       # Test Mezmo API connection
make clean          # Clean up containers and images
```

## 🚀 Running the Server

### Local Development

```bash
# stdio transport (for local MCP clients like Claude Desktop)
uv run fastmcp run server.py

# HTTP transport (for web-based clients like Cursor)
uv run fastmcp run server.py --transport streamable-http --port 18080

# With custom host and port
uv run fastmcp run server.py --transport streamable-http --host 0.0.0.0 --port 18080

# Direct Python execution (stdio only)
python server.py
```

### Docker Deployment

```bash
# Run with environment file
docker run -d \
  --name mezmo-mcp \
  -p 18080:18080 \
  -p 9090:9090 \
  --env-file .env \
  mezmo-mcp:latest

# Run with inline environment variables
docker run -d \
  --name mezmo-mcp \
  -p 18080:18080 \
  -e MEZMO_API_KEY=your_key_here \
  -e MCP_ENABLE_METRICS=true \
  mezmo-mcp:latest
```

### Docker Compose

```yaml
version: "3.8"
services:
  mezmo-mcp:
    build: .
    ports:
      - "18080:18080"
      - "9090:9090"
    env_file:
      - .env
    restart: unless-stopped
# Or use the provided docker-compose.yml
# docker-compose up -d
```

## 🔧 API Reference

### Tools

#### `get_logs`

Retrieve logs from Mezmo with comprehensive filtering options.

**⭐ Smart Defaults**: Works out-of-the-box! When no timestamps are specified, automatically retrieves logs from the **last 4 hours** - perfect for debugging production issues.

**Parameters:**

- `count` (int, 1-10000): Number of logs to return (default: 50)
- `apps` (str, optional): Comma-separated list of applications
- `hosts` (str, optional): Comma-separated list of hosts
- `levels` (str, optional): Comma-separated list of log levels
- `query` (str, optional): Search query string
- `from_ts` (str, optional): Start time (UNIX timestamp) - defaults to 4 hours ago
- `to_ts` (str, optional): End time (UNIX timestamp) - defaults to now
- `prefer` (str): 'head' or 'tail' ordering (default: 'tail')
- `pagination_id` (str, optional): Pagination token

**Example Usage:**

```json
// Simple usage - gets last 4 hours automatically
{
  "count": 50
}

// With filters - still uses 4-hour window
{
  "count": 100,
  "apps": "web-app,api-service",
  "levels": "ERROR,WARNING",
  "query": "database connection"
}

// Custom time range
{
  "count": 100,
  "from_ts": "1640995200",
  "to_ts": "1640998800",
  "levels": "ERROR"
}
```

### Resources

#### `health://status`

Get comprehensive health status including dependency checks.

**Returns:** JSON health status with timestamp and dependency information.

### Prompts

#### `analyze_logs`

Generate AI-optimized prompts for log analysis.

**Parameters:**

- `query` (str): Search query for analysis
- `time_range` (str): Time range (default: "1h")
- `log_level` (str): Log level to focus on (default: "ERROR")

## 📊 Monitoring and Observability

### Metrics (Prometheus)

Available at `http://localhost:9090/metrics`:

- `mezmo_mcp_requests_total` - Total request count by tool and status
- `mezmo_mcp_request_duration_seconds` - Request latency histogram
- `mezmo_mcp_active_connections` - Active connection gauge
- `mezmo_mcp_logs_fetched_total` - Total logs retrieved counter

### Structured Logging

All logs are output in JSON format for easy parsing:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "info",
  "logger": "mezmo_mcp_server",
  "message": "Processing get_logs request",
  "count": 50,
  "apps": "web-app",
  "levels": "ERROR"
}
```

## 🔒 Security

### Authentication

Enable token-based authentication:

```bash
export MCP_ENABLE_AUTH=true
export MCP_API_TOKEN=your_secure_token_here
```

Include the token in client requests:

```bash
curl -H "Authorization: Bearer your_secure_token_here" \
  http://localhost:18080/mcp/
```

### Best Practices

- Use strong, randomly generated API tokens
- Enable HTTPS in production environments
- Regularly rotate API tokens
- Monitor authentication logs for suspicious activity
- Use non-root containers in production

## 🧪 Testing

### Manual Testing

```bash
# Test with MCP Inspector
fastmcp dev server.py

# Test HTTP endpoint health
curl http://localhost:18080/mcp/

# Test with authentication
curl -H "Authorization: Bearer your_token" \
  http://localhost:18080/mcp/
```

### Integration Testing

```bash
# Run with test configuration
python server.py --transport http --log-level DEBUG

# Test log retrieval using make command
make test-api
```

## 🐛 Troubleshooting

### Common Issues

1. **"MEZMO_API_KEY not set"**

   - Ensure your `.env` file contains the API key
   - Check that the environment variable is loaded correctly

2. **Connection timeouts**

   - Increase `MEZMO_REQUEST_TIMEOUT` value
   - Check network connectivity to Mezmo API

3. **Authentication failures**

   - Verify `MCP_API_TOKEN` is set correctly
   - Ensure client is sending proper Authorization header

4. **"from/to timestamp required" errors**
   - This should not happen with the latest version - the server automatically provides 4-hour defaults
   - If you see this error, ensure you're using the latest version

### Debug Mode

Enable detailed logging by setting environment variable:

```bash
export MCP_LOG_LEVEL=DEBUG
uv run fastmcp run server.py --transport streamable-http --port 18080
```

### Docker Troubleshooting

```bash
# Check container logs
docker logs mezmo-mcp-server

# Get shell access
docker exec -it mezmo-mcp-server /bin/bash

# Check container status
docker-compose ps
```

## 📈 Performance Optimization

### Connection Pooling

The server uses HTTP connection pooling with configurable limits:

- Max connections: 20
- Max keepalive connections: 10
- Keepalive expiry: 30 seconds

### Retry Logic

Automatic retry with exponential backoff:

- Max retries: 3 (configurable)
- Base delay: 1 second
- Exponential backoff multiplier: 2

### Timeouts

Configurable timeouts for different operations:

- Connect timeout: 5 seconds
- Read timeout: 30 seconds (configurable)
- Pool timeout: 2 seconds

## 🔄 Deployment Strategies

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mezmo-mcp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mezmo-mcp
  template:
    metadata:
      labels:
        app: mezmo-mcp
    spec:
      containers:
        - name: mezmo-mcp
          image: mezmo-mcp:latest
          ports:
            - containerPort: 18080
            - containerPort: 9090
          env:
            - name: MEZMO_API_KEY
              valueFrom:
                secretKeyRef:
                  name: mezmo-secrets
                  key: api-key
          livenessProbe:
            httpGet:
              path: /mcp/
              port: 18080
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /mcp/
              port: 18080
            initialDelaySeconds: 5
            periodSeconds: 5
```

### Load Balancing

For high availability, deploy multiple instances behind a load balancer:

- Use health checks for automatic failover
- Configure session affinity if needed
- Monitor metrics across all instances

## 📚 References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification)
- [FastMCP Documentation](https://fastmcp.ai/)
- [Mezmo Log Analysis API](https://docs.mezmo.com/log-analysis-api#export)
- [Prometheus Metrics](https://prometheus.io/docs/concepts/metric_types/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
