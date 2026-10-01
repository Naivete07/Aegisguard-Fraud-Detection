# Multi-stage Dockerfile for AegisGuard Scoring Engine & API
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt httpx

# Copy project code
COPY . .

# Ensure models and data directories exist
RUN mkdir -p data/processed data/raw models reports

# Expose FastAPI port
EXPOSE 8000

# Default command starts FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
