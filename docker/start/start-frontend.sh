#!/bin/bash
# Start the Frontend server
# Usage: ./start-frontend.sh

# Start Frontend server
cd /app/frontend
echo "🚀 Starting Frontend server..."
echo "  📱 Frontend:  http://localhost:3000"
echo ""

pnpm dev

