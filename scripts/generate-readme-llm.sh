#!/bin/bash
# Script to run the README generator, always by launching a Docker container.
# This script is the user-facing wrapper.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Initializations ---
EFFECTIVE_IMAGE_NAME="${IMAGE_NAME:-readme-llm-generator}"
REPO_PATH_ARG=""
PASSTHROUGH_ARGS="" # For include/exclude patterns

# The first argument is the repository path.
# All subsequent arguments are passthrough arguments for the internal script.
if [ -n "$1" ]; then
    REPO_PATH_ARG="$1"
    echo "Debug (wrapper): REPO_PATH_ARG set to $REPO_PATH_ARG from \$1"
    shift # Remove repo path, remaining $@ are include/exclude options
    PASSTHROUGH_ARGS="$@" # Store the remaining arguments
else
    echo "❌ Error (wrapper): REPO_PATH argument is not set."
    echo "Usage: ./scripts/generate-readme-llm.sh /absolute/path/to/your/repo [--include PATTERN] [--exclude PATTERN]"
    exit 1
fi

# Validate REPO_PATH_ARG: must be an absolute path for Docker volume mounting.
if [[ "$REPO_PATH_ARG" != /* ]]; then
  echo "❌ Error (wrapper): REPO_PATH must be an absolute path for Docker mount."
  echo "Provided: $REPO_PATH_ARG"
  exit 1
fi

# Check for .env file in the current directory (optional warning).
if [ ! -f "$(pwd)/.env" ]; then
    echo "⚠️ Warning (wrapper): .env file not found in current directory ($(pwd)). The script inside Docker might not have access to GOOGLE_API_KEY."
fi

echo "--- Wrapper script: Launching README generation in Docker image: ${EFFECTIVE_IMAGE_NAME} ---"

# Execute the internal script INSIDE the Docker container.
# Note: IS_IN_DOCKER=true is set here for the internal script's environment,
# even though this wrapper doesn't check it. This maintains compatibility
# if the internal script *were* to check it, but it's not strictly necessary
# for the new internal script which is dedicated to running in Docker.
docker run \
    --rm \
    -v "$REPO_PATH_ARG:/app/repo" \
    -v "$(pwd)/.env:/app/.env" \
    -e IMAGE_NAME="${EFFECTIVE_IMAGE_NAME}" \
    -e PYTHONUNBUFFERED=1 \
    "${EFFECTIVE_IMAGE_NAME}" \
    python /app/src/generate_readme_llm.py /app/repo ${PASSTHROUGH_ARGS}

echo "--- Wrapper script: README generator process finished ---"
