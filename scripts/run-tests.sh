#!/bin/bash

# Check if pytest is installed
if ! command -v pytest &> /dev/null
then
    echo "pytest could not be found, installing..."
    pip install pytest
else
    echo "pytest is already installed."
fi

# Run pytest from the root of the repository
echo "Running pytest..."
pytest
