#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
IMAGE_NAME="readme-llm-generator"
PROJECT_ROOT="$(dirname "$0")/.."

# --- Validation ---
# Check if a repository path is provided as an argument.
if [ -z "$1" ]; then
  echo "❌ Error: No repository path provided."
  echo "Usage: ./scripts/create-readme-llm.sh /path/to/your/repo"
  exit 1
fi

REPO_PATH="$1"

# Check if the .env file exists in the project root.
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "❌ Error: .env file not found in project root."
    echo "Please copy .env.example to .env and add your GOOGLE_API_KEY."
    exit 1
fi

# Check if the provided repository directory exists.
if [ ! -d "$REPO_PATH" ]; then
  echo "❌ Error: Target directory '$REPO_PATH' does not exist."
  exit 1
fi

# --- Execution ---
echo "🚀 Running the generator on repository: $REPO_PATH"

# Run the Docker container, mounting the target repository into the container.
# We now pass the REPO_PATH as an environment variable for better logging.
docker run --rm \
  --env-file ./.env \
  -e HOST_REPO_PATH="$REPO_PATH" \
  -v "$REPO_PATH":/app/repo \
  "$IMAGE_NAME"

echo "✨ Script finished."