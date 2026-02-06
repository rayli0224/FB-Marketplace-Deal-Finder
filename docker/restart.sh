#!/bin/bash
# Start/Restart the FB Marketplace Deal Finder application
# Usage: ./docker/restart.sh
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

# Start containers with --build to ensure dependencies are up-to-date
# This rebuilds the image if requirements.txt or Dockerfile changed
# --remove-orphans removes containers from previous compose file versions
echo "Starting services..."
docker compose up -d --build --remove-orphans

echo ""
echo "✅ Containers started successfully!"
echo ""
echo "📋 Container Status:"
docker compose ps
echo ""
echo "💡 To enter the container, use: ./docker/into.sh"
echo "   Inside the container, run:"
echo "     🏴‍☠️  ahoy plunder (start API server)"
echo "     🏴‍☠️  ahoy show_loot (start frontend server)"

