#!/bin/bash
# Script to run tests, potentially inside a Docker container

# Exit immediately if a command exits with a non-zero status.
set -e

# Use IMAGE_NAME from environment variable, default if not set
EFFECTIVE_IMAGE_NAME="${IMAGE_NAME:-readme-llm-generator}"

if [ "$IS_IN_DOCKER" == "true" ]; then
    # --- Running inside Docker ---
    echo "--- Already inside Docker, running tests ---"
    echo "Changing to /app/repo directory..."
    cd /app/repo

    echo "Running pytest..."
    pytest
else
    # --- Not running inside Docker, re-execute in Docker ---
    echo "--- Not inside Docker, re-launching in Docker image: ${EFFECTIVE_IMAGE_NAME} ---"
    docker run \
        --rm \
        -v "$(pwd):/app/repo" \
        -e IS_IN_DOCKER=true \
        -e IMAGE_NAME="${EFFECTIVE_IMAGE_NAME}" \
        "${EFFECTIVE_IMAGE_NAME}" \
        /app/scripts/run-tests.sh # Path to this script *inside the container*
fi

echo "--- Test script finished ---"
