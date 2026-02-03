#!/bin/bash
# Build the Docker image
# Usage: ./docker/build.sh

cd "$(dirname "$0")/.." || exit 1
docker compose build
