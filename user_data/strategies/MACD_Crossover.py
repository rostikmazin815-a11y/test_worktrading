"""
MACD Crossover Strategy (1h Futures)
Classic MACD signal line crossover for trend following.
"""
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class MACD_Crossover(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 50

    stoploss = -0.04
    minimal_roi = {
        "0": 0.03,
        "45": 0.01,
        "90": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1))
                & (dataframe["macdhist"] > 0)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1))
                & (dataframe["macdhist"] > 0)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "macd_bull_cross"

        dataframe.loc[
            (
                (dataframe["macd"] < dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1))
                & (dataframe["macdhist"] < 0)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["macd"] < dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1))
                & (dataframe["macdhist"] < 0)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "macd_bear_cross"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["macd"] < dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["macd"] < dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "macd_cross_down"

        dataframe.loc[
            (
                (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["macd"] > dataframe["macdsignal"])
                & (dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "macd_cross_up"

        return dataframe
