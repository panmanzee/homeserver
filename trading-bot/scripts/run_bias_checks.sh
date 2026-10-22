#!/bin/bash
# run_bias_checks.sh - lookahead + recursive analysis for experiment variants (4h, turb, adx)
cd /home/pan/homeserver/trading-bot
mkdir -p results
la() { # name envflags extra-args
  local name=$1 envs=$2; shift 2
  docker compose run --rm -T $envs freqtrade lookahead-analysis --config /freqtrade/user_data/config.json \
    --strategy TrendSimple --timerange 20190101-20261021 "$@" > results/lookahead_$name.txt 2>&1
  grep -E "no bias|bias detected|has_bias|│ TrendSimple" results/lookahead_$name.txt | tail -3
}
la 4h "-e TS_TF=4h" --timeframe 4h
la turb "-e TS_FILTER=turb"
la adx "-e TS_FILTER=adx"
docker compose run --rm -T -e TS_TF=4h freqtrade recursive-analysis --config /freqtrade/user_data/config.json \
  --strategy TrendSimple --timeframe 4h --timerange 20250101-20261021 > results/recursive_4h.txt 2>&1
tail -12 results/recursive_4h.txt
echo BIAS-DONE
