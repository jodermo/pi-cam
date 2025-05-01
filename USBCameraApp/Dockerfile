# USBCameraApp/Dockerfile

FROM python:3.10-slim

# Ensure stdout/stderr are unbuffered
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for OpenCV *and* audio (ffmpeg + alsa)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      python3-dev \
      portaudio19-dev \
      libportaudio2 \
      ffmpeg \
      alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy & install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and any fallback image you use
COPY app.py fallback_image.png ./

# Expose the stream port
EXPOSE ${STREAM_PORT:-8000}

# Launch the FastAPI app via Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
