FROM nginx:alpine

RUN apk add --no-cache openssl

COPY conf.d/ /etc/nginx/conf.d/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
