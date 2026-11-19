"""BtcTrendL1 - 4h EMA20/100 cross + 4h EMA200 slope filter, vol targeting (paper). Long only (short signals -> flat).
Research: /root/trading-research E_final.md (O1 sizing: min(1, 0.40/30d ann. vol), resize on >20% change).
Beda dari research: ราคา fill = open ของแท่ง 1h ถัดไป, ขนาดคงที่ (ไม่ rebalance ทุกแท่ง), funding จริงจาก freqtrade."""
import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class BtcTrendL1(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "1h"
    startup_candle_count = 2400
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    minimal_roi = {"0": 100}
    stoploss = -0.99
    position_adjustment_enable = True
    max_entry_position_adjustment = -1

    vol_target = 0.40
    band = 0.20

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        return 1.0

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        d = df.set_index("date")
        c = d["close"]
        g = c.resample("4h").last()
        g = g[c.resample("4h").count() == 4]          # เฉพาะแท่ง 4h ที่ปิดครบ
        e200 = g.ewm(span=200, adjust=False).mean()
        slope = e200 - e200.shift(5)
        f = g.ewm(span=20, adjust=False).mean()
        s = g.ewm(span=100, adjust=False).mean()
        p = np.where((f > s) & (slope > 0), 1.0, np.where((f < s) & (slope < 0), -1.0, 0.0))
        p[np.isnan(slope.values)] = 0.0
        p[:200] = 0.0
        sig = pd.Series(np.nan, index=d.index)
        sig.loc[g.index + pd.Timedelta(hours=3)] = p   # ตัดสินที่ปิดแท่ง 1h ที่ 4 ของแท่ง 4h
        df["sig"] = sig.ffill().fillna(0.0).values
        df["vol30"] = c.pct_change().rolling(720).std().values * np.sqrt(8760)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[df["sig"] == 1, ["enter_long", "enter_tag"]] = (1, "t2_long")
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[df["sig"] < 1, "exit_long"] = 1
        return df

    def _want(self, pair):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty:
            return 1.0
        v = df["vol30"].iloc[-1]
        return 1.0 if (pd.isna(v) or v <= 0) else min(1.0, self.vol_target / v)

    def _equity(self):
        return self.wallets.get_total_stake_amount()

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side, **kwargs):
        stake = self._equity() * self._want(pair)
        return max(min_stake or 0.0, min(stake, max_stake))

    def order_filled(self, pair, trade, order, current_time, **kwargs):
        if order.ft_order_side == trade.entry_side and trade.get_custom_data("s") is None:
            trade.set_custom_data("s", self._want(pair))

    def adjust_trade_position(self, trade, current_time, current_rate, current_profit, min_stake, max_stake, current_entry_rate, current_exit_rate, current_entry_profit, current_exit_profit, **kwargs):
        if trade.has_open_orders:
            return None
        want = self._want(trade.pair)
        cur = trade.get_custom_data("s")
        if cur is None:
            trade.set_custom_data("s", want)
            return None
        if abs(want - cur) / cur <= self.band:
            return None
        delta = want * self._equity() - trade.amount * current_rate
        if abs(delta) < (min_stake or 0.0) * 1.05:
            return None
        trade.set_custom_data("s", want)
        return delta
