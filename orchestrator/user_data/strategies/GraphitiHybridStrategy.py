# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file

import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy
from freqtrade.strategy import IntParameter, IStrategy, stoploss_from_open
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import logging

logger = logging.getLogger(__name__)


class GraphitiHybridStrategy(IStrategy):
    """
    Graphiti Hybrid Strategy containing news impact analysis.
    """

    INTERFACE_VERSION = 3

    # Minimal ROI
    minimal_roi = {"60": 0.01, "30": 0.02, "0": 0.04}

    # Stoploss
    stoploss = -0.10

    # Trailing stop
    trailing_stop = False

    # Timeframe
    timeframe = "1h"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = False

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Hyperopt parameters
    rsi_period = IntParameter(4, 24, default=14, space="buy")
    rsi_overbought = IntParameter(60, 80, default=70, space="sell")
    rsi_oversold = IntParameter(20, 40, default=30, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        dataframe.loc[
            ((dataframe["rsi"] < self.rsi_oversold.value) & (dataframe["volume"] > 0)), "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        dataframe.loc[
            ((dataframe["rsi"] > self.rsi_overbought.value) & (dataframe["volume"] > 0)),
            "exit_long",
        ] = 1

        return dataframe
