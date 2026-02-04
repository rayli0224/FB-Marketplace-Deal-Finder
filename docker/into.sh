#!/bin/bash
# Enter a Docker container interactively
# Usage: ./docker/into.sh [container-name]
# Defaults to deal-finder-app if no container name is provided

set -e

cd "$(dirname "$0")/.." || exit 1

# Default container name
CONTAINER_NAME="${1:-deal-finder-app}"

# Check if container is running
if ! docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ Container '${CONTAINER_NAME}' is not running."
    echo ""
    echo "Available containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}"
    echo ""
    echo "💡 Start containers first with: ./docker/restart.sh"
    exit 1
fi

echo "🔧 Entering container: ${CONTAINER_NAME}"
echo "   Type 'exit' to leave the container"
echo ""

# Exec into the container interactively
exec docker exec -it "${CONTAINER_NAME}" /bin/bash

