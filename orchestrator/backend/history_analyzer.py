import asyncio
import logging
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict

logger = logging.getLogger(__name__)


class HistoryAnalyzer:
    """
    Analyzes historical data (News + Price) to build initial knowledge graph.
    """

    def __init__(self):
        self.news_processor = None

    def set_processor(self, processor):
        self.news_processor = processor

    async def analyze_history(self, bot_id: int, pair: str, days: int = 10):
        """
        Main entry point:
        1. Fetch 10 days of candles.
        2. Fetch 10 days of news (day by day).
        3. Correlate and store.
        """
        logger.info(f"📜 Starting historical analysis for {pair} ({days} days)")

        try:
            # 1. Fetch Candles
            from .paper_trading_manager import paper_trading_manager

            engine = paper_trading_manager.get_engine(bot_id)
            if not engine:
                logger.error(f"❌ Engine not found for bot {bot_id}")
                return

            # Fetch via CCXT (we need OHLCV for 10 days)
            # 10 days * 24h = 240 hours. If timeframe 15m -> 96 * 10 = 960 candles.
            # safe limit 1500
            candles = await paper_trading_manager.exchange.fetch_ohlcv(
                pair, "1h", limit=24 * days
            )
            df = pd.DataFrame(
                candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

            logger.info(f"📜 Fetched {len(df)} candles for {pair}")

            # 2. Fetch News Day by Day
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            current_date = start_date
            total_news = 0

            while current_date < end_date:
                next_date = current_date + timedelta(days=1)

                # Fetch news for this 24h window
                news_items = await self._fetch_news_for_day(pair, current_date)

                for article in news_items:
                    # 3. Correlate
                    await self._correlate_and_store(article, df, pair)
                    total_news += 1

                current_date = next_date
                await asyncio.sleep(1)  # Rate limit protection

            logger.info(
                f"✅ Historical analysis complete. Processed {total_news} articles."
            )

        except Exception as e:
            logger.error(f"❌ Historical analysis failed: {e}", exc_info=True)

    async def _fetch_news_for_day(self, pair: str, date: datetime) -> List[Dict]:
        """Fetch news for a specific date using Perplexica"""
        if not self.news_processor:
            return []

        base = pair.split("/")[0]
        date_str = date.strftime("%Y-%m-%d")
        query = f"{base} crypto news {date_str}"

        try:
            # We access Perplexica client via news_processor
            results = await self.news_processor.perplexica.search(
                query=query,
                focus_mode="news",
                time_range="month",  # broader range, client filters
            )
            # Filter loosely by date (Perplexica might return recent stuff)
            # In a real prod env, we'd need a better archive news API.
            # For now, we accept what Perplexica gives if it mentions the date or looks relevant.
            return results
        except Exception as e:
            logger.warning(f"Failed to fetch history for {date_str}: {e}")
            return []

    async def _correlate_and_store(self, article: Dict, df: pd.DataFrame, pair: str):
        """
        Check price movement after article publication and store influence.
        """
        try:
            # 1. Parse Date - handle both datetime objects and strings
            pub_date_raw = (
                article.get("published_at")
                or article.get("date")
                or article.get("publishedDate")
            )
            if not pub_date_raw:
                logger.debug(
                    f"No date found for article: {article.get('title', 'Unknown')[:50]}"
                )
                return

            # Handle datetime object or string
            if isinstance(pub_date_raw, datetime):
                pub_date = pub_date_raw
            elif isinstance(pub_date_raw, str):
                try:
                    pub_date = datetime.fromisoformat(
                        pub_date_raw.replace("Z", "+00:00")
                    )
                except ValueError:
                    logger.debug(f"Invalid date format: {pub_date_raw}")
                    return
            else:
                logger.debug(f"Unknown date type: {type(pub_date_raw)}")
                return

            # 2. Find Price Impact (1h, 4h)
            # Find candle closest to pub_date
            closest_idx = df.index[df["datetime"].sub(pub_date).abs().idxmin()]

            if closest_idx + 4 >= len(df):
                return  # Not enough data after news

            price_at_news = df.iloc[closest_idx]["close"]
            price_1h_after = df.iloc[closest_idx + 1]["close"]  # Assuming 1h candles
            price_4h_after = df.iloc[closest_idx + 4]["close"]

            impact_1h = ((price_1h_after - price_at_news) / price_at_news) * 100
            impact_4h = ((price_4h_after - price_at_news) / price_at_news) * 100

            # 3. Classify News (Using LLM via NewsProcessor logic)
            # We reuse the _classify_with_context or similar logic,
            # but here we KNOW the impact, so we are TEACHING the system.

            # Construct a "Teaching" prompt -> Graphiti
            classification = await self.news_processor._classify_with_context(
                pair, article
            )

            logger.info(
                f"📜 {pair} History: {article.get('title', '')[:30]}... "
                f"Impact 1h: {impact_1h:+.2f}% | Type: {classification['type']}"
            )

            # 4. Store Knowledge in Graphiti (Memory)
            # We store the FACT that this type of news caused this impact
            try:
                pub_date_str = pub_date.isoformat() if pub_date else "unknown"
                fact = (
                    f"News: '{article.get('title')}' ({classification['type']}) "
                    f"on {pub_date_str} caused {impact_1h:+.2f}% movement in 1h."
                )
                await self.news_processor.graphiti.add_fact(
                    source=article.get("url", "history"),
                    fact=fact,
                    user_id=pair.replace("/", "_"),  # Store per pair as requested
                )
            except Exception as e:
                logger.warning(f"Failed to store fact in Graphiti: {e}")

            # 5. Save article to NewsArticle table
            from .database import db
            from .news_models import NewsArticle, NewsImpactCoefficient
            import hashlib

            try:
                url = article.get("url", "")
                url_hash = hashlib.md5(url.encode()).hexdigest() if url else None

                with db.get_session() as session:
                    # Check if article already exists
                    if url_hash:
                        existing = (
                            session.query(NewsArticle)
                            .filter(NewsArticle.url_hash == url_hash)
                            .first()
                        )
                        if not existing:
                            news_article = NewsArticle(
                                url_hash=url_hash,
                                title=article.get("title", "")[:500],
                                url=url[:1000],
                                source=article.get("source", "SearXNG")[:100],
                                summary=article.get("content", "")[:2000],
                                news_type=classification.get("type", "unknown"),
                                sentiment=classification.get("sentiment", "neutral"),
                                impact_score=abs(impact_1h) / 100.0
                                if impact_1h
                                else 0.0,  # Normalize to 0-1 scale
                                published_at=pub_date,
                                related_pair=pair,  # Set the trading pair
                                created_at=datetime.utcnow(),
                            )
                            session.add(news_article)
                            session.commit()
                            logger.debug(
                                f"💾 Saved article: {article.get('title', '')[:40]}"
                            )
            except Exception as e:
                logger.warning(f"Failed to save article: {e}")

            # 6. Connect to SQL DB Models (NewsImpactCoefficient)
            with db.get_session() as session:
                coeff = (
                    session.query(NewsImpactCoefficient)
                    .filter(
                        NewsImpactCoefficient.pair == pair,
                        NewsImpactCoefficient.news_type == classification["type"],
                    )
                    .first()
                )

                if not coeff:
                    coeff = NewsImpactCoefficient(
                        pair=pair,
                        news_type=classification["type"],
                        # Initialize all timeframe impacts (will be calculated as data comes in)
                        impact_1m=0.0,
                        impact_3m=0.0,
                        impact_5m=0.0,
                        impact_15m=0.0,
                        impact_30m=0.0,
                        impact_1h=0.0,
                        impact_2h=0.0,
                        impact_4h=0.0,
                        impact_6h=0.0,
                        impact_8h=0.0,
                        impact_12h=0.0,
                        impact_1d=0.0,
                        impact_1w=0.0,
                        confidence=0.0,
                        sample_count=0,
                    )
                    session.add(coeff)

                # Update moving average
                n = coeff.sample_count
                coeff.impact_1h = (coeff.impact_1h * n + impact_1h) / (n + 1)
                coeff.impact_4h = (coeff.impact_4h * n + impact_4h) / (n + 1)
                coeff.sample_count += 1
                coeff.confidence = min(
                    0.95, coeff.sample_count * 0.1
                )  # increases with samples

                session.commit()

        except Exception as e:
            logger.error(f"Error correlating history: {e}")


# Global Instance
history_analyzer = HistoryAnalyzer()


async def start_historical_analysis(bot_id: int, pair: str, days: int):
    # Link processor dynamically from news_processor module
    from .news_processor import news_processor

    if news_processor:
        history_analyzer.set_processor(news_processor)
        await history_analyzer.analyze_history(bot_id, pair, days)
    else:
        logger.warning("News processor not ready for history analysis")
