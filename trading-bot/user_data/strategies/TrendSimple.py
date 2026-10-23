"""
TrendSimple - slow trend-following, spot, long only (paper trading only).

Rules (few parameters, chosen BEFORE any backtest, not optimised):
  entry : close > SMA(sma_long)  AND  close > highest high of the previous `breakout` candles
  exit  : close < SMA(sma_exit)  (exit signal)
          OR chandelier trailing stop: highest close since entry - atr_mult * ATR(14)
          OR hard stoploss -15% (backstop)
  size  : risk 1% of equity per trade. stake = equity * 1% / stop_distance,
          stop_distance = atr_mult * ATR / close (clipped 3%..15%), stake capped at 50% of equity.
  risk  : max_open_trades 2 (config), protections below, daily loss limit 3% (confirm_trade_entry).

Parameters can be overridden with env vars TS_SMA_LONG, TS_BREAKOUT, TS_SMA_EXIT, TS_ATR_MULT
(used only by the walk-forward script). Live/paper uses the defaults.
"""
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


class TrendSimple(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = os.environ.get("TS_TF", "1d")
    _K = {"1d": 1, "4h": 6}.get(timeframe, 1)   # candles per day; periods below are in DAYS x _K

    # --- the only strategy parameters ---
    sma_long = _env_int("TS_SMA_LONG", 100) * _K
    breakout = _env_int("TS_BREAKOUT", 20) * _K
    sma_exit = _env_int("TS_SMA_EXIT", 50) * _K
    atr_mult = _env_float("TS_ATR_MULT", 3.0) * _K ** 0.5   # ATR of 4h bars ~ daily ATR / sqrt(6)
    # experiment-only regime filters (default "none" = live behaviour unchanged)
    regime_filter = os.environ.get("TS_FILTER", "none")   # none | turb | adx
    turb_q = _env_float("TS_TURB_Q", 0.90)

    # --- risk settings ---
    risk_per_trade = _env_float("TS_RISK", 0.01)        # 1% of equity lost if the stop is hit
    max_stake_ratio = _env_float("TS_MAX_STAKE", 0.50)  # never more than 50% of equity in one trade
    min_stop_dist = 0.03
    max_stop_dist = 0.15
    daily_loss_limit = 0.03    # no new entries after -3% realised in the last 24h

    stoploss = -0.15           # hard backstop
    use_custom_stoploss = True
    trailing_stop = False
    minimal_roi = {"0": 100}   # no ROI exits; trend rules decide
    use_exit_signal = True
    exit_profit_only = False
    process_only_new_candles = True
    startup_candle_count = (210 if regime_filter != "turb" else 252 + 365 + 5) * _K

    # TS_PROT=light (v2 full-size bot): drop the two MaxDrawdown locks. They were sized for 1% risk;
    # at full size one normal losing trade trips the 15% lock and it re-fires for a year (reviewer 2026-10-23).
    prot_mode = os.environ.get("TS_PROT", "full")

    @property
    def protections(self):
        if self.prot_mode == "light":
            return [
                {"method": "CooldownPeriod", "stop_duration_candles": 2 * self._K},
                {"method": "StoplossGuard", "lookback_period_candles": 30 * self._K, "trade_limit": 3,
                 "stop_duration_candles": 7 * self._K, "only_per_pair": False},
            ]
        return [
            # pause 2 candles after a trade closes on a pair
            {"method": "CooldownPeriod", "stop_duration_candles": 2 * self._K},
            # 3 stop-losses within 30 days -> pause all trading 7 days
            {"method": "StoplossGuard", "lookback_period_candles": 30 * self._K, "trade_limit": 3,
             "stop_duration_candles": 7 * self._K, "only_per_pair": False},
            # equity drawdown > 15% over the last year of closed trades -> pause 30 days
            {"method": "MaxDrawdown", "lookback_period_candles": 365 * self._K, "trade_limit": 1,
             "stop_duration_candles": 30 * self._K, "max_allowed_drawdown": 0.15,
             "calculation_mode": "equity"},
            # daily loss limit (closed trades): > 3% equity drop within 1 day -> pause 1 day
            {"method": "MaxDrawdown", "lookback_period_candles": 1 * self._K, "trade_limit": 1,
             "stop_duration_candles": 1 * self._K, "max_allowed_drawdown": 0.03,
             "calculation_mode": "equity"},
        ]

    # ------------------------------------------------------------------ indicators
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe
        df["sma_long"] = ta.SMA(df, timeperiod=self.sma_long)
        df["sma_exit"] = ta.SMA(df, timeperiod=self.sma_exit)
        df["sma200"] = ta.SMA(df, timeperiod=200)
        df["sma50"] = ta.SMA(df, timeperiod=50)
        # highest high of the PREVIOUS n candles (shift(1) => no look-ahead)
        df["hh"] = df["high"].rolling(self.breakout).max().shift(1)
        df["atr"] = ta.ATR(df, timeperiod=14 * self._K)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["stop_dist"] = (self.atr_mult * df["atr"] / df["close"]).clip(
            self.min_stop_dist, self.max_stop_dist)
        if self.regime_filter == "turb":
            df = self._add_turbulence(df, metadata)
        if self.regime_filter == "adx":
            # OpenBB-style rule regime: trend if ADX>25 and Choppiness(14)<61.8 (textbook values)
            n = 14
            tr = ta.TRANGE(df)
            rng_ = df["high"].rolling(n).max() - df["low"].rolling(n).min()
            df["chop"] = 100 * np.log10(tr.rolling(n).sum() / rng_) / np.log10(n)
        return df

    def _add_turbulence(self, df: DataFrame, metadata: dict) -> DataFrame:
        """FinRL-style turbulence: Mahalanobis distance of today's BTC+ETH daily returns vs
        the previous 252 days. Threshold = 90% quantile of the PAST 365 turbulence values
        (rolling, shifted 1) -> no look-ahead. Entry blocked when turb > threshold."""
        pairs = self.config.get("exchange", {}).get("pair_whitelist", ["BTC/USDT", "ETH/USDT"])
        rets = {}
        for p in pairs:
            o = df if p == metadata["pair"] else self.dp.get_pair_dataframe(p, self.timeframe)
            if o is None or o.empty:
                continue
            rets[p] = o.set_index("date")["close"].pct_change()
        r = pd.DataFrame(rets).reindex(df["date"]).values
        win = 252
        turb = np.full(len(r), np.nan)
        for i in range(win + 1, len(r)):
            hist = r[i - win:i]
            hist = hist[~np.isnan(hist).any(axis=1)]
            x = r[i]
            if len(hist) < win // 2 or np.isnan(x).any():
                continue
            mu = hist.mean(axis=0)
            cov = np.cov(hist, rowvar=False)
            d = x - mu
            turb[i] = float(d @ np.linalg.pinv(np.atleast_2d(cov)) @ d)
        s = pd.Series(turb, index=df.index)
        df["turb"] = s
        # rolling 365-day window so the value does not depend on how much history is loaded
        df["turb_thr"] = s.rolling(365, min_periods=365).quantile(self.turb_q).shift(1)
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        cond = (
            (dataframe["close"] > dataframe["sma_long"])
            & (dataframe["close"] > dataframe["hh"])
            & (dataframe["volume"] > 0)
        )
        if self.regime_filter == "turb":
            cond &= dataframe["turb"].notna() & dataframe["turb_thr"].notna() & (
                dataframe["turb"] <= dataframe["turb_thr"])
        elif self.regime_filter == "adx":
            cond &= (dataframe["adx"] > 25) & (dataframe["chop"] < 61.8)
        dataframe.loc[cond, ["enter_long", "enter_tag"]] = (1, "breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["sma_exit"], ["exit_long", "exit_tag"]] = (
            1, "below_sma_exit")
        return dataframe

    # ------------------------------------------------------------------ sizing
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df is None or df.empty:
            return 0
        stop_dist = float(df["stop_dist"].iloc[-1])
        if not np.isfinite(stop_dist) or stop_dist <= 0:
            return 0
        equity = self.wallets.get_total_stake_amount()
        stake = equity * self.risk_per_trade / stop_dist
        stake = min(stake, equity * self.max_stake_ratio, max_stake)
        if min_stake and stake < min_stake:
            return 0
        return stake

    # ------------------------------------------------------------------ trailing stop
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float | None:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df is None or df.empty:
            return None
        since = df.loc[df["date"] >= trade.open_date_utc, "close"]
        highest = max(trade.open_rate, float(since.max()) if len(since) else trade.open_rate)
        atr = float(df["atr"].iloc[-1])
        if not np.isfinite(atr):
            return None
        stop_price = highest - self.atr_mult * atr
        if stop_price >= current_rate:
            # price already below the chandelier level -> exit at once (tiny distance)
            return 0.001
        return stoploss_from_absolute(stop_price, current_rate, is_short=False)

    # ------------------------------------------------------------------ daily loss limit
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: str | None,
                            side: str, **kwargs) -> bool:
        """Block new entries if closed trades lost >= 3% of equity in the last 24h.
        Only local DB/wallet reads here (no network calls)."""
        since = current_time - timedelta(days=1)
        closed = Trade.get_trades_proxy(is_open=False, close_date=since)
        pnl = sum((t.close_profit_abs or 0.0) for t in closed)
        equity = self.wallets.get_total_stake_amount()
        if equity > 0 and pnl < 0 and (-pnl) / (equity - pnl) >= self.daily_loss_limit:
            return False
        return True
