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
- ✅ **Health Checks**: Liveness and readiness endpoints for orchestration
- ✅ **Authentication**: Optional token-based API security
- ✅ **Connection Pooling**: Efficient HTTP client with automatic retry logic
- ✅ **Error Handling**: Comprehensive error handling with graceful degradation
- ✅ **Request Validation**: Pydantic models for input validation
- ✅ **Configurable Timeouts**: Customizable request and connection timeouts
- ✅ **Docker Support**: Production-ready containerization

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

For HTTP-based clients:

```json
{
  "mcpServers": {
    "mezmo": {
      "url": "http://localhost:18080",
      "transport": "streamable-http",
      "description": "Production Mezmo MCP server"
    }
  }
}
```

## 🚀 Running the Server

### Local Development

```bash
# stdio transport (for local MCP clients)
python server.py --transport stdio

# HTTP transport (for web-based clients)
python server.py --transport http --host 0.0.0.0 --port 18080

# SSE transport (for legacy SSE clients)
python server.py --transport sse --host 0.0.0.0 --port 18080

# With debug logging
python server.py --transport http --log-level DEBUG
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
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:18080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## 🔧 API Reference

### Tools

#### `get_logs`

Retrieve logs from Mezmo with comprehensive filtering options.

**Parameters:**

- `count` (int, 1-10000): Number of logs to return (default: 50)
- `apps` (str, optional): Comma-separated list of applications
- `hosts` (str, optional): Comma-separated list of hosts
- `levels` (str, optional): Comma-separated list of log levels
- `query` (str, optional): Search query string
- `from_ts` (str, optional): Start time (UNIX timestamp)
- `to_ts` (str, optional): End time (UNIX timestamp)
- `prefer` (str): 'head' or 'tail' ordering (default: 'tail')
- `pagination_id` (str, optional): Pagination token

**Example Usage:**

```json
{
  "count": 100,
  "apps": "web-app,api-service",
  "levels": "ERROR,WARNING",
  "query": "database connection",
  "prefer": "tail"
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

### Health Endpoints

- `GET /health` - Basic health check
- `GET /health/live` - Liveness probe (Kubernetes compatible)
- `GET /health/ready` - Readiness probe with dependency checks

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
  http://localhost:18080/health
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
mcp dev server.py

# Test HTTP endpoint
curl http://localhost:18080/health

# Test with authentication
curl -H "Authorization: Bearer your_token" \
  http://localhost:18080/health
```

### Integration Testing

```bash
# Run with test configuration
python server.py --transport http --log-level DEBUG

# Test log retrieval
# Use your MCP client to call get_logs tool
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

4. **Health check failures**
   - Check Mezmo API connectivity
   - Verify all dependencies are available

### Debug Mode

Enable detailed logging:

```bash
python server.py --transport http --log-level DEBUG
```

### Docker Troubleshooting

```bash
# Check container logs
docker logs mezmo-mcp

# Get shell access
docker exec -it mezmo-mcp /bin/bash

# Check health status
docker exec mezmo-mcp curl -f http://localhost:18080/health
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
              path: /health/live
              port: 18080
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health/ready
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
