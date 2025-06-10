# Makefile for the README.llm Generator Project

# --- Configuration ---
# Use ':=' for a simple variable assignment that is evaluated only once.
IMAGE_NAME := readme-llm-generator

# Use '?=' to set REPO_PATH only if it's not already set.
# This allows it to be passed from the command line.
REPO_PATH ?=

# --- Shell Scripts ---
# Define paths to the scripts for easier maintenance
BUILD_SCRIPT := ./scripts/create-image.sh
RUN_SCRIPT   := ./scripts/generate-readme-llm.sh

# --- Commands ---
# .PHONY declares targets that are not actual files.
.PHONY: help setup build run clean

# The default command executed when you just type 'make'.
default: help

help:
	@echo "Commands for README.llm Generator:"
	@echo ""
	@echo "Usage:"
	@echo "  make setup    - 🚀 Create the .env file from the example to get started."
	@echo "  make build    - 🛠️  Build the Docker image by calling the build script."
	@echo "  make run      - ✨ Run the generator. Requires a path. Usage: make run REPO_PATH=/path/to/your/repo"
	@echo "  make clean    - 🧹 Remove dangling Docker images to save space."
	@echo "  make help     - ℹ️  Display this help message."
	@echo ""

setup:
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
		echo "✅ .env file created. Please edit it to add your GOOGLE_API_KEY."; \
	else \
		echo "⚠️  .env file already exists. Skipping creation."; \
	fi

build:
	@echo "--- Calling build script ---"
	@$(BUILD_SCRIPT)

run:
	@if [ -z "$(REPO_PATH)" ]; then \
		echo "❌ Error: REPO_PATH is not set."; \
		echo "Usage: make run REPO_PATH=/path/to/your/repo"; \
		exit 1; \
	fi
	@echo "--- Calling run script for repository: $(REPO_PATH) ---"
	@$(RUN_SCRIPT) "$(REPO_PATH)"

clean:
	@echo "--- Removing dangling Docker images ---"
	@docker image prune -f