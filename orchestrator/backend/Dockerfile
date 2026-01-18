FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
COPY orchestrator/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend package
COPY orchestrator/backend/ ./backend/

# Copy config from ROOT of project (build context is parent of orchestrator/)
COPY config.yml ./config.yml

# Copy launcher script
COPY orchestrator/run_orchestrator.py ./run_orchestrator.py

# Expose port
EXPOSE 8080

# Run via launcher
CMD ["python", "run_orchestrator.py"]
