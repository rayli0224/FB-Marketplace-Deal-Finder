#!/bin/bash
# Start the Frontend server
# Usage: ./start-frontend.sh

# Start Frontend server
cd /app/frontend
echo "🚀 Starting Frontend server..."
echo "  📱 Frontend:  http://localhost:3000"
echo ""

# Ensure dependencies are installed (in case volume mount interfered)
if [ ! -d "node_modules/@hookform" ]; then
  echo "📦 Installing missing dependencies..."
  pnpm install
fi

pnpm dev

