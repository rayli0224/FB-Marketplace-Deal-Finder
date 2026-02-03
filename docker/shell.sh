#!/bin/bash
# Drop into an interactive shell in the scraper container
# Usage: ./docker/shell.sh

cd "$(dirname "$0")/.." || exit 1
docker compose run --rm scraper
