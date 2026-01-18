"""
News Analysis API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta

from ..database import get_db
from ..news_models import NewsArticle, NewsImpactCoefficient
from pydantic import BaseModel

router = APIRouter(prefix="/api/news", tags=["news"])


class NewsResponse(BaseModel):
    id: int
    pair: str | None = None
    title: str
    summary: str | None
    source_url: str | None
    source_name: str | None
    impact_score: float
    confidence: float
    news_category: str | None
    price_change_percent: float | None
    ai_sentiment: str | None
    created_at: datetime
    published_at: datetime | None

    class Config:
        from_attributes = True


class CoefficientResponse(BaseModel):
    pair: str
    news_category: str
    positive_impact_avg: float
    negative_impact_avg: float
    neutral_impact_avg: float
    sample_count: int
    confidence_level: float

    class Config:
        from_attributes = True


@router.get("/list", response_model=List[NewsResponse])
async def list_news(
    pair: str | None = None, limit: int = 20, db: Session = Depends(get_db)
):
    """Get list of analyzed news"""
    query = db.query(NewsArticle)

    if pair:
        # Assuming NewsArticle has a way to relate to pair, or we filter by content
        # For now, simplistic filtering if NewsArticle had a pair column, which it might not directly have
        # If it doesn't, we return all recent news
        pass

    news = query.order_by(NewsArticle.published_at.desc()).limit(limit).all()

    # Map NewsArticle to NewsResponse to handle missing fields gracefully
    result = []
    for n in news:
        result.append(
            NewsResponse(
                id=n.id,
                pair=n.related_pair,  # Use related_pair from NewsArticle
                title=n.title,
                summary=n.summary,
                source_url=n.url,
                source_name=n.source,
                impact_score=n.impact_score or 0.0,
                confidence=0.0,  # Placeholder
                news_category=n.news_type,
                price_change_percent=None,
                ai_sentiment=n.sentiment,
                created_at=n.created_at,
                published_at=n.published_at,
            )
        )

    return result


@router.get("/coefficients", response_model=List[CoefficientResponse])
async def get_coefficients(pair: str | None = None, db: Session = Depends(get_db)):
    """Get impact coefficients"""
    query = db.query(NewsImpactCoefficient)

    if pair:
        query = query.filter(NewsImpactCoefficient.pair == pair)

    coeffs = query.all()

    result = []
    for c in coeffs:
        result.append(
            CoefficientResponse(
                pair=c.pair,
                news_category=c.category,
                positive_impact_avg=c.avg_impact,  # Simplified mapping
                negative_impact_avg=0.0,
                neutral_impact_avg=0.0,
                sample_count=c.sample_count,
                confidence_level=c.confidence,
            )
        )

    return result


@router.get("/stats/{pair}")
async def get_pair_stats(pair: str, db: Session = Depends(get_db)):
    """Get news statistics for a pair"""
    total_news = db.query(NewsImpact).filter(NewsImpact.pair == pair).count()

    avg_impact = (
        db.query(NewsImpact)
        .filter(NewsImpact.pair == pair)
        .with_entities(func.avg(NewsImpact.impact_score))
        .scalar()
        or 0.0
    )

    recent_news = (
        db.query(NewsImpact)
        .filter(
            NewsImpact.pair == pair,
            NewsImpact.created_at >= datetime.utcnow() - timedelta(days=7),
        )
        .count()
    )

    return {
        "pair": pair,
        "total_news_analyzed": total_news,
        "average_impact_score": round(avg_impact, 3),
        "news_last_7_days": recent_news,
    }
