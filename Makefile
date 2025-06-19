.PHONY: help install dev prod docker-build docker-run docker-stop test-health clean

# Default target
help:
	@echo "🚀 Mezmo MCP Server - Quick Commands"
	@echo ""
	@echo "Setup Commands:"
	@echo "  make install     - Install dependencies"
	@echo "  make env         - Create .env file from example"
	@echo ""
	@echo "Development Commands:"
	@echo "  make dev         - Run server in development mode (stdio)"
	@echo "  make dev-http    - Run server with HTTP transport"
	@echo "  make dev-debug   - Run server with debug logging"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Run server in Docker"
	@echo "  make docker-stop  - Stop Docker containers"
	@echo "  make docker-logs  - View Docker logs"
	@echo ""
	@echo "Testing Commands:"
	@echo "  make health      - Test server health"
	@echo "  make test-api    - Test Mezmo API connection"
	@echo ""
	@echo "Utility Commands:"
	@echo "  make clean       - Clean up temporary files"
	@echo "  make monitor     - Start with monitoring stack"

# Setup commands
install:
	@echo "📦 Installing dependencies..."
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --python 3.11; \
		uv pip install -r requirements.txt; \
	else \
		python -m venv .venv; \
		. .venv/bin/activate && pip install -r requirements.txt; \
	fi
	@echo "✅ Dependencies installed!"

env:
	@if [ ! -f .env ]; then \
		echo "📝 Creating .env file..."; \
		echo "# Mezmo API Configuration (Required)" > .env; \
		echo "MEZMO_API_KEY=your_service_key_here" >> .env; \
		echo "MEZMO_API_BASE_URL=https://api.mezmo.com" >> .env; \
		echo "" >> .env; \
		echo "# Server Configuration" >> .env; \
		echo "MCP_SERVER_NAME=Mezmo MCP Server" >> .env; \
		echo "MCP_SERVER_HOST=0.0.0.0" >> .env; \
		echo "MCP_SERVER_PORT=18080" >> .env; \
		echo "MCP_LOG_LEVEL=INFO" >> .env; \
		echo "" >> .env; \
		echo "# Optional: Authentication" >> .env; \
		echo "MCP_ENABLE_AUTH=false" >> .env; \
		echo "# MCP_API_TOKEN=your_secure_token_here" >> .env; \
		echo "" >> .env; \
		echo "# Optional: Metrics" >> .env; \
		echo "MCP_ENABLE_METRICS=true" >> .env; \
		echo "MCP_METRICS_PORT=9090" >> .env; \
		echo "" >> .env; \
		echo "# Development" >> .env; \
		echo "PYTHONUNBUFFERED=1" >> .env; \
		echo "✅ Created .env file. Please edit it with your Mezmo API key!"; \
		echo "⚠️  Don't forget to set MEZMO_API_KEY in .env"; \
	else \
		echo "✅ .env file already exists"; \
	fi

# Development commands
dev:
	@echo "🚀 Starting MCP server in development mode (stdio)..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run python server.py --transport stdio; \
	else \
		. .venv/bin/activate && python server.py --transport stdio; \
	fi

dev-http:
	@echo "🌐 Starting MCP server with HTTP transport..."
	@echo "📍 Server will be available at: http://localhost:18080"
	@echo "📊 Metrics will be available at: http://localhost:9090/metrics"
	@if command -v uv >/dev/null 2>&1; then \
		uv run python server.py --transport http --host 0.0.0.0 --port 18080; \
	else \
		. .venv/bin/activate && python server.py --transport http --host 0.0.0.0 --port 18080; \
	fi

dev-debug:
	@echo "🐛 Starting MCP server in debug mode..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run python server.py --transport http --log-level DEBUG; \
	else \
		. .venv/bin/activate && python server.py --transport http --log-level DEBUG; \
	fi

# Docker commands
docker-build:
	@echo "🐳 Building Docker image..."
	docker build -t mezmo-mcp:latest .
	@echo "✅ Docker image built successfully!"

docker-run: docker-build
	@echo "🐳 Starting MCP server in Docker..."
	@echo "📍 Server will be available at: http://localhost:18080"
	@echo "📊 Metrics will be available at: http://localhost:9090/metrics"
	docker run -d \
		--name mezmo-mcp-server \
		-p 18080:18080 \
		-p 9090:9090 \
		--env-file .env \
		mezmo-mcp:latest
	@echo "✅ Docker container started!"
	@echo "💡 Use 'make docker-logs' to view logs"
	@echo "💡 Use 'make docker-stop' to stop the container"

docker-stop:
	@echo "🛑 Stopping Docker containers..."
	@docker stop mezmo-mcp-server 2>/dev/null || true
	@docker rm mezmo-mcp-server 2>/dev/null || true
	@echo "✅ Containers stopped"

docker-logs:
	@echo "📋 Viewing Docker logs..."
	docker logs -f mezmo-mcp-server

monitor:
	@echo "📊 Starting with monitoring stack..."
	docker-compose --profile monitoring up -d
	@echo "✅ Started with monitoring!"
	@echo "📍 MCP Server: http://localhost:18080"
	@echo "📊 Prometheus: http://localhost:9091"
	@echo "📈 Grafana: http://localhost:3000 (admin/admin)"

# Testing commands
health:
	@echo "🏥 Testing server health..."
	@if curl -f http://localhost:18080/health >/dev/null 2>&1; then \
		echo "✅ Server is healthy!"; \
		curl -s http://localhost:18080/health | python -m json.tool; \
	else \
		echo "❌ Server health check failed"; \
		echo "💡 Make sure the server is running with 'make dev-http' or 'make docker-run'"; \
	fi

test-api:
	@echo "🔗 Testing Mezmo API connection..."
	@if command -v uv >/dev/null 2>&1; then \
		uv run python -c "import asyncio; from memo_api import test_mezmo_connection; print(asyncio.run(test_mezmo_connection()))"; \
	else \
		. .venv/bin/activate && python -c "import asyncio; from memo_api import test_mezmo_connection; print(asyncio.run(test_mezmo_connection()))"; \
	fi

quick-test: dev-http &
	@echo "⏱️  Starting quick test..."
	@sleep 3
	@make health
	@pkill -f "python server.py" || true

# Utility commands
clean:
	@echo "🧹 Cleaning up..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@docker system prune -f 2>/dev/null || true
	@echo "✅ Cleanup complete!"

# Quick start for first-time users
setup: install env
	@echo ""
	@echo "🎉 Setup complete!"
	@echo ""
	@echo "Next steps:"
	@echo "1. Edit .env file and add your MEZMO_API_KEY"
	@echo "2. Run 'make dev-http' to start the server"
	@echo "3. Run 'make health' to test if it's working"
	@echo ""

# Show status of all services
status:
	@echo "📊 Service Status:"
	@echo ""
	@echo "🐳 Docker Containers:"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep mezmo || echo "No mezmo containers running"
	@echo ""
	@echo "🌐 HTTP Endpoints:"
	@if curl -f http://localhost:18080/health >/dev/null 2>&1; then \
		echo "✅ MCP Server: http://localhost:18080 (healthy)"; \
	else \
		echo "❌ MCP Server: http://localhost:18080 (not responding)"; \
	fi
	@if curl -f http://localhost:9090/metrics >/dev/null 2>&1; then \
		echo "✅ Metrics: http://localhost:9090/metrics (available)"; \
	else \
		echo "❌ Metrics: http://localhost:9090/metrics (not available)"; \
	fi 