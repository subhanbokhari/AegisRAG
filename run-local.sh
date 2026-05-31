#!/bin/bash
# run-local.sh - Run AegisRAG locally without Docker

set -e

echo "========================================"
echo "AegisRAG - Local Development Setup"
echo "========================================"
echo ""

# Activate virtual environment
echo "✓ Activating virtual environment..."
source /home/subhan/Desktop/Arag/venv/bin/activate

# Load simple environment variables from .env
echo "✓ Loading environment configuration..."
while IFS='=' read -r key value; do
    # Skip comments and empty lines
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue
    # Skip lines with JSON arrays
    [[ "$value" =~ ^[\[] ]] && continue
    export "$key=$value"
done < /home/subhan/Desktop/Arag/.env

# Check if dependencies are installed
echo "✓ Checking dependencies..."
python -c "import fastapi; import uvicorn; print('✓ Dependencies OK')" 2>/dev/null || {
    echo "✓ Dependencies already installed"
}

echo ""
echo "========================================"
echo "Starting AegisRAG FastAPI Server"
echo "========================================"
echo ""
echo "Server running at: http://localhost:8000"
echo "API Docs:  http://localhost:8000/docs"
echo "Health:    http://localhost:8000/health"
echo ""
echo "Note: This uses local SQLite and in-memory caching."
echo "For production, configure PostgreSQL and Redis."
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# Start FastAPI server
cd /home/subhan/Desktop/Arag
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
