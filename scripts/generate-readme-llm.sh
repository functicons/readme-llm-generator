#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
IMAGE_NAME="readme-llm-generator"
PROJECT_ROOT="$(dirname "$0")/.."

INCLUDE_ARGS=""
EXCLUDE_ARGS=""
REPO_PATH_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --include)
      if [[ -z "$2" || "$2" == --* ]]; then
        echo "❌ Error: --include requires an argument." >&2
        exit 1
      fi
      # These are glob patterns, passed to the Python script.
      INCLUDE_ARGS="$INCLUDE_ARGS --include $2"
      shift 2
      ;;
    --exclude)
      if [[ -z "$2" || "$2" == --* ]]; then
        echo "❌ Error: --exclude requires an argument." >&2
        exit 1
      fi
      # These are glob patterns, passed to the Python script.
      EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude $2"
      shift 2
      ;;
    *)
      # Assume it's the repository path
      if [ -n "$REPO_PATH_ARG" ]; then
        # If REPO_PATH_ARG is already set, then it's an unknown argument
        echo "❌ Error: Unknown argument or multiple repository paths: $1" >&2
        exit 1
      fi
      REPO_PATH_ARG="$1"
      shift
      ;;
  esac
done

# --- Validation ---
# Check if a repository path is provided as an argument.
if [ -z "$REPO_PATH_ARG" ]; then # Changed from $1 to $REPO_PATH_ARG
  echo "❌ Error: No repository path provided."
  echo "Usage: ./scripts/create-readme-llm.sh /path/to/your/repo [--include PATTERN] [--exclude PATTERN]"
  exit 1
fi

REPO_PATH="$REPO_PATH_ARG" # Changed from $1 to $REPO_PATH_ARG

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
# The PYTHONUNBUFFERED=1 variable ensures logs are streamed in real-time.
docker run --rm \
  --env-file ./.env \
  -e HOST_REPO_PATH="$REPO_PATH" \
  -e PYTHONUNBUFFERED=1 \
  -v "$REPO_PATH":/app/repo \
  "$IMAGE_NAME" \
  /app/repo ${INCLUDE_ARGS} ${EXCLUDE_ARGS} # Pass repo_path and then include/exclude args

echo "✨ Script finished."
