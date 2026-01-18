"""
Paper Trading Manager

Manages lifecycle of paper trading bots and strategy execution.
Runs strategy loop independently from Freqtrade.
"""

import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

import ccxt.async_support as ccxt
import pandas as pd
import ta

from .paper_trading import PaperTradingEngine

logger = logging.getLogger(__name__)


class PaperTradingManager:
    """
    Manages paper trading bot lifecycle and strategy execution.
    """

    def __init__(self):
        self.running_bots: Dict[int, Dict] = {}  # bot_id -> {task, engine, config}
        self.exchange = ccxt.kucoin({"enableRateLimit": True})
        self.news_processor = None

    def set_news_processor(self, processor):
        """Set the news processor instance"""
        self.news_processor = processor
        logger.info("✅ News processor linked to PaperTradingManager")

    async def start_bot(
        self,
        bot_id: int,
        pair: str,
        timeframe: str,
        initial_balance: float,
        trading_mode: str,
        leverage: int,
        params: Dict,
    ):
        """Start paper trading bot with strategy loop"""
        if bot_id in self.running_bots:
            logger.warning(f"Bot {bot_id} already running")
            return

        # Create engine
        engine = PaperTradingEngine(
            bot_id=bot_id,
            pair=pair,
            initial_balance=initial_balance,
            trading_mode=trading_mode,
            leverage=leverage,
        )

        # Start strategy loop
        task = asyncio.create_task(
            self._run_strategy_loop(bot_id, engine, pair, timeframe, params)
        )

        self.running_bots[bot_id] = {
            "task": task,
            "engine": engine,
            "pair": pair,
            "timeframe": timeframe,
            "params": params,
        }

        logger.info(f"Started paper trading bot {bot_id}: {pair} @ {timeframe}")

        # Auto-start news processor for this bot
        if self.news_processor:
            try:
                enable_hard = params.get("news_hard_influence_enabled", False)
                await self.news_processor.start_for_bot(
                    bot_id=bot_id,
                    pair=pair,
                    timeframe=timeframe,
                    enable_hard_influence=enable_hard,
                )
                logger.info(f"📰 News processor started for bot {bot_id}")
            except Exception as e:
                logger.error(f"❌ Failed to start news processor for bot {bot_id}: {e}")

    async def stop_bot(self, bot_id: int):
        """Stop paper trading bot"""
        if bot_id not in self.running_bots:
            logger.warning(f"Bot {bot_id} not running")
            return

        bot_data = self.running_bots[bot_id]

        # Cancel task
        bot_data["task"].cancel()

        try:
            await bot_data["task"]
        except asyncio.CancelledError:
            pass

        # Cleanup engine
        await bot_data["engine"].close()

        del self.running_bots[bot_id]
        logger.info(f"Stopped paper trading bot {bot_id}")

    def get_engine(self, bot_id: int) -> Optional[PaperTradingEngine]:
        """Get engine for bot"""
        bot_data = self.running_bots.get(bot_id)
        return bot_data["engine"] if bot_data else None

    async def get_candles(self, bot_id: int, limit: int = 1000) -> list:
        """Get candles for paper trading bot charts"""
        bot_data = self.running_bots.get(bot_id)
        if not bot_data:
            logger.warning(f"Bot {bot_id} not running")
            return []

        pair = bot_data["pair"]
        timeframe = bot_data["timeframe"]

        try:
            candles = await self._fetch_candles(pair, timeframe, limit=limit)
            return candles
        except Exception as e:
            logger.error(f"Failed to get candles for bot {bot_id}: {e}")
            return []

    async def get_bot_trades(self, bot_id: int, limit: int = 100) -> list:
        """Get trade history for paper trading bot"""
        try:
            from .database import db
            from .paper_trading_models import PaperTrade

            with db.get_session() as session:
                trades = (
                    session.query(PaperTrade)
                    .filter(PaperTrade.bot_id == bot_id)
                    .order_by(PaperTrade.executed_at.desc())
                    .limit(limit)
                    .all()
                )

                # Convert to dict list
                return [
                    {
                        "id": t.id,
                        "bot_id": t.bot_id,
                        "side": t.side,
                        "pair": t.pair,
                        "amount": float(t.amount),
                        "price": float(t.price),
                        "fee": float(t.fee),
                        "pnl": float(t.realized_pnl) if t.realized_pnl else None,
                        "timestamp": t.executed_at.isoformat(),
                        "datetime": t.executed_at.isoformat(),
                    }
                    for t in trades
                ]
        except Exception as e:
            logger.error(f"Failed to get trades for bot {bot_id}: {e}")
            return []

    async def _run_strategy_loop(
        self,
        bot_id: int,
        engine: PaperTradingEngine,
        pair: str,
        timeframe: str,
        params: Dict,
    ):
        """
        Main strategy execution loop.

        Fetches candles, calculates indicators, generates signals,
        and executes trades.
        """
        logger.info(f"Strategy loop started for bot {bot_id}")

        while True:
            try:
                # 1. Fetch latest candles
                candles = await self._fetch_candles(pair, timeframe, limit=100)

                if not candles or len(candles) < 50:
                    logger.warning(f"Not enough candles for {pair}, waiting...")
                    await asyncio.sleep(60)
                    continue

                # 2. Calculate indicators
                df = self._candles_to_dataframe(candles)
                indicators = self._calculate_indicators(df, params)

                # 3. Generate signal
                signal = self._evaluate_strategy(indicators, params)

                # 4. Execute if signal
                if signal == "buy":
                    try:
                        # Calculate position size
                        current_price = await engine.get_current_price()
                        max_position = params.get("max_position_size", 100)
                        amount = max_position / current_price

                        await engine.execute_order("buy", amount)
                        logger.info(
                            f"Bot {bot_id}: Executed BUY {amount} @ ${current_price}"
                        )
                    except Exception as e:
                        logger.error(f"Buy order failed: {e}")

                elif signal == "sell":
                    try:
                        # Get current position
                        from .database import db
                        from .paper_trading_models import PaperPosition

                        with db.get_session() as session:
                            position = (
                                session.query(PaperPosition)
                                .filter(
                                    PaperPosition.bot_id == bot_id,
                                    PaperPosition.pair == pair,
                                )
                                .first()
                            )

                            if position:
                                amount = float(position.amount)
                                await engine.execute_order("sell", amount)
                                logger.info(f"Bot {bot_id}: Executed SELL {amount}")
                    except Exception as e:
                        logger.error(f"Sell order failed: {e}")

                # 5. Check liquidations (for futures)
                if engine.trading_mode == "futures":
                    await engine.check_liquidations()

                # 6. Sleep until next candle
                sleep_seconds = self._timeframe_to_seconds(timeframe)
                await asyncio.sleep(sleep_seconds)

            except asyncio.CancelledError:
                logger.info(f"Strategy loop cancelled for bot {bot_id}")
                raise
            except Exception as e:
                logger.error(
                    f"Error in strategy loop for bot {bot_id}: {e}", exc_info=True
                )
                await asyncio.sleep(60)  # Wait before retry

    async def _fetch_candles(self, pair: str, timeframe: str, limit: int = 100):
        """Fetch OHLCV candles from exchange"""
        try:
            candles = await self.exchange.fetch_ohlcv(pair, timeframe, limit=limit)
            return candles
        except Exception as e:
            logger.error(f"Failed to fetch candles for {pair}: {e}")
            return []

    async def fetch_candles_direct(self, pair: str, timeframe: str, limit: int = 1000):
        """
        Fetch candles directly from exchange without requiring bot to be running.
        Used when bot is not in memory but we still need chart data.
        """
        return await self._fetch_candles(pair, timeframe, limit)

    def _candles_to_dataframe(self, candles) -> pd.DataFrame:
        """Convert candles to DataFrame"""
        df = pd.DataFrame(
            candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    def _calculate_indicators(self, df: pd.DataFrame, params: Dict) -> Dict:
        """Calculate technical indicators"""
        # RSI
        rsi_period = params.get("rsi_period", 14)
        rsi = ta.momentum.RSIIndicator(df["close"], window=rsi_period).rsi()

        # MACD
        macd_indicator = ta.trend.MACD(
            df["close"], window_fast=12, window_slow=26, window_sign=9
        )
        macd = macd_indicator.macd()
        macd_signal = macd_indicator.macd_signal()

        # Volume
        volume_sma = df["volume"].rolling(window=20).mean()

        return {
            "rsi": rsi.iloc[-1] if len(rsi) > 0 else 50,
            "macd": macd.iloc[-1] if len(macd) > 0 else 0,
            "macd_signal": macd_signal.iloc[-1] if len(macd_signal) > 0 else 0,
            "volume": df["volume"].iloc[-1],
            "volume_sma": volume_sma.iloc[-1]
            if len(volume_sma) > 0
            else df["volume"].iloc[-1],
            "close": df["close"].iloc[-1],
        }

    def _evaluate_strategy(self, indicators: Dict, params: Dict) -> str:
        """
        Evaluate strategy and generate signal.

        Enhanced RSI + MACD strategy:
        - Buy when RSI < oversold AND (MACD bullish OR macd_enabled=False)
        - Sell when RSI > overbought AND (MACD bearish OR macd_enabled=False)
        - Default thresholds: 40 (oversold), 60 (overbought) for more trades
        """
        rsi = indicators["rsi"]
        macd = indicators["macd"]
        macd_signal = indicators["macd_signal"]
        close = indicators["close"]

        # Wider thresholds for more frequent trades (40/60 instead of 30/70)
        rsi_oversold = params.get("rsi_oversold", 40)
        rsi_overbought = params.get("rsi_overbought", 60)
        macd_enabled = params.get("macd_enabled", True)

        # MACD conditions
        macd_bullish = macd > macd_signal  # MACD above signal line
        macd_bearish = macd < macd_signal  # MACD below signal line

        # Log current indicators
        macd_status = f"MACD={macd:.4f} vs Signal={macd_signal:.4f} ({'↑bull' if macd_bullish else '↓bear'})"
        logger.debug(
            f"📊 RSI={rsi:.2f} (buy<{rsi_oversold}, sell>{rsi_overbought}) | "
            f"{macd_status if macd_enabled else 'MACD disabled'} | "
            f"Price=${close:.2f}"
        )

        # Buy signal: RSI oversold + (MACD bullish or MACD disabled)
        if rsi < rsi_oversold:
            if not macd_enabled or macd_bullish:
                logger.info(
                    f"🟢 BUY SIGNAL: RSI={rsi:.2f} < {rsi_oversold}"
                    + (f" + MACD bullish" if macd_enabled else "")
                )
                return "buy"
            else:
                logger.debug(f"⏸️  RSI oversold but MACD bearish - waiting")

        # Sell signal: RSI overbought + (MACD bearish or MACD disabled)
        if rsi > rsi_overbought:
            if not macd_enabled or macd_bearish:
                logger.info(
                    f"🔴 SELL SIGNAL: RSI={rsi:.2f} > {rsi_overbought}"
                    + (f" + MACD bearish" if macd_enabled else "")
                )
                return "sell"
            else:
                logger.debug(f"⏸️  RSI overbought but MACD bullish - waiting")

        return "hold"

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        """Convert timeframe string to seconds"""
        multipliers = {
            "m": 60,
            "h": 3600,
            "d": 86400,
        }

        if len(timeframe) < 2:
            return 900  # Default 15 minutes

        value = int(timeframe[:-1])
        unit = timeframe[-1]

        return value * multipliers.get(unit, 60)

    async def cleanup(self):
        """Cleanup all resources"""
        # Stop all bots
        for bot_id in list(self.running_bots.keys()):
            await self.stop_bot(bot_id)

        # Close exchange
        await self.exchange.close()


# Global instance
paper_trading_manager = PaperTradingManager()
