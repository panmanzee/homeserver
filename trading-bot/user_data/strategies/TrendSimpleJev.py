"""
TrendSimpleJev - TrendSimple + Jev regime filter on NEW entries only.

A base entry signal is kept only if Jev says the regime is TREND with confidence >= 0.7.
Jev is asked at most once per pair per closed candle, and ONLY on candles where the base
signal fires (cheap). Calls happen in populate_entry_trend (once per new candle), never in
confirm_trade_entry. Error / timeout / low confidence => no entry (fail safe).
Exits and stops are exactly the same as TrendSimple.

Backtest: only candles on/after env JEV_START (YYYY-MM-DD) are sent to Jev
(earlier signal candles are dropped, so run the A/B with --timerange starting at JEV_START).
Live/dry-run: only the last closed candle is evaluated.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from pandas import DataFrame

sys.path.insert(0, str(Path(__file__).parent))
import jev_filter  # noqa: E402
from TrendSimple import TrendSimple  # noqa: E402

from freqtrade.enums import RunMode  # noqa: E402


class TrendSimpleJev(TrendSimple):

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = super().populate_indicators(dataframe, metadata)
        c = df["close"]
        df["ret5"] = c.pct_change(5)
        df["ret20"] = c.pct_change(20)
        df["ret60"] = c.pct_change(60)
        df["sma50_slope"] = df["sma50"].pct_change(20)
        df["vol20"] = c.pct_change().rolling(20).std() * (365 ** 0.5)
        df["up20"] = (c.diff() > 0).astype(float).rolling(20).sum()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = super().populate_entry_trend(dataframe, metadata)
        pair = metadata["pair"]
        sig = df["enter_long"] == 1
        live = self.dp is not None and self.dp.runmode in (RunMode.DRY_RUN, RunMode.LIVE)
        if live:
            # only the last closed candle matters in live/paper trading
            idx = [df.index[-1]] if len(df) and sig.iloc[-1] else []
            # every earlier candle: no signal (they are history anyway)
            keep = pd.Series(False, index=df.index)
        else:
            start = pd.Timestamp(os.environ.get("JEV_START", "2100-01-01"), tz="UTC")
            idx = list(df.index[sig & (df["date"] >= start)])
            keep = pd.Series(False, index=df.index)

        def ask(i):
            row = df.loc[i]
            return i, jev_filter.regime(pair, str(row["date"].date()), jev_filter.features(row))

        if idx:
            workers = 1 if live else 4
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for i, ans in ex.map(ask, idx):
                    keep.loc[i] = bool(ans.get("allow"))
                    df.loc[i, "jev_choice"] = ans.get("choice")
                    df.loc[i, "jev_conf"] = ans.get("confidence")
        df.loc[sig & ~keep, ["enter_long", "enter_tag"]] = (0, None)
        df.loc[sig & keep, "enter_tag"] = "breakout_jev"
        return df
