# pi-cam

A Docker-powered Raspberry Pi camera solution that lets you:

- **Stream & control** a USB or CSI camera via a simple web UI  
- **Capture photos**, record video, and schedule timelapse sequences  
- **Browse, download, and delete** media in an integrated gallery  
- **Secure** your setup with Let’s Encrypt SSL and environment-driven configuration  
- **Persist** data in PostgreSQL and store media on the host via Docker volumes  

Everything runs in containers—just configure your `.env`, plug in a camera, and deploy with `docker-compose up -d`.


## Quick Start

1.  **Clone the repo**  
    ```bash
    git clone https://github.com/jodermo/pi-cam.git
    cd pi-cam
    ```

2. **Configure** 
    - Copy .env.example to .env and edit your domain, database credentials, camera device, etc.
    - (If using HTTPS) obtain certificates with Certbot and set SSL_ACTIVE=true.

3. **Build & run**
    ```bash
    docker-compose up -d --build
    ```

4. **Configure** 
    - Camera stream & controls: http://<YOUR_DOMAIN_OR_PI_IP>/
    - Timelapse & media gallery: via the top-nav links in the web UI.

5. **Configure** 
    ```bash
    docker-compose logs -f        # view logs
    docker-compose down           # stop
    docker-compose up -d          # restart in background
    ```


## Configutration

###### Device Mapping in `docker-compose.yml`

The `devices` section in the `pi-cam-camera` service grants the container access to your host’s video device node. By default it looks like this:

```yaml
services:
  pi-cam-camera:
    # …
    devices:
      - "/dev/video0:/dev/video0"
    # …
```

#### Environment Variables ([.env](/.env))

| Variable                | Example Value                                              | Description                                                                                                                                           |
|-------------------------|------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| `DOMAIN`                | `your-domain.com`                                          | The public hostname where your app is served. Used for building absolute URLs, redirects, and SSL certificate domain.                                  |
| `SSL_ACTIVE`            | `false`                                                    | Enable HTTPS when `true`. If `false`, the app will only serve HTTP.                                                                                   |
| `SSL_CERTIFICATE`       | `/etc/letsencrypt/live/your-domain.com/fullchain.pem`      | Path to your SSL/TLS certificate bundle (PEM). Only used if `SSL_ACTIVE=true`.                                                                        |
| `SSL_CERTIFICATE_KEY`   | `/etc/letsencrypt/live/your-domain.com/privkey.pem`        | Path to the private key matching your certificate. Only used if `SSL_ACTIVE=true`.                                                                    |
| `ADMIN_NAME`            | `Admin`                                                    | Username for the built-in administrative account. Change for improved security.                                                                        |
| `ADMIN_PASSWORD`        | `Password`                                                 | Password for the admin account. **Override with a strong secret in production.**                                                                       |
| `POSTGRES_DB`           | `camdb`                                                    | Name of the PostgreSQL database the Django app will connect to.                                                                                        |
| `POSTGRES_USER`         | `camuser`                                                  | PostgreSQL role used by the application.                                                                                                              |
| `POSTGRES_PASSWORD`     | `securepass`                                               | Password for the Postgres user. **Use a strong password**; do not commit to version control.                                                           |
| `CAMERA_LOCATIONS`      | `/dev/video0,0,http://localhost:3322`                      | Comma-separated camera sources in the form `device,index,stream_url`.                                                                                  |
| `DJANGO_DEBUG`          | `true`                                                     | Django debug mode. Set to `false` in production to disable detailed error pages and enable optimizations.                                               |


<br>
<br>

# Some Helpfull Stuff:

### Certbot

#### Install Certbot for SSL Certificates


1. Install snapd and reboot:

    ```bash
    sudo apt update
    sudo apt install -y snapd
    sudo reboot
    ```


2. Ensure snap’s classic support:

    ```bash
    sudo snap install core; sudo snap refresh core
    ```

3. Install Certbot:

    ```bash
    sudo snap install certbot --classic
    ```

4. Verify:

    ```bash
    certbot --version
    # e.g. Certbot 2.x.x
    ```

5. Run Certbot as usual:

    ```bash
    sudo certbot certonly --standalone -d your.domain.com
    ```

<br>
<br>


#### Create SSL Certificate for "your-domain" (replace your-domain)

```bash
sudo certbot certonly --standalone -d your-domain -d www.your-domain.com
```

<br>
<br>
<br>

### Docker and Docker-Compose

#### Install Docker and Docker-Compose:


1. Update your package index and install prerequisites:

    ```bash
    sudo apt-get update 
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    ```


2. Add Docker’s official GPG key and repository:

    ```bash
    sudo apt-get update 
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    ```

3. Install Docker Engine & CLI:

    ```bash
    sudo apt-get update 
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    ```

4. (Optional) Let your “pi” user run Docker without sudo:

    ```bash
    sudo usermod -aG docker $USER
    # then log out & back in (or reboot)
    ```

5. Verify Docker is working:

    ```bash
    docker run --rm hello-world
    ```


<br>
<br>

### Docker cleaning: 

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