#!/bin/bash
# run_jev.sh - E3 rerun: TrendSimpleJev into jsonl so analyze.py can score it like the others.
# Uses the cached Jev answers from the first run (jev_cache_backtest.json); max 300 new calls.
# JEV_START is required: without it nothing is sent to Jev and every entry is blocked (0 trades).
# To redo: rm user_data/backtest_results/wf/jev.jsonl first (run_jobs.sh resumes otherwise).
cd /home/pan/homeserver/trading-bot
YEARS="20180401-20190101 20190101-20200101 20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
J="20180401-20261021:0.0025 20180401-20261021:0.001 20180401-20261021:0.003"; for y in $YEARS; do J="$J $y:0.0025"; done
STRAT=TrendSimpleJev bash scripts/run_jobs.sh jev "-e JEV_START=2018-01-01 -e JEV_CACHE=/freqtrade/user_data/jev_cache_backtest.json -e JEV_MAX_CALLS=300" $J
echo JEV-DONE
