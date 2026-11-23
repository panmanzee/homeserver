FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends strongswan strongswan-swanctl charon-systemd frr iproute2 iputils-ping procps && rm -rf /var/lib/apt/lists/*
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
