#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
IMAGE_NAME="readme-llm-generator"

echo "Building Docker image: $IMAGE_NAME..."

# The script is in a subdirectory, so we build from the parent directory (project root).
docker build -t "$IMAGE_NAME" "$(dirname "$0")/.."

echo "✅ Docker image '$IMAGE_NAME' built successfully."