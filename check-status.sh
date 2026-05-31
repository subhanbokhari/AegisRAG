#!/bin/bash

echo "=== AegisRAG Docker Compose Status ==="
echo "Time: $(date)"
echo ""

echo "1. Process Status:"
if pgrep -f "docker-compose" > /dev/null; then
    echo "   ✓ docker-compose is running"
else
    echo "   ✗ docker-compose is NOT running"
fi

echo ""
echo "2. Docker Containers:"
docker ps -a --filter "name=aegis" --format "table {{.Names}}\t{{.Status}}"

echo ""
echo "3. Log File Size:"
wc -l /home/subhan/Desktop/Arag/docker-compose.log 2>/dev/null || echo "Log file not found"

echo ""
echo "4. Last 10 log entries:"
tail -10 /home/subhan/Desktop/Arag/docker-compose.log 2>/dev/null

echo ""
echo "=== To run this check again: bash /home/subhan/Desktop/Arag/check-status.sh ==="
