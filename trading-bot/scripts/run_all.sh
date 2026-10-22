#!/bin/bash
# run_all.sh - finish walk-forward grid + E2 filter experiment (resumable, one job at a time)
cd /home/pan/homeserver/trading-bot
YEARS="20180401-20190101 20190101-20200101 20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
J=""
for f in 0.001 0.0025 0.003; do
  J="$J 20180401-20261021:$f"; for y in $YEARS; do J="$J $y:$f"; done
done
bash scripts/run_jobs.sh default "-e TS_SMA_LONG=100 -e TS_BREAKOUT=20 -e TS_ATR_MULT=3" $J
for sma in 100 200; do for brk in 20 55; do for atr in 3 4; do
  [ "$sma-$brk-$atr" = "100-20-3" ] && continue
  J=""; for y in $YEARS; do J="$J $y:0.0025"; done
  bash scripts/run_jobs.sh "g_${sma}_${brk}_${atr}" "-e TS_SMA_LONG=$sma -e TS_BREAKOUT=$brk -e TS_ATR_MULT=$atr" $J
done; done; done
Y2="20200101-20210101 20210101-20220101 20220101-20230101 20230101-20240101 20240101-20250101 20250101-20260101 20260101-20261021"
for filt in none turb adx; do
  J=""; for f in 0.0025 0.001; do J="$J 20200101-20261021:$f"; for y in $Y2; do J="$J $y:$f"; done; done
  bash scripts/run_jobs.sh "f_$filt" "-e TS_FILTER=$filt" $J
done
echo ALL-RUNS-DONE
