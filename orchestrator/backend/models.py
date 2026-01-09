"""
Database Models for AI-Trader Orchestrator

SQLAlchemy models for bot instances and parameters.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class BotInstance(Base):
    """Bot instance model - represents a running Freqtrade bot"""

    __tablename__ = "bot_instances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    pair = Column(String(20), nullable=False)  # e.g., BTC/USDT
    timeframe = Column(String(10), nullable=False)  # e.g., 15m, 1h, 4h
    status = Column(String(20), default="stopped")  # stopped, running, error
    mode = Column(String(10), default="demo")  # demo or real

    # Docker/Process info
    container_id = Column(String(100), nullable=True)
    process_id = Column(Integer, nullable=True)

    # Performance metrics
    current_profit = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)

    # Relationships
    params = relationship(
        "BotParams", back_populates="bot", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<BotInstance(id={self.id}, name={self.name}, pair={self.pair}, status={self.status})>"
        )


class BotParams(Base):
    """Bot trading parameters"""

    __tablename__ = "bot_params"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bot_instances.id"), nullable=False)

    # RSI Parameters
    rsi_period = Column(Integer, default=14)
    rsi_oversold = Column(Integer, default=30)
    rsi_overbought = Column(Integer, default=70)

    # Risk Management
    stop_loss = Column(Float, default=-0.05)  # -5%
    take_profit = Column(Float, default=0.10)  # 10%
    max_position_size = Column(Float, default=100.0)  # USDT

    # AI Strategy Parameters
    enable_ai_analysis = Column(Boolean, default=True)
    news_check_interval = Column(Integer, default=3600)  # seconds
    min_impact_score = Column(Float, default=0.3)  # minimum impact score to trade

    # Advanced settings
    custom_params = Column(JSON, nullable=True)  # For any additional custom parameters

    # Relationship
    bot = relationship("BotInstance", back_populates="params")

    def __repr__(self):
        return f"<BotParams(bot_id={self.bot_id}, rsi_period={self.rsi_period})>"


class TradingSignal(Base):
    """Historical trading signals with AI correlation data"""

    __tablename__ = "trading_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bot_instances.id"), nullable=False)

    # Signal data
    timestamp = Column(DateTime, default=datetime.utcnow)
    pair = Column(String(20), nullable=False)
    action = Column(String(10))  # buy, sell, hold

    # Technical indicators
    rsi_value = Column(Float)
    price = Column(Float)

    # AI Analysis
    news_summary = Column(String(500), nullable=True)
    impact_score = Column(Float, nullable=True)
    graphiti_context = Column(JSON, nullable=True)

    # Outcome
    executed = Column(Boolean, default=False)
    profit_loss = Column(Float, nullable=True)

    def __repr__(self):
        return f"<TradingSignal(id={self.id}, pair={self.pair}, action={self.action}, impact_score={self.impact_score})>"
