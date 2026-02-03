#!/bin/bash
# Run a quick search without entering the shell
# Usage: ./docker/search.sh "iPhone 13 Pro" 50
#        ./docker/search.sh "Nintendo Switch" (defaults to 100 items)

cd "$(dirname "$0")/.." || exit 1

SEARCH_TERM="${1:?Usage: ./docker/search.sh \"search term\" [num_items]}"
NUM_ITEMS="${2:-100}"

docker compose run --rm scraper python ebay_scraper.py "$SEARCH_TERM" -n "$NUM_ITEMS"
