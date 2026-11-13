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
COPY app.py settings_store.py ./
COPY auth/ ./auth/
# COPY data.json .
COPY static/ ./static/
COPY templates/ ./templates/
COPY integrations/ ./integrations/
COPY seat_traffic.py ./

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
