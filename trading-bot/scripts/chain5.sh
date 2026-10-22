#!/bin/bash
cd /home/pan/homeserver/trading-bot
while pgrep -f run_e4.sh >/dev/null; do sleep 15; done
bash scripts/run_e5.sh
