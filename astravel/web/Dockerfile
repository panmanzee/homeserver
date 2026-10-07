FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security.inc /etc/nginx/conf.d/security.inc
COPY site/ /usr/share/nginx/html/
