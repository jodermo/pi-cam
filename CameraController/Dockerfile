# ── builder stage ──
FROM python:3.10-slim AS builder
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 1) System dependencies for psycopg2, ffmpeg, opencv, etc.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential libpq-dev libgl1 libglib2.0-0 libsm6 libxext6 ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# 2) Install Python deps into the container’s default site-packages
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 3) Copy your code & bake migrations + collectstatic
COPY . .
RUN python manage.py makemigrations --noinput \
 && python manage.py migrate       --noinput \
 && python manage.py collectstatic --noinput

# ── runtime stage ──
FROM python:3.10-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 4) Only install system runtime deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpq-dev libgl1 libglib2.0-0 libsm6 libxext6 ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# 5) Copy over Python site-packages built in the builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin            /usr/local/bin

# 6) Copy the baked app (including migrations & static)
COPY --from=builder /app /app

# 7) Entrypoint to apply any new migrations & collectstatic at runtime
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8001
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "camera_controller.wsgi:application", "--bind", "0.0.0.0:8001"]
