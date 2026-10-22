#!/bin/bash
# run_jobs.sh <label> <envflags (quoted)> <jobs...>
# Runs bt_worker in the freqtrade image and RE-RUNS it until every job is in the jsonl.
# Why: the container has mem_limit 768m and the python process grows per backtest,
# so it gets killed after ~4-5 jobs. bt_worker skips finished jobs, so re-running resumes.
cd /home/pan/homeserver/trading-bot
label=$1; envs=$2; shift 2
OUT=/freqtrade/user_data/backtest_results/wf
HOSTOUT=user_data/backtest_results/wf/$label.jsonl
need=$#
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  have=$( [ -f "$HOSTOUT" ] && wc -l < "$HOSTOUT" || echo 0 )
  [ "$have" -ge "$need" ] && break
  docker compose run --rm -T $envs --entrypoint python freqtrade \
    /freqtrade/user_data/scripts/bt_worker.py $OUT/$label.jsonl TrendSimple $label "$@" 2>&1 \
    | grep -E '^done|Error|Traceback' | grep -v cached || true
done
have=$( [ -f "$HOSTOUT" ] && wc -l < "$HOSTOUT" || echo 0 )
echo "jobs $label: $have/$need"
