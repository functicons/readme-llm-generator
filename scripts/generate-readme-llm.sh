#!/bin/bash
# Script to run the README generator, potentially inside a Docker container

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Initializations ---
EFFECTIVE_IMAGE_NAME="${IMAGE_NAME:-readme-llm-generator}"
REPO_PATH_ARG=""
# For this simplified test, assume no include/exclude args are passed from 'make run'
_INCLUDE_ARGS_FOR_PYTHON=""
_EXCLUDE_ARGS_FOR_PYTHON=""

if [ -n "$1" ]; then
    REPO_PATH_ARG="$1"
    echo "Debug: REPO_PATH_ARG set to $REPO_PATH_ARG from \$1"
else
    echo "Debug: No REPO_PATH_ARG provided as \$1 to the script."
    # This would be an error condition for the 'else' branch later if REPO_PATH_ARG is empty.
fi

if [ "$IS_IN_DOCKER" == "true" ]; then
    # --- Running inside Docker ---
    echo "--- Already inside Docker, running README generator ---"

    # When IS_IN_DOCKER is true, $1 is REPO_PATH_ARG (e.g., /app/repo)
    # and subsequent arguments ($2 onwards) would be include/exclude pairs.
    EFFECTIVE_REPO_PATH_IN_CONTAINER="$1" # This is /app/repo
    shift # Remove repo path, remaining $@ are include/exclude options for python

    # In this simplified test, we assume no include/exclude args are passed here either.
    # If they were, the original logic to rebuild PYTHON_SCRIPT_OPTIONS was:
    # PYTHON_SCRIPT_OPTIONS=""
    # while [[ $# -gt 0 ]]; do
    #   case "$1" in
    #     --include) PYTHON_SCRIPT_OPTIONS="$PYTHON_SCRIPT_OPTIONS --include $2"; shift 2 ;;
    #     --exclude) PYTHON_SCRIPT_OPTIONS="$PYTHON_SCRIPT_OPTIONS --exclude $2"; shift 2 ;;
    #     *) echo "Unknown option inside Docker: $1"; exit 1 ;;
    #   esac
    # done
    # For now, just pass any remaining args:
    PYTHON_SCRIPT_OPTIONS="$@"


    echo "Executing python /app/src/generate_readme_llm.py ${EFFECTIVE_REPO_PATH_IN_CONTAINER} ${PYTHON_SCRIPT_OPTIONS}"
    python /app/src/generate_readme_llm.py "${EFFECTIVE_REPO_PATH_IN_CONTAINER}" ${PYTHON_SCRIPT_OPTIONS}

else
    # --- Not running inside Docker, re-execute in Docker ---
    echo "Debug: In outer script, REPO_PATH_ARG is $REPO_PATH_ARG"
    if [ -z "$REPO_PATH_ARG" ]; then
      echo "❌ Error: REPO_PATH argument is not set."
      echo "Usage: ./scripts/generate-readme-llm.sh /absolute/path/to/your/repo [--include PATTERN] [--exclude PATTERN]"
      exit 1
    fi

    if [[ "$REPO_PATH_ARG" != /* ]]; then
      echo "❌ Error: REPO_PATH must be an absolute path for Docker mount."
      echo "Provided: $REPO_PATH_ARG"
      exit 1
    fi

    if [ ! -f "$(pwd)/.env" ]; then
        echo "⚠️ Warning: .env file not found in current directory ($(pwd)). The script inside Docker might not have access to GOOGLE_API_KEY."
    fi

    echo "--- Not inside Docker, re-launching in Docker image: ${EFFECTIVE_IMAGE_NAME} ---"

    # In this simplified version, _INCLUDE_ARGS_FOR_PYTHON and _EXCLUDE_ARGS_FOR_PYTHON are empty.
    # If they had values, they'd be passed here.
    docker run \
        --rm \
        -v "$REPO_PATH_ARG:/app/repo" \
        -v "$(pwd)/.env:/app/.env" \
        -e IS_IN_DOCKER=true \
        -e IMAGE_NAME="${EFFECTIVE_IMAGE_NAME}" \
        -e PYTHONUNBUFFERED=1 \
        "${EFFECTIVE_IMAGE_NAME}" \
        /app/scripts/generate-readme-llm.sh /app/repo $_INCLUDE_ARGS_FOR_PYTHON $_EXCLUDE_ARGS_FOR_PYTHON
fi

echo "--- README generator script finished ---"
