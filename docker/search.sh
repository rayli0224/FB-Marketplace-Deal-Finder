#!/bin/bash
# Run a quick eBay price search
# Usage: ./docker/search.sh "iPhone 13 Pro" [num_items]

cd "$(dirname "$0")/.." || exit 1

SEARCH_TERM="${1:?Usage: ./docker/search.sh \"search term\" [num_items]}"
NUM_ITEMS="${2:-100}"

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  No .env file found!"
    echo "   Copy .env.example to .env and add your eBay API credentials"
    exit 1
fi

docker compose run --rm scraper python ebay_scraper.py "$SEARCH_TERM" -n "$NUM_ITEMS"
