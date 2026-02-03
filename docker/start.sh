#!/bin/bash
# Start the application (frontend + backend services)
# Usage: ./docker/start.sh
# Access the app at: http://localhost:3000

cd "$(dirname "$0")/.." || exit 1

echo "Starting application..."
echo "Frontend will be available at: http://localhost:3000"
docker compose up --build

