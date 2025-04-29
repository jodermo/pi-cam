## CameraController/Dockerfile

FROM python:3.10-slim

# Ensure stdout/stderr are unbuffered
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for Postgres client libraries
# and OpenCV (headless) support
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      libgl1 \
      libglib2.0-0 \
      libsm6 \
      libxext6 \
      ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy & install Python dependencies
COPY requirements.txt .
# Ensure opencv-python-headless is present
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir opencv-python-headless

# Copy the rest of the application
COPY . .

# Copy and register our entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Django port internally (nginx will proxy to this)
EXPOSE 8001

# Use the entrypoint to run migrations, collectstatic, then exec CMD
ENTRYPOINT ["/entrypoint.sh"]

# Default command: launch Gunicorn
CMD ["gunicorn", "camera_controller.wsgi:application", "--bind", "0.0.0.0:8001"]