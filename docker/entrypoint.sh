#!/bin/bash
# Start Xvfb virtual display in the background
Xvfb :99 -screen 0 1920x1080x24 &

# Wait for Xvfb to start
sleep 1

# Execute the command passed to docker
exec "$@"
