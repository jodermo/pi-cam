#!/bin/sh
# nginx/entrypoint.sh
set -e

# Pick which config to render
if [ "$SSL_ACTIVE" = "true" ]; then
  echo "SSL active — rendering HTTPS config"
  envsubst '$DOMAIN $SSL_CERTIFICATE $SSL_CERTIFICATE_KEY' \
    < /etc/nginx/conf.d/default.conf.https.template \
    > /etc/nginx/conf.d/default.conf
else
  echo "SSL inactive — rendering HTTP-only config"
  envsubst '$DOMAIN' \
    < /etc/nginx/conf.d/default.conf.http.template \
    > /etc/nginx/conf.d/default.conf
fi

# Start nginx
exec "$@"
