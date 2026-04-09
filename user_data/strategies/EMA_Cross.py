"""
EMA Crossover Strategy (1h Futures)
Fast EMA(9) crossing slow EMA(21) for trend entry.
"""
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class EMA_Cross(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 30

    stoploss = -0.035
    minimal_roi = {
        "0": 0.025,
        "60": 0.01,
        "120": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=21)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "ema9_above_ema21"

        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "ema9_below_ema21"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_fast"] < dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "ema_cross_down"

        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "ema_cross_up"

        return dataframe
