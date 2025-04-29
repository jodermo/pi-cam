#!/usr/bin/env sh
set -e

# Apply migrations and collect static files

echo "Creating migrations for all apps…"
python manage.py makemigrations --noinput

echo "Applying database migrations…"
python manage.py migrate --noinput

echo "Collecting static files…"
python manage.py collectstatic --noinput

# Auto-create Django superuser from .env
if [ -n "$ADMIN_NAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
  echo "Checking for existing superuser '$ADMIN_NAME'…"
  python manage.py shell <<EOF
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.getenv('ADMIN_NAME')
password = os.getenv('ADMIN_PASSWORD')
email    = os.getenv('ADMIN_EMAIL', '')

if not User.objects.filter(username=username).exists():
    print("Creating superuser:", username)
    User.objects.create_superuser(username=username, email=email, password=password)
else:
    print(f"Superuser '{username}' already exists, skipping.")
EOF
else
  echo "ADMIN_NAME or ADMIN_PASSWORD not set; skipping superuser creation."
fi

# Auto-create default CameraSettings if none exist
echo "Ensuring default CameraSettings exist…"
python manage.py shell <<EOF
from controller.models import CameraSettings

if not CameraSettings.objects.exists():
    CameraSettings.objects.create()
    print("Default CameraSettings created.")
else:
    print("CameraSettings already present, skipping.")
EOF

# Auto-create default AppConfigSettings if none exist
echo "Ensuring default AppConfigSettings exist…"
python manage.py shell <<EOF
from controller.models import AppConfigSettings

if not AppConfigSettings.objects.exists():
    AppConfigSettings.objects.create(
        enable_timelapse=True,
        timelapse_interval_minutes=1,
        timelapse_folder='timelapse',
        capture_resolution_width=1280,
        capture_resolution_height=720,
    )
    print("Default AppConfigSettings created.")
else:
    print("AppConfigSettings already present, skipping.")
EOF

# Finally launch the app
exec "$@"
