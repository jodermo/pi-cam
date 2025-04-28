Pi USB Camera Controller

Repository Layout

```bash
project-root/
├── USBCameraApp/          # FastAPI service for camera control
├── CameraController/      # Django web UI and controller
├── nginx/                 # Nginx configuration and SSL cert mounts
│   ├── conf.d/            # Nginx vhost config
│   └── certs/             # Mounted Certbot certs directory
├── docker-compose.yml     # Orchestrates all services
└── README.md
```

Environment Variables

Set in docker-compose.yml:

CAMERA_DEVICE (FastAPI): Camera device path (default /dev/video0).

STREAM_PORT (FastAPI): Port inside container (default 8000).

CONTROLLER_URL (FastAPI): Internal URL of Django for webhooks.

CAMERA_API_URL (Django): Base API proxy prefix (/api).

CAMERA_SERVICE_URL (Django): Internal FastAPI URL (http://pi-cam-camera:8000).

DATABASE_URL (Django): Postgres connection string.

DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS (Django settings)


Quick Start

Configure domain: Replace really.dont-use.com in nginx/conf.d/default.conf and environment variables.

Ensure Certbot certs are present under /etc/letsencrypt on the host.

Launch:
```bash
docker-compose up --build -d
```

Initialize Django:

```bash
docker-compose exec pi-cam-controller \
python manage.py migrate --noinput
```

Access:

UI: https:///

FastAPI health: https:///api/health









Docker cleaning: 

```bash
# 1. Stop all running containers
sudo docker stop $(docker ps -q)        # stop any running containers

# 2. Remove all containers
sudo docker rm -f $(docker ps -aq)      # delete every container

# 3. Remove all images
sudo docker rmi -f $(docker images -q)  # delete every image

# 4. Remove all volumes
sudo docker volume rm $(docker volume ls -q)  # delete every volume

# 5. Remove all custom networks
sudo docker network rm $(docker network ls -q | grep -v bridge | grep -v host | grep -v none)

# 6. (Optional) Prune any dangling build cache
sudo docker builder prune -af

# 7. (Optional) Prune everything interactively
sudo docker system prune --all --volumes
```