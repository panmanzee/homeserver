#!/bin/bash
# run_e4.sh - E4 position size test (signal unchanged). fee 0.25%, full + per year.
cd /home/pan/homeserver/trading-bot
YEARS="20180401-20190101 20190101-20200101 20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
J="20180401-20261021:0.0025"; for y in $YEARS; do J="$J $y:0.0025"; done
bash scripts/run_jobs.sh s_r2_c50 "-e TS_RISK=0.02 -e TS_MAX_STAKE=0.5" $J
bash scripts/run_jobs.sh s_r3_c100 "-e TS_RISK=0.03 -e TS_MAX_STAKE=1.0" $J
echo E4-DONE
