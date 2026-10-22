#!/bin/bash
# runs inside 101: create .env with random creds if missing (never printed)
set -e
cd /home/pan/homeserver/trading-bot
if [ ! -f .env ]; then
  umask 077
  {
    echo "FREQTRADE__API_SERVER__USERNAME=ft_$(openssl rand -hex 4)"
    echo "FREQTRADE__API_SERVER__PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' )"
    echo "FREQTRADE__API_SERVER__JWT_SECRET_KEY=$(openssl rand -hex 32)"
    echo "FREQTRADE__API_SERVER__WS_TOKEN=$(openssl rand -hex 24)"
    echo "BOT_STRATEGY=TrendSimple"
  } > .env
fi
chmod 600 .env; chown pan:pan .env
echo env-ok
