#!/bin/bash
# run_e5c.sh - add the 0.3% fee run (0.25% + slippage) for the 4h candidate, then re-analyse
cd /home/pan/homeserver/trading-bot
YEARS="20180401-20190101 20190101-20200101 20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
J="20180401-20261021:0.0025 20180401-20261021:0.001 20180401-20261021:0.003 20200101-20261021:0.0025"; for y in $YEARS; do J="$J $y:0.0025"; done
bash scripts/run_jobs.sh tf_4h "-e TS_TF=4h" $J
docker compose run --rm -T --entrypoint python freqtrade /freqtrade/user_data/scripts/analyze.py > /dev/null 2>/home/pan/analyze.err
grep -A5 Traceback /home/pan/analyze.err | tail -6
echo E5C-DONE
