# Multi-stage build for Genesis Python Backend/CLI
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for OpenCV and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    libopencv-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-dev \
    libgtk-3-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libv4l-dev \
    libxvidcore-dev \
    libx264-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libopenblas-dev \
    gfortran \
    wget \
    git \
    curl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy and install Python dependencies
# Use Docker-optimized requirements (CPU-only for compatibility)
COPY requirements-docker.txt ./requirements.txt
COPY backend/requirements-docker.txt ./backend_requirements.txt

# Note: Ollama runs as separate service in docker-compose
# Install ollama python client for API communication  
RUN pip install ollama

# Install PaddlePaddle CPU (universal compatibility)
RUN python -m pip install paddlepaddle==3.1.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/

# Install Python dependencies
# Install main requirements first (has more dependencies)
RUN pip install --no-cache-dir -r requirements.txt

# Install backend-specific requirements (may have some overlaps)
RUN pip install --no-cache-dir -r backend_requirements.txt

# Copy project source code
COPY . .

# Set Python path
ENV PYTHONPATH="/app:/app/src:/app/backend"

# Create directories for data persistence
RUN mkdir -p /app/data /app/tmp /app/inputs /app/outputs

# Expose ports
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden)
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
