#!/bin/bash
# run_e5.sh - E5: same rules on 4h candles (periods in days x6, ATR mult x sqrt(6)). fee 0.25%.
cd /home/pan/homeserver/trading-bot
YEARS="20180401-20190101 20190101-20200101 20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
J="20180401-20261021:0.0025 20180401-20261021:0.001"; for y in $YEARS; do J="$J $y:0.0025"; done
bash scripts/run_jobs.sh tf_4h "-e TS_TF=4h" $J
echo E5-DONE
