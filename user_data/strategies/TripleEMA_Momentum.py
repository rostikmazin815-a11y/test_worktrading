"""
Triple EMA Momentum Strategy (1h Futures)
EMA(8/21/55) alignment with momentum confirmation.
"""
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class TripleEMA_Momentum(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 60

    stoploss = -0.04
    minimal_roi = {
        "0": 0.03,
        "60": 0.01,
        "120": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_8"] = ta.EMA(dataframe, timeperiod=8)
        dataframe["ema_21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_55"] = ta.EMA(dataframe, timeperiod=55)
        dataframe["mom"] = ta.MOM(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_8"] > dataframe["ema_21"])
                & (dataframe["ema_21"] > dataframe["ema_55"])
                & (dataframe["mom"] > 0)
                & (dataframe["mom"].shift(1) <= 0)  # Momentum crosses zero
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_8"] > dataframe["ema_21"])
                & (dataframe["ema_21"] > dataframe["ema_55"])
                & (dataframe["mom"] > 0)
                & (dataframe["mom"].shift(1) <= 0)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "triple_ema_momentum_up"

        dataframe.loc[
            (
                (dataframe["ema_8"] < dataframe["ema_21"])
                & (dataframe["ema_21"] < dataframe["ema_55"])
                & (dataframe["mom"] < 0)
                & (dataframe["mom"].shift(1) >= 0)  # Momentum crosses zero
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_8"] < dataframe["ema_21"])
                & (dataframe["ema_21"] < dataframe["ema_55"])
                & (dataframe["mom"] < 0)
                & (dataframe["mom"].shift(1) >= 0)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "triple_ema_momentum_down"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_8"] < dataframe["ema_21"])
                & (dataframe["ema_8"].shift(1) >= dataframe["ema_21"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_8"] < dataframe["ema_21"])
                & (dataframe["ema_8"].shift(1) >= dataframe["ema_21"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "ema8_cross_down_ema21"

        dataframe.loc[
            (
                (dataframe["ema_8"] > dataframe["ema_21"])
                & (dataframe["ema_8"].shift(1) <= dataframe["ema_21"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["ema_8"] > dataframe["ema_21"])
                & (dataframe["ema_8"].shift(1) <= dataframe["ema_21"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "ema8_cross_up_ema21"

        return dataframe
