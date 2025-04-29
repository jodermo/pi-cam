#!/usr/bin/env bash
set -euo pipefail

#-------------------------------------------------------------------------------
# Docker entrypoint: apply migrations, collect static, create defaults, then launch
#-------------------------------------------------------------------------------

# Function: wait for database to be ready
wait_for_db() {
  local host port
  host=$(python - <<'PYCODE'
import os; print(os.getenv('DB_HOST', 'localhost'))
PYCODE
  )
  port=$(python - <<'PYCODE'
import os; print(os.getenv('DB_PORT', '5432'))
PYCODE
  )
  echo "Waiting for database at $host:$port..."
  until pg_isready -h "$host" -p "$port" >/dev/null 2>&1; do
    printf '.'
    sleep 1
  done
  echo "Database is up"
}

# Wait for DB
wait_for_db

#-------------------------------------------------------------------------------
# Django management commands
#-------------------------------------------------------------------------------
echo "Making migrations…"
python manage.py makemigrations --noinput

echo "Applying migrations…"
python manage.py migrate --noinput

echo "Collecting static files…"
python manage.py collectstatic --noinput

#-------------------------------------------------------------------------------
# Helper: run a Django shell snippet
run_shell() {
  python manage.py shell <<EOF
$1
EOF
}

#-------------------------------------------------------------------------------
# Create superuser if credentials provided
#-------------------------------------------------------------------------------
if [[ -n "${ADMIN_NAME-}" && -n "${ADMIN_PASSWORD-}" ]]; then
  echo "Ensuring superuser '$ADMIN_NAME' exists…"
  run_shell "import os; from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username=os.getenv('ADMIN_NAME')).exists():
    User.objects.create_superuser(
        username=os.getenv('ADMIN_NAME'),
        email=os.getenv('ADMIN_EMAIL', ''),
        password=os.getenv('ADMIN_PASSWORD')
    ) and print('Superuser created.')
else:
    print('Superuser exists, skipping.')"
else
  echo "ADMIN_NAME or ADMIN_PASSWORD not set; skipping superuser creation."
fi

#-------------------------------------------------------------------------------
# Create default CameraSettings and AppConfigSettings if absent
#-------------------------------------------------------------------------------

echo "Ensuring default CameraSettings…"
run_shell "from controller.models import CameraSettings
CameraSettings.objects.get_or_create(id=1)
print('CameraSettings OK')"

echo "Ensuring default AppConfigSettings…"
run_shell "from controller.models import AppConfigSettings
AppConfigSettings.objects.get_or_create(
    id=1,
    defaults={
        'enable_timelapse': True,
        'timelapse_interval_minutes': 1,
        'timelapse_folder': 'timelapse',
        'capture_resolution_width': 1280,
        'capture_resolution_height': 720,
    }
)
print('AppConfigSettings OK')"

#-------------------------------------------------------------------------------
# Exec the container command (e.g. start server)
#-------------------------------------------------------------------------------
exec "$@"
