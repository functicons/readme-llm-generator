#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Install mypy if not already installed
if ! python -m mypy --version > /dev/null 2>&1; then
  echo "mypy not found. Please install it as part of your project's development dependencies."
  echo "For example: python -m pip install mypy"
  exit 1
fi

# Run mypy on the src and tests directories
echo "Running mypy type checking..."
python -m mypy src/ tests/

echo "Type checking completed successfully."
