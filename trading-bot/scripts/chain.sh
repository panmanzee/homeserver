#!/bin/bash
# chain.sh - wait for the walk-forward run to finish, then run the filter experiment.
cd /home/pan/homeserver/trading-bot
while pgrep -f run_wf_seq.sh >/dev/null; do sleep 20; done
bash scripts/run_filters.sh
