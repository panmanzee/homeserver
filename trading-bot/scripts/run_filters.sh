#!/bin/bash
# run_filters.sh - experiment E2: regime filters (no LLM) vs plain TrendSimple.
#   f_none = TrendSimple default, f_turb = FinRL turbulence filter, f_adx = ADX>25 & Chop<61.8
# Same windows for all: 2020..2026 years + full 2020-01-01..2026-10-21, fee 0.1% and 0.25%.
# (2020 start because the turbulence filter needs ~2 years of warm-up data.)
# Resumable: bt_worker skips jobs already in the jsonl.
cd /home/pan/homeserver/trading-bot
OUT=/freqtrade/user_data/backtest_results/wf
YEARS="20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
for filt in none turb adx; do
  J=""
  for f in 0.0025 0.001; do
    J="$J 20200101-20261021:$f"
    for y in $YEARS; do J="$J $y:$f"; done
  done
  docker compose run --rm -T -e TS_FILTER=$filt --entrypoint python freqtrade \
    /freqtrade/user_data/scripts/bt_worker.py $OUT/f_$filt.jsonl TrendSimple f_$filt $J 2>&1 | grep -E '^done|Error|Traceback' || true
done
echo FILTERS-DONE
