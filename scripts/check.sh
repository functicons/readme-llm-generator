#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Install mypy if not already installed
if ! python -m mypy --version > /dev/null 2>&1; then
  echo "mypy not found. Installing mypy..."
  python -m pip install mypy
else
  echo "mypy is already installed."
fi

# Run mypy on the src and tests directories
echo "Running mypy type checking..."
python -m mypy src/ tests/

echo "Type checking completed successfully."
