#!/bin/bash
# Start the API server
# Usage: ./start-api.sh

# Start Xvfb if not already running
if ! pgrep -x "Xvfb" > /dev/null; then
    Xvfb :99 -screen 0 1920x1080x24 &
    sleep 1
fi

# Start API server
cd /app
echo "🚀 Starting API server..."
echo "  🔌 API:       http://localhost:8000"
echo "  📊 API Docs:  http://localhost:8000/docs"
echo ""

uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

