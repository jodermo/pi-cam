# CameraController/Dockerfile

FROM python:3.10-slim

# Ensure stdout/stderr are unbuffered
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for Postgres client libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy & install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Collect static files into /app/static (served by nginx)
RUN python manage.py collectstatic --noinput

# Expose Django port internally (nginx will proxy to this)
EXPOSE 8001

# Launch Gunicorn
CMD ["gunicorn", "camera_controller.wsgi:application", "--bind", "0.0.0.0:8001"]
