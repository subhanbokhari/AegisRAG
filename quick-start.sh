#!/bin/bash
# quick-start.sh - One-command setup for AegisRAG v2.0

set -e

echo "======================================"
echo "AegisRAG v2.0 - Quick Start Setup"
echo "======================================"
echo ""

# Check prerequisites
echo "✓ Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo "✗ Docker not found. Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "✗ Docker Compose not found. Install from: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✓ Docker and Docker Compose found"
echo ""

# Setup environment
echo "✓ Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example"
    echo "  ⚠️  Remember to customize passwords in .env for production"
else
    echo "  .env already exists"
fi

echo ""

# Build images
echo "✓ Building Docker images..."
docker-compose build --no-cache

echo ""

# Start services
echo "✓ Starting services..."
docker-compose up -d

echo ""
echo "✓ Waiting for services to be healthy..."
sleep 15

# Health check
echo ""
echo "✓ Checking service health..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ AegisRAG is healthy!"
        break
    fi
    attempt=$((attempt + 1))
    echo "  Attempt $attempt/$max_attempts..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "✗ Service health check failed"
    echo "  Run: docker-compose logs aegis_app"
    exit 1
fi

echo ""
echo "======================================"
echo "✓ Setup Complete!"
echo "======================================"
echo ""
echo "Services running:"
echo "  - API: http://localhost:8000"
echo "  - Health: curl http://localhost:8000/health"
echo "  - Metrics: http://localhost:8000/metrics"
echo "  - Prometheus: http://localhost:9090"
echo "  - Database: localhost:5432 (aegis_admin/aegis_rag)"
echo "  - Redis: localhost:6379"
echo ""
echo "Test the API:"
echo "  curl -X POST http://localhost:8000/query \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"query\": \"What is AegisRAG?\"}'"
echo ""
echo "View logs:"
echo "  docker-compose logs -f aegis_app"
echo ""
echo "Stop services:"
echo "  docker-compose down"
echo ""
echo "For more information, see README.md"
echo ""
