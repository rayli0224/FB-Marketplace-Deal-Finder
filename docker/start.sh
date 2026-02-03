#!/bin/bash
# Start the FB Marketplace Deal Finder application
# Usage: ./docker/start.sh
# This starts all services: frontend, API, and scrapers

set -e

cd "$(dirname "$0")/.." || exit 1

echo "🚀 Starting FB Marketplace Deal Finder..."
echo ""
echo "Services:"
echo "  📱 Frontend:  http://localhost:3000"
echo "  🔌 API:       http://localhost:8000"
echo "  📊 API Docs:  http://localhost:8000/docs"
echo ""
echo "Building and starting all services..."
echo ""

docker compose up --build

