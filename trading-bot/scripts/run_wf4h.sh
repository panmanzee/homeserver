#!/bin/bash
# run_wf4h.sh - walk-forward grid for the 4h version (same 8 day-based param sets as daily). fee 0.25%.
# Waits for bias checks to finish first (one heavy job at a time, 7 GB host).
cd /home/pan/homeserver/trading-bot
while pgrep -f run_bias_checks.sh >/dev/null; do sleep 15; done
YEARS="20180401-20190101 20190101-20200101 20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
for sma in 100 200; do for brk in 20 55; do for atr in 3 4; do
  [ "$sma-$brk-$atr" = "100-20-3" ] && continue   # = tf_4h (already run)
  J=""; for y in $YEARS; do J="$J $y:0.0025"; done
  bash scripts/run_jobs.sh "h_${sma}_${brk}_${atr}" "-e TS_TF=4h -e TS_SMA_LONG=$sma -e TS_BREAKOUT=$brk -e TS_ATR_MULT=$atr" $J
done; done; done
echo WF4H-DONE
