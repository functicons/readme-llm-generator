# Use a lightweight Python base image 
FROM python:3.11-slim

# Set the working directory inside the container 
WORKDIR /app

# Copy the requirements file and install dependencies 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code into the container 
COPY src/ .

# Define the entrypoint to execute the script 
# The script will analyze the repository mounted at /app/repo
ENTRYPOINT ["python", "generate_readme_llm.py", "/app/repo"]