"""
News Analysis Models - Complete Implementation

Database models for news articles, learned impact coefficients,
and strategy adjustments.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class NewsArticle(Base):
    """News article with AI analysis metadata"""

    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url_hash = Column(
        String(64), unique=True, nullable=False, index=True
    )  # SHA256 hash for dedup
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    source = Column(String(100))  # e.g., "CoinDesk", "Twitter", "Reddit"
    published_at = Column(DateTime, nullable=False, index=True)
    content = Column(Text)  # Full article text
    summary = Column(Text)  # LLM-generated summary

    # AI Analysis
    analyzed = Column(Boolean, default=False, index=True)
    impact_score = Column(Float)  # 0-1 scale
    sentiment = Column(String(20))  # positive, negative, neutral
    news_type = Column(String(50), index=True)  # regulation, partnership, hack, etc.

    # Relations
    related_pair = Column(String(20), index=True)  # e.g., BTC/USDT

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NewsImpactCoefficient(Base):
    """
    Learned impact coefficients per news type and trading pair.

    Tracks average price movements after specific news types
    to predict future impact.
    """

    __tablename__ = "news_impact_coefficients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(20), nullable=False, index=True)  # BTC/USDT
    news_type = Column(String(50), nullable=False, index=True)  # regulation, hack, etc.

    # Learned values
    avg_price_change = Column(Float)  # Average % change after this news type
    confidence = Column(Float)  # 0-1, based on sample size
    sample_count = Column(Integer, default=0)  # How many times seen

    # Time decay - impact at different timeframes (all KuCoin supported)
    impact_1m = Column(Float)  # 1 minute
    impact_3m = Column(Float)  # 3 minutes
    impact_5m = Column(Float)  # 5 minutes
    impact_15m = Column(Float)  # 15 minutes
    impact_30m = Column(Float)  # 30 minutes
    impact_1h = Column(Float)  # 1 hour
    impact_2h = Column(Float)  # 2 hours
    impact_4h = Column(Float)  # 4 hours
    impact_6h = Column(Float)  # 6 hours
    impact_8h = Column(Float)  # 8 hours
    impact_12h = Column(Float)  # 12 hours
    impact_1d = Column(Float)  # 1 day (24 hours)
    impact_1w = Column(Float)  # 1 week

    # Timestamps
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one coefficient per pair+type
    __table_args__ = (UniqueConstraint("pair", "news_type", name="uq_pair_newstype"),)


class NewsStrategyAdjustment(Base):
    """
    Log of strategy adjustments made based on news.

    Tracks all parameter changes and forced actions to analyze
    effectiveness of news-based adjustments.
    """

    __tablename__ = "news_strategy_adjustments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(
        Integer, ForeignKey("bot_instances.id", ondelete="CASCADE"), nullable=False
    )
    news_id = Column(Integer, ForeignKey("news_articles.id"), nullable=True)

    # Adjustment details
    adjustment_type = Column(String(20))  # soft, hard
    action = Column(String(50))  # rsi_threshold_up, force_sell, etc.
    old_value = Column(Float)
    new_value = Column(Float)

    # Outcome tracking
    was_beneficial = Column(Boolean, nullable=True)  # Did it help?
    pnl_impact = Column(Float, nullable=True)  # Estimated PnL impact

    # Timestamp
    executed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    bot = relationship("BotInstance")
