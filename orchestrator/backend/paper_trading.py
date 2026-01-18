"""
Paper Trading Engine

Complete local simulation of trading without exchange interaction.
Fetches only OHLCV data from exchange for price information.
"""

import asyncio
import logging
import random
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

import ccxt.async_support as ccxt
from sqlalchemy.orm import Session

from .database import db
from .paper_trading_models import (
    PaperBalance,
    PaperMetrics,
    PaperOrder,
    PaperPosition,
    PaperTrade,
)

logger = logging.getLogger(__name__)


class InsufficientBalance(Exception):
    """Raised when account has insufficient balance"""

    pass


class InsufficientPosition(Exception):
    """Raised when trying to sell more than position size"""

    pass


class PaperTradingEngine:
    """
    Paper trading engine with realistic order execution simulation.

    Features:
    - Realistic slippage (0.05% - 0.1%)
    - Trading fees (0.1% taker)
    - Balance and position tracking
    - PnL calculation
    - Futures liquidation simulation
    """

    def __init__(
        self,
        bot_id: int,
        pair: str,
        initial_balance: float = 1000.0,
        trading_mode: str = "spot",
        leverage: int = 1,
    ):
        self.bot_id = bot_id
        self.pair = pair
        self.trading_mode = trading_mode
        self.leverage = leverage

        # Initialize exchange (for price data only)
        self.exchange = ccxt.kucoin(
            {
                "enableRateLimit": True,
            }
        )

        # Initialize balance
        self._init_balance(initial_balance)

        logger.info(
            f"PaperTradingEngine initialized for bot {bot_id}: "
            f"{trading_mode} mode, {leverage}x leverage, ${initial_balance} initial"
        )

    def _init_balance(self, amount: float):
        """Initialize starting balance in database"""
        with db.get_session() as session:
            # Check if balance already exists
            existing = (
                session.query(PaperBalance)
                .filter(PaperBalance.bot_id == self.bot_id, PaperBalance.currency == "USDT")
                .first()
            )

            if not existing:
                balance = PaperBalance(
                    bot_id=self.bot_id,
                    currency="USDT",
                    total=Decimal(str(amount)),
                    free=Decimal(str(amount)),
                    used=Decimal("0"),
                )
                session.add(balance)

                # Initialize metrics
                metrics = PaperMetrics(
                    bot_id=self.bot_id,
                    peak_balance=Decimal(str(amount)),
                )
                session.add(metrics)

                session.commit()
                logger.info(f"Initialized balance: ${amount} USDT")

    async def get_current_price(self, pair: Optional[str] = None) -> float:
        """Fetch real-time price from exchange"""
        try:
            ticker = await self.exchange.fetch_ticker(pair or self.pair)
            return float(ticker["last"])
        except Exception as e:
            logger.error(f"Failed to fetch price for {pair or self.pair}: {e}")
            raise

    async def execute_order(
        self,
        side: str,
        amount: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Dict:
        """
        Execute paper trade or place pending order.
        """
        logger.info(
            f"Processing {order_type} {side} order: {amount} {self.pair} (Lev: {self.leverage}x)"
        )

        # 1. Get current market price
        market_price = await self.get_current_price()

        # 2. Limit Order Logic
        if order_type == "limit":
            if not limit_price:
                raise ValueError("Limit price required for limit orders")

            # Create PENDING order
            with db.get_session() as session:
                order = PaperOrder(
                    bot_id=self.bot_id,
                    pair=self.pair,
                    order_type="limit",
                    side=side,
                    amount=Decimal(str(amount)),
                    price=Decimal(str(limit_price)),
                    status="pending",
                )
                session.add(order)
                session.commit()
                logger.info(f"⏳ Placed pending limit {side} order @ {limit_price}")
                return {"id": order.id, "status": "pending", "price": limit_price, "side": side}

        # 3. Market Order Execution
        # Calculate slippage (0.05% - 0.1% random)
        slippage_pct = random.uniform(0.0005, 0.001)
        if side == "buy":
            fill_price = market_price * (1 + slippage_pct)
        else:
            fill_price = market_price * (1 - slippage_pct)

        return await self._execute_fill(side, amount, fill_price)

    async def _execute_fill(
        self, side: str, amount: float, fill_price: float, order_id: int = None
    ) -> Dict:
        """Internal method to execute a fill (market or triggered limit)"""

        # Calculate fees (0.1% taker)
        fee_rate = 0.001
        notional_value = amount * fill_price
        fee = notional_value * fee_rate

        # Calculate Required Margin / Cost
        if self.trading_mode == "futures":
            # Margin = Notional / Leverage
            initial_margin = notional_value / self.leverage
            cost = initial_margin
        else:
            # Spot = Full Value
            cost = notional_value

        with db.get_session() as session:
            # Check Balance / Position
            if side == "buy":
                # For Futures Buy = Open Long OR Close Short
                # Simplified: We treat 'buy' as Open Long if no Short exists, or Close Short if Short exists.
                # But for now assuming Freqtrade logic: Buy = Enter Long (or Close Short distinct?)
                # We'll stick to simple "Buy = Enter Long" for this MVP unless position exists

                # Check for existing short to close?
                existing_short = (
                    session.query(PaperPosition)
                    .filter(PaperPosition.bot_id == self.bot_id, PaperPosition.side == "short")
                    .first()
                )

                if existing_short:
                    # Closing Short
                    return self._close_position_internal(
                        session, existing_short, fill_price, amount
                    )

                # Open Long
                balance = self._get_balance(session, "USDT")
                required = cost + fee

                if required > float(balance.free):
                    # Try to free up 'used' balance if it's a limit order fill?
                    # For now raise error
                    raise InsufficientBalance(
                        f"Need ${required:.2f}, have ${float(balance.free):.2f}"
                    )

                self._open_position(session, amount, fill_price, "long")
                self._update_balance(session, "USDT", -required)  # Deduct margin + fee
                pnl = 0.0

            else:  # Sell
                # For Futures Sell = Open Short OR Close Long
                existing_long = (
                    session.query(PaperPosition)
                    .filter(PaperPosition.bot_id == self.bot_id, PaperPosition.side == "long")
                    .first()
                )

                if existing_long:
                    # Closing Long
                    return self._close_position_internal(session, existing_long, fill_price, amount)

                # Open Short
                balance = self._get_balance(session, "USDT")
                required = cost + fee

                if required > float(balance.free):
                    raise InsufficientBalance(
                        f"Need ${required:.2f}, have ${float(balance.free):.2f}"
                    )

                # Deduct margin for short
                self._open_position(session, amount, fill_price, "short")
                self._update_balance(session, "USDT", -required)
                pnl = 0.0

            # Record Trade
            trade = self._save_trade(session, side, amount, fill_price, fee, pnl)
            if order_id:
                trade.order_id = order_id
                # Update Order Status
                order = session.query(PaperOrder).get(order_id)
                if order:
                    order.status = "filled"
                    order.filled_price = Decimal(str(fill_price))
                    order.filled_at = datetime.utcnow()

            self._update_metrics(session, 0)  # PnL realized only on close
            session.commit()

            return {"id": trade.id, "side": side, "amount": amount, "price": fill_price, "fee": fee}

    def _close_position_internal(self, session, position, price, amount):
        """Helper to close position and calculate PnL"""
        # Calculate PnL
        pnl = self._calculate_pnl(position, price)

        # Release Margin (Initial Margin was locked)
        initial_margin = (float(position.entry_price) * float(position.amount)) / position.leverage

        # Return Margin + PnL - Fee
        fee = (price * amount) * 0.001
        return_amount = initial_margin + pnl - fee

        self._update_balance(session, "USDT", return_amount)
        self._close_position(session, position.id, price, pnl)

        # Record Trade
        trade = self._save_trade(
            session, "sell" if position.side == "long" else "buy", amount, price, fee, pnl
        )
        self._update_metrics(session, pnl)
        session.commit()

        return {"id": trade.id, "side": "sell", "pnl": pnl, "status": "closed"}

    def _get_balance(self, session: Session, currency: str) -> PaperBalance:
        """Get balance for currency"""
        balance = (
            session.query(PaperBalance)
            .filter(PaperBalance.bot_id == self.bot_id, PaperBalance.currency == currency)
            .first()
        )

        if not balance:
            raise ValueError(f"No balance found for {currency}")

        return balance

    def _get_position(self, session: Session) -> Optional[PaperPosition]:
        """Get open position for pair"""
        return (
            session.query(PaperPosition)
            .filter(PaperPosition.bot_id == self.bot_id, PaperPosition.pair == self.pair)
            .first()
        )

    def _open_position(self, session: Session, amount: float, price: float, side: str):
        """Open new position"""
        # Calculate liquidation price for futures
        if self.trading_mode == "futures":
            liq_price = self._calc_liquidation_price(price, side)
        else:
            liq_price = None

        position = PaperPosition(
            bot_id=self.bot_id,
            pair=self.pair,
            side=side,
            amount=Decimal(str(amount)),
            entry_price=Decimal(str(price)),
            current_price=Decimal(str(price)),
            unrealized_pnl=Decimal("0"),
            leverage=self.leverage,
            liquidation_price=Decimal(str(liq_price)) if liq_price else None,
        )

        session.add(position)
        logger.debug(f"Opened {side} position: {amount} @ ${price}")

    def _close_position(self, session: Session, position_id: int, exit_price: float, pnl: float):
        """Close position"""
        position = session.query(PaperPosition).get(position_id)
        if position:
            session.delete(position)
            logger.debug(f"Closed position {position_id}: PnL=${pnl:.2f}")

    def _calculate_pnl(self, position: PaperPosition, exit_price: float) -> float:
        """Calculate realized PnL"""
        entry = float(position.entry_price)
        amount = float(position.amount)

        if position.side == "long":
            pnl = (exit_price - entry) * amount
        else:  # short
            pnl = (entry - exit_price) * amount

        # Apply leverage multiplier
        pnl *= self.leverage

        return pnl

    def _calc_liquidation_price(self, entry_price: float, side: str) -> float:
        """Calculate liquidation price for futures"""
        buffer = 0.05  # 5% buffer

        if side == "long":
            # Long liquidation = entry - (entry / leverage) - buffer
            liq = entry_price * (1 - (1 / self.leverage) - buffer)
        else:
            # Short liquidation = entry + (entry / leverage) + buffer
            liq = entry_price * (1 + (1 / self.leverage) + buffer)

        return liq

    def _update_balance(self, session: Session, currency: str, delta: float):
        """Update balance by delta"""
        balance = self._get_balance(session, currency)

        balance.total = Decimal(str(float(balance.total) + delta))
        balance.free = Decimal(str(float(balance.free) + delta))
        balance.updated_at = datetime.utcnow()

        logger.debug(f"Updated {currency} balance: {delta:+.2f} -> {float(balance.total):.2f}")

    def _save_trade(
        self,
        session: Session,
        side: str,
        amount: float,
        price: float,
        fee: float,
        pnl: Optional[float],
    ) -> PaperTrade:
        """Record trade in database"""
        trade = PaperTrade(
            bot_id=self.bot_id,
            pair=self.pair,
            side=side,
            amount=Decimal(str(amount)),
            price=Decimal(str(price)),
            fee=Decimal(str(fee)),
            fee_currency="USDT",
            realized_pnl=Decimal(str(pnl)) if pnl else None,
        )

        session.add(trade)
        return trade

    def _update_metrics(self, session: Session, pnl: float):
        """Update performance metrics"""
        metrics = session.query(PaperMetrics).filter(PaperMetrics.bot_id == self.bot_id).first()

        if not metrics:
            return

        metrics.total_trades += 1
        metrics.total_pnl = Decimal(str(float(metrics.total_pnl) + pnl))

        if pnl > 0:
            metrics.winning_trades += 1
            if metrics.avg_win:
                # Running average
                metrics.avg_win = Decimal(
                    str(
                        (float(metrics.avg_win) * (metrics.winning_trades - 1) + pnl)
                        / metrics.winning_trades
                    )
                )
            else:
                metrics.avg_win = Decimal(str(pnl))
        elif pnl < 0:
            metrics.losing_trades += 1
            if metrics.avg_loss:
                metrics.avg_loss = Decimal(
                    str(
                        (float(metrics.avg_loss) * (metrics.losing_trades - 1) + abs(pnl))
                        / metrics.losing_trades
                    )
                )
            else:
                metrics.avg_loss = Decimal(str(abs(pnl)))

        # Update win rate
        if metrics.total_trades > 0:
            metrics.win_rate = Decimal(str((metrics.winning_trades / metrics.total_trades) * 100))

        # Update drawdown
        balance = self._get_balance(session, "USDT")
        current_total = float(balance.total)

        if current_total > float(metrics.peak_balance):
            metrics.peak_balance = Decimal(str(current_total))

        drawdown = (float(metrics.peak_balance) - current_total) / float(metrics.peak_balance)
        if drawdown > float(metrics.max_drawdown or 0):
            metrics.max_drawdown = Decimal(str(drawdown))

        metrics.updated_at = datetime.utcnow()

    async def check_liquidations(self):
        """Check if any positions should be liquidated"""
        if self.trading_mode != "futures":
            return

        with db.get_session() as session:
            position = self._get_position(session)

            if not position or not position.liquidation_price:
                return

            current_price = await self.get_current_price()
            liq_price = float(position.liquidation_price)

            should_liquidate = False

            if position.side == "long" and current_price <= liq_price:
                should_liquidate = True
                logger.warning(
                    f"LIQUIDATION: Long position @ ${liq_price} (current: ${current_price})"
                )
            elif position.side == "short" and current_price >= liq_price:
                should_liquidate = True
                logger.warning(
                    f"LIQUIDATION: Short position @ ${liq_price} (current: ${current_price})"
                )

            if should_liquidate:
                # Forced close at liquidation price
                pnl = self._calculate_pnl(position, liq_price)
                self._close_position(session, position.id, liq_price, pnl)

                # Liquidation fee (additional 0.5%)
                liquidation_fee = float(position.amount) * liq_price * 0.005
                self._update_balance(session, "USDT", -liquidation_fee)

                # Record liquidation trade
                self._save_trade(
                    session, "sell", float(position.amount), liq_price, liquidation_fee, pnl
                )

                session.commit()

    def get_portfolio_value(self) -> Dict:
        """Calculate total portfolio value"""
        with db.get_session() as session:
            balance = self._get_balance(session, "USDT")
            position = self._get_position(session)

            total_value = float(balance.total)
            positions_value = 0

            if position:
                # Add unrealized PnL
                positions_value = float(position.unrealized_pnl or 0)
                total_value += positions_value

            return {
                "total_value": total_value,
                "cash": float(balance.total),
                "positions_value": positions_value,
                "positions_count": 1 if position else 0,
            }

    async def process_pending_orders(
        self, candle_open: float, candle_high: float, candle_low: float, candle_close: float
    ):
        """
        Check pending orders against candle High/Low.
        Realistic matching: Buy Limit fills if Low < Price. Sell Limit fills if High > Price.
        """
        with db.get_session() as session:
            pending_orders = (
                session.query(PaperOrder)
                .filter(PaperOrder.bot_id == self.bot_id, PaperOrder.status == "pending")
                .all()
            )

            if not pending_orders:
                return

            for order in pending_orders:
                limit_price = float(order.price)
                triggered = False

                # Buy Limit
                if order.side == "buy":
                    if candle_low <= limit_price:
                        # Filled! Assume filled at limit price (best case) or worst case?
                        # Honest: Filled at Limit Price
                        triggered = True

                # Sell Limit
                elif order.side == "sell":
                    if candle_high >= limit_price:
                        triggered = True

                if triggered:
                    logger.info(
                        f"⚡ Order {order.id} triggered! {order.side} @ {limit_price} (High: {candle_high}, Low: {candle_low})"
                    )
                    try:
                        # Execute the fill
                        await self._execute_fill(
                            order.side, float(order.amount), limit_price, order.id
                        )
                    except Exception as e:
                        logger.error(f"Failed to fill triggered order {order.id}: {e}")

    async def close(self):
        """Cleanup resources"""
        await self.exchange.close()
