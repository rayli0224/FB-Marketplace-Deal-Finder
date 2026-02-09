#!/bin/bash
# Start the API server
# Usage: ./start-api.sh [--debug]

# Start Xvfb if not already running
if ! pgrep -x "Xvfb" > /dev/null; then
    Xvfb :99 -screen 0 1920x1080x24 &
    sleep 1
fi

# Check for --debug flag and set DEBUG environment variable
DEBUG_MODE=""
if [[ "$*" == *"--debug"* ]]; then
    export DEBUG=1
    DEBUG_MODE=" (DEBUG MODE)"
fi

# Start API server
cd /app
echo "🚀 Starting API server${DEBUG_MODE}..."
echo "  🔌 API:       http://localhost:8000"
echo "  📊 API Docs:  http://localhost:8000/docs"
if [[ -n "$DEBUG_MODE" ]]; then
    echo "  🐛 Debug logging enabled"
fi
echo ""

uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log

