#!/bin/bash
# Run the eBay Price Analyzer interactively
# Usage: ./docker/shell.sh

cd "$(dirname "$0")/.." || exit 1

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  No .env file found!"
    echo "   Copy .env.example to .env and add your eBay API credentials"
    echo "   cp .env.example .env"
    exit 1
fi

# Load environment variables and run
docker compose run --rm scraper
