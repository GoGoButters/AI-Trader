"""
Paper Trading Models

SQLAlchemy models for complete local paper trading simulation.
All trading state is stored locally without Freqtrade interaction.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship

from .database import Base


class PaperBalance(Base):
    """Paper trading balance per currency"""

    __tablename__ = "paper_balances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bot_instances.id", ondelete="CASCADE"), nullable=False)
    currency = Column(String(10), nullable=False)  # e.g., USDT, BTC
    total = Column(DECIMAL(20, 8), nullable=False)  # Total balance
    free = Column(DECIMAL(20, 8), nullable=False)  # Available balance
    used = Column(DECIMAL(20, 8), default=0)  # In open positions
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    bot = relationship("BotInstance", back_populates="paper_balances")


class PaperPosition(Base):
    """Open paper trading positions"""

    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bot_instances.id", ondelete="CASCADE"), nullable=False)
    pair = Column(String(20), nullable=False)  # e.g., BTC/USDT
    side = Column(String(10), nullable=False)  # 'long' or 'short'
    amount = Column(DECIMAL(20, 8), nullable=False)
    entry_price = Column(DECIMAL(20, 8), nullable=False)
    current_price = Column(DECIMAL(20, 8), nullable=True)
    unrealized_pnl = Column(DECIMAL(20, 8), nullable=True)
    leverage = Column(Integer, default=1)
    liquidation_price = Column(DECIMAL(20, 8), nullable=True)  # For futures
    opened_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    bot = relationship("BotInstance", back_populates="paper_positions")


class PaperOrder(Base):
    """Paper trading orders (pending and filled)"""

    __tablename__ = "paper_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bot_instances.id", ondelete="CASCADE"), nullable=False)
    pair = Column(String(20), nullable=False)
    order_type = Column(String(10), nullable=False)  # 'market', 'limit'
    side = Column(String(10), nullable=False)  # 'buy', 'sell'
    amount = Column(DECIMAL(20, 8), nullable=False)
    price = Column(DECIMAL(20, 8), nullable=True)  # Limit price (NULL for market)
    filled_price = Column(DECIMAL(20, 8), nullable=True)  # Actual fill price
    status = Column(String(20), nullable=False)  # 'pending', 'filled', 'cancelled'
    created_at = Column(DateTime, default=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)

    # Relationships
    bot = relationship("BotInstance", back_populates="paper_orders")


class PaperTrade(Base):
    """Executed paper trades"""

    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bot_instances.id", ondelete="CASCADE"), nullable=False)
    pair = Column(String(20), nullable=False)
    order_id = Column(Integer, ForeignKey("paper_orders.id"), nullable=True)
    side = Column(String(10), nullable=False)  # 'buy', 'sell'
    amount = Column(DECIMAL(20, 8), nullable=False)
    price = Column(DECIMAL(20, 8), nullable=False)
    fee = Column(DECIMAL(20, 8), nullable=False)
    fee_currency = Column(String(10), nullable=False)
    realized_pnl = Column(DECIMAL(20, 8), nullable=True)  # For closing trades
    executed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    bot = relationship("BotInstance", back_populates="paper_trades")


class PaperMetrics(Base):
    """Paper trading performance metrics"""

    __tablename__ = "paper_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(
        Integer, ForeignKey("bot_instances.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pnl = Column(DECIMAL(20, 8), default=0)
    max_drawdown = Column(DECIMAL(20, 8), default=0)
    peak_balance = Column(DECIMAL(20, 8), default=0)
    sharpe_ratio = Column(DECIMAL(10, 4), nullable=True)
    win_rate = Column(DECIMAL(5, 2), nullable=True)  # Percentage
    avg_win = Column(DECIMAL(20, 8), nullable=True)
    avg_loss = Column(DECIMAL(20, 8), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    bot = relationship("BotInstance", back_populates="paper_metrics", uselist=False)
