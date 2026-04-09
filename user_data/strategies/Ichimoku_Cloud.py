"""
Ichimoku Cloud Strategy (1h Futures)
Tenkan/Kijun cross with cloud confirmation for trend trading.
"""
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class Ichimoku_Cloud(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 80

    stoploss = -0.05
    minimal_roi = {
        "0": 0.04,
        "120": 0.01,
        "240": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    @staticmethod
    def _midpoint(dataframe: DataFrame, period: int) -> "Series":
        return (
            dataframe["high"].rolling(window=period).max()
            + dataframe["low"].rolling(window=period).min()
        ) / 2

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Tenkan-sen (Conversion Line) - 9 period
        dataframe["tenkan"] = self._midpoint(dataframe, 9)
        # Kijun-sen (Base Line) - 26 period
        dataframe["kijun"] = self._midpoint(dataframe, 26)
        # Senkou Span A (Leading Span A) - displaced 26 periods ahead
        dataframe["senkou_a"] = ((dataframe["tenkan"] + dataframe["kijun"]) / 2).shift(26)
        # Senkou Span B (Leading Span B) - 52 period midpoint, displaced 26 periods ahead
        dataframe["senkou_b"] = self._midpoint(dataframe, 52).shift(26)
        # Cloud top and bottom
        dataframe["cloud_top"] = dataframe[["senkou_a", "senkou_b"]].max(axis=1)
        dataframe["cloud_bottom"] = dataframe[["senkou_a", "senkou_b"]].min(axis=1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["tenkan"] > dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) <= dataframe["kijun"].shift(1))
                & (dataframe["close"] > dataframe["cloud_top"])
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["tenkan"] > dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) <= dataframe["kijun"].shift(1))
                & (dataframe["close"] > dataframe["cloud_top"])
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "ichimoku_cloud_breakout_long"

        dataframe.loc[
            (
                (dataframe["tenkan"] < dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) >= dataframe["kijun"].shift(1))
                & (dataframe["close"] < dataframe["cloud_bottom"])
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["tenkan"] < dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) >= dataframe["kijun"].shift(1))
                & (dataframe["close"] < dataframe["cloud_bottom"])
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "ichimoku_cloud_breakout_short"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["tenkan"] < dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) >= dataframe["kijun"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["tenkan"] < dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) >= dataframe["kijun"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "ichimoku_tenkan_below_kijun"

        dataframe.loc[
            (
                (dataframe["tenkan"] > dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) <= dataframe["kijun"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["tenkan"] > dataframe["kijun"])
                & (dataframe["tenkan"].shift(1) <= dataframe["kijun"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "ichimoku_tenkan_above_kijun"

        return dataframe
