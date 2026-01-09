"""
GraphitiHybridStrategy - AI-Powered Trading Strategy

Combines traditional technical analysis (RSI) with AI-powered news analysis
and shared memory from Graphiti to make informed trading decisions.

INSTALLATION:
Copy this file to: user_data/strategies/GraphitiHybridStrategy.py
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from freqtrade.persistence import Trade

# Import our custom AI components
import sys
from pathlib import Path

# Add orchestrator backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "orchestrator" / "backend"))

from config_parser import get_config
from graphiti_client import GraphitiClient
from perplexica_client import PerplexicaClient
from llm_client import LLMClient, LLMMessage

logger = logging.getLogger(__name__)


class GraphitiHybridStrategy(IStrategy):
    """
    Hybrid strategy combining:
    1. Technical Analysis (RSI)
    2. AI News Analysis (via Perplexica)
    3. Shared Memory (via Graphiti)
    """

    # Strategy metadata
    INTERFACE_VERSION = 3

    # Minimal ROI configuration
    minimal_roi = {
        "0": 0.10,  # 10% profit target
        "30": 0.05,  # 5% after 30 minutes
        "60": 0.02,  # 2% after 1 hour
    }

    # Stoploss
    stoploss = -0.05  # -5% default, will be overridden by config

    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    # Optimal timeframe
    timeframe = "15m"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Strategy parameters (can be optimized via hyperopt)
    rsi_period = IntParameter(7, 21, default=14, space="buy")
    rsi_oversold = IntParameter(20, 35, default=30, space="buy")
    rsi_overbought = IntParameter(65, 80, default=70, space="sell")

    # AI parameters
    min_impact_score = DecimalParameter(0.1, 0.8, default=0.3, decimals=2, space="buy")
    news_check_interval = IntParameter(1800, 7200, default=3600, space="buy")  # seconds

    # Internal state
    _last_news_check: Dict[str, datetime] = {}
    _news_cache: Dict[str, Any] = {}
    _config = None
    _graphiti_client: Optional[GraphitiClient] = None
    _perplexica_client: Optional[PerplexicaClient] = None
    _llm_client: Optional[LLMClient] = None

    def __init__(self, config: dict) -> None:
        super().__init__(config)

        # Load global config
        try:
            self._config = get_config()
            logger.info("GraphitiHybridStrategy: Configuration loaded successfully")

            # Initialize AI clients
            self._init_ai_clients()

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            logger.warning("Running in degraded mode (technical analysis only)")

    def _init_ai_clients(self):
        """Initialize AI service clients"""
        try:
            # Graphiti client
            graphiti_config = self._config.get_service("graphiti")
            self._graphiti_client = GraphitiClient(
                url=graphiti_config.url, token=graphiti_config.token
            )

            # Perplexica client
            perplexica_config = self._config.get_service("perplexica")
            self._perplexica_client = PerplexicaClient(
                url=perplexica_config.url, api_key=perplexica_config.api_key
            )

            # LLM client
            primary_model = self._config.get_model("primary_analysis")
            fallback_model_config = self._config.get_fallback_model()

            fallback_dict = None
            if fallback_model_config:
                fallback_dict = {
                    "model": fallback_model_config.model,
                    "api_base": fallback_model_config.api_base,
                    "api_key": fallback_model_config.api_key,
                }

            self._llm_client = LLMClient(
                model=primary_model.model,
                api_base=primary_model.api_base,
                api_key=primary_model.api_key,
                fallback_model=fallback_dict,
            )

            logger.info("All AI clients initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize AI clients: {e}")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Add technical indicators to dataframe
        """
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)

        # Additional indicators for context
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=12)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=26)

        # Volume
        dataframe["volume_mean"] = dataframe["volume"].rolling(window=20).mean()

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate entry (buy) signals

        Entry conditions:
        1. RSI is oversold
        2. Volume above average
        """
        dataframe["enter_long"] = 0

        conditions = [
            (dataframe["rsi"] < self.rsi_oversold.value),
            (dataframe["volume"] > dataframe["volume_mean"]),
        ]

        # Combine conditions
        if len(conditions) > 0:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate exit (sell) signals

        Exit conditions:
        1. RSI is overbought
        """
        dataframe["exit_long"] = 0

        conditions = [(dataframe["rsi"] > self.rsi_overbought.value)]

        if len(conditions) > 0:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "exit_long"] = 1

        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        """
        AI-POWERED ENTRY CONFIRMATION

        This is where the magic happens - we check news and AI analysis
        before confirming any trade.
        """
        # If AI clients not available, use traditional strategy only
        if not self._graphiti_client or not self._perplexica_client or not self._llm_client:
            return True

        # Check if we need to fetch news
        if not self._should_check_news(pair, current_time):
            # Use cached analysis if available
            if pair in self._news_cache:
                return self._evaluate_cached_analysis(pair)
            return True  # Default to allowing trade

        # Fetch and analyze news asynchronously
        try:
            analysis_result = asyncio.run(self._analyze_with_ai(pair, rate, **kwargs))

            # Cache the result
            self._news_cache[pair] = analysis_result
            self._last_news_check[pair] = current_time

            # Decision based on analysis
            impact_score = analysis_result.get("impact_score", 0.0)
            sentiment = analysis_result.get("sentiment", "neutral")

            logger.info(f"AI Analysis for {pair}: Impact={impact_score:.2f}, Sentiment={sentiment}")

            # Allow trade if:
            # 1. Impact score is above minimum threshold
            # 2. Sentiment is positive
            should_enter = impact_score >= self.min_impact_score.value and sentiment == "positive"

            if should_enter:
                logger.info(f"✅ AI confirms entry for {pair}")
            else:
                logger.info(f"❌ AI rejects entry for {pair}")

            return should_enter

        except Exception as e:
            logger.error(f"Error in AI analysis: {e}")
            return True  # Default to allowing trade on error

    def _should_check_news(self, pair: str, current_time: datetime) -> bool:
        """Check if it's time to fetch news again"""
        if pair not in self._last_news_check:
            return True

        time_since_check = (current_time - self._last_news_check[pair]).total_seconds()
        return time_since_check >= self.news_check_interval.value

    def _evaluate_cached_analysis(self, pair: str) -> bool:
        """Evaluate using cached analysis"""
        cached = self._news_cache.get(pair, {})
        impact_score = cached.get("impact_score", 0.0)
        sentiment = cached.get("sentiment", "neutral")

        return impact_score >= self.min_impact_score.value and sentiment == "positive"

    async def _analyze_with_ai(self, pair: str, current_price: float, **kwargs) -> Dict[str, Any]:
        """
        Perform full AI analysis:
        1. Fetch news from Perplexica
        2. Analyze correlation with LLM
        3. Store in Graphiti
        4. Retrieve historical context from Graphiti
        """
        dataframe = kwargs.get("dataframe")

        # Get current RSI
        rsi_value = float(dataframe["rsi"].iloc[-1]) if dataframe is not None else 50.0

        # 1. Fetch news
        news_results = await self._perplexica_client.search_crypto_news(pair, timeframe="24h")
        news_summary = await self._perplexica_client.summarize_news(news_results)

        if not news_results:
            return {
                "impact_score": 0.0,
                "sentiment": "neutral",
                "confidence": 0.0,
                "reasoning": "No recent news found",
            }

        # 2. Calculate price change
        if dataframe is not None and len(dataframe) > 1:
            price_change = (
                (dataframe["close"].iloc[-1] - dataframe["close"].iloc[-2])
                / dataframe["close"].iloc[-2]
                * 100
            )
        else:
            price_change = 0.0

        # 3. Analyze with LLM
        analysis = await self._llm_client.analyze_correlation(
            news_summary=news_summary, rsi_value=rsi_value, price_change=price_change, pair=pair
        )

        # 4. Store in Graphiti for shared memory
        impact_score = analysis.get("impact_score", 0.0)

        memory_content = (
            f"News: {news_summary[:100]}... | "
            f"RSI: {rsi_value:.1f} | "
            f"Price Change: {price_change:.2f}% | "
            f"Impact: {impact_score:.2f} | "
            f"Sentiment: {analysis.get('sentiment', 'neutral')}"
        )

        await self._graphiti_client.add_memory(
            pair=pair,
            content=memory_content,
            impact_score=impact_score,
            metadata={
                "rsi": rsi_value,
                "price_change": price_change,
                "sentiment": analysis.get("sentiment"),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # 5. Get historical context (shared across all bots)
        avg_impact = await self._graphiti_client.get_average_impact(pair)

        logger.info(f"Historical avg impact for {pair}: {avg_impact:.2f}")

        # Enhance analysis with historical context
        analysis["historical_avg_impact"] = avg_impact

        return analysis


def reduce(func, iterable):
    """Simple reduce implementation"""
    it = iter(iterable)
    value = next(it)
    for element in it:
        value = func(value, element)
    return value
