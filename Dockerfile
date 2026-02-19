# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (backend + data pipeline only, frontend deployed separately)
COPY src/__init__.py ./src/
COPY src/apps/__init__.py ./src/apps/
COPY src/apps/backend/ ./src/apps/backend/
COPY src/apps/data_pipeline/ ./src/apps/data_pipeline/

# Expose port 8000 for FastAPI
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["uvicorn", "src.apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
