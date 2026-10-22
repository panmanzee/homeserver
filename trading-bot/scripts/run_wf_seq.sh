#!/bin/bash
# run_wf_seq.sh - same as run_wf.sh but one job at a time (parallel runs ran out of RAM)
# 1) default params: full period at 3 fee levels + per-year windows at 3 fee levels
# 2) small grid (8 combos) per-year at 0.25% fee -> used for walk-forward parameter selection
set -e
cd /home/pan/homeserver/trading-bot
OUT=/freqtrade/user_data/backtest_results/wf
mkdir -p user_data/backtest_results/wf
[ "$FRESH" = 1 ] && rm -f user_data/backtest_results/wf/*.jsonl
YEARS="20180401-20190101 20190101-20200101 20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"

run() { # label sma brk atr jobs...
  local label=$1 sma=$2 brk=$3 atr=$4; shift 4
  docker compose run --rm -T -e TS_SMA_LONG=$sma -e TS_BREAKOUT=$brk -e TS_ATR_MULT=$atr \
    --entrypoint python freqtrade /freqtrade/user_data/scripts/bt_worker.py \
    $OUT/$label.jsonl TrendSimple $label "$@" 2>&1 | grep '^done' || true
}

# default (chosen before testing): SMA100, 20-candle breakout, ATR x3
JOBS=""
for f in 0.001 0.0025 0.003; do
  JOBS="$JOBS 20180401-20261021:$f"
  for y in $YEARS; do JOBS="$JOBS $y:$f"; done
done
run default 100 20 3 $JOBS

i=0
for sma in 100 200; do for brk in 20 55; do for atr in 3 4; do
  [ "$sma-$brk-$atr" = "100-20-3" ] && continue
  J=""; for y in $YEARS; do J="$J $y:0.0025"; done
  run "g_${sma}_${brk}_${atr}" $sma $brk $atr $J
done; done; done
wait
echo ALL-DONE
