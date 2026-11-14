# The React app (frontend/), built into static/app/
FROM node:24-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py VERSION ./
COPY floorbit/ ./floorbit/
COPY auth/ ./auth/
# COPY data.json .
COPY static/ ./static/
COPY --from=frontend /src/static/app/ ./static/app/
COPY templates/ ./templates/
COPY integrations/ ./integrations/

# Create necessary directories
RUN mkdir -p static/uploads

# Expose port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "-u", "app.py"]
