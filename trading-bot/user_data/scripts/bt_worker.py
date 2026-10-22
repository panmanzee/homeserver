"""
bt_worker.py - run several freqtrade backtests in ONE python process (inside the container).

usage (inside container):
  python /freqtrade/user_data/scripts/bt_worker.py <out.jsonl> <strategy> <label> <timerange>:<fee> [...]
Strategy parameters come from env TS_* (read when the strategy file is loaded).
Each run appends one JSON line with the main metrics + the trade list.
"""
import json
import logging
import sys

from freqtrade.configuration.config_setup import setup_utils_configuration  # noqa
from freqtrade.enums import RunMode
from freqtrade.optimize.optimize_reports import generate_backtest_stats  # noqa
from freqtrade.commands.optimize_commands import setup_optimize_configuration
from freqtrade.optimize.backtesting import Backtesting

logging.disable(logging.WARNING)

out, strategy, label = sys.argv[1], sys.argv[2], sys.argv[3]
KEEP = ["total_trades", "profit_total", "profit_total_abs", "cagr", "sharpe", "sortino",
        "calmar", "max_drawdown_account", "max_drawdown_abs", "winrate", "wins", "losses",
        "holding_avg_s", "market_change", "starting_balance", "final_balance",
        "backtest_start", "backtest_end", "backtest_days", "profit_factor", "expectancy_ratio"]

for job in sys.argv[4:]:
    timerange, fee = job.split(":")
    args = {
        "config": ["/freqtrade/user_data/config.json"],
        "user_data_dir": "/freqtrade/user_data",
        "strategy": strategy,
        "timerange": timerange,
        "fee": float(fee),
        "export": "none",
    }
    config = setup_optimize_configuration(args, RunMode.BACKTEST)
    bt = Backtesting(config)
    bt.start()
    st = bt.results["strategy"][strategy]
    rec = {"label": label, "strategy": strategy, "timerange": timerange, "fee": float(fee)}
    for k in KEEP:
        rec[k] = st.get(k)
    # daily-wallet based metrics if present
    for k in list(st.keys()):
        if "wallet" in k or k.startswith("max_drawdown"):
            v = st.get(k)
            if isinstance(v, (int, float, str)) or v is None:
                rec[k] = v
    rec["trades"] = [
        {k: t.get(k) for k in ("pair", "open_date", "close_date", "open_rate", "close_rate",
                               "stake_amount", "amount", "profit_ratio", "profit_abs",
                               "trade_duration", "exit_reason", "enter_tag")}
        for t in st.get("trades", [])
    ]
    rec["daily_profit"] = st.get("daily_profit")
    with open(out, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(f"done {label} {timerange} fee={fee} trades={rec['total_trades']} "
          f"profit={rec['profit_total']:.4f} dd={rec['max_drawdown_account']}", flush=True)
