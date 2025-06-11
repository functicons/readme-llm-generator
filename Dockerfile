# Use a lightweight Python base image 
FROM python:3.11-slim

# Set the working directory inside the container 
WORKDIR /app

# Copy the requirements file and install dependencies 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code, tests, and scripts
COPY src/ /app/src/
COPY tests/ /app/tests/
COPY scripts/ /app/scripts/

# Make scripts executable
RUN chmod +x /app/scripts/*.sh

# Define the entrypoint to execute the script 
# The script will analyze the repository mounted at /app/repo
# ENTRYPOINT ["python", "/app/src/generate_readme_llm.py", "/app/repo"]