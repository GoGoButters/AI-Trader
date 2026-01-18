"""
News Correlation Engine

Analyzes historical news and correlates with price movements
to learn impact patterns using AI.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import ccxt.async_support as ccxt
import pandas as pd

logger = logging.getLogger(__name__)


class NewsCorrelationEngine:
    """
    Correlates news events with price movements to learn impact patterns.
    """

    def __init__(self, llm_client, perplexica_client, graphiti_client):
        self.llm = llm_client
        self.perplexica = perplexica_client
        self.graphiti = graphiti_client

    async def analyze_historical(
        self,
        pair: str,
        days: int = 10,
    ) -> List[Dict]:
        """
        Analyze last N days of news and price data.

        Args:
            pair: Trading pair (e.g., BTC/USDT)
            days: Number of days to analyze

        Returns:
            List of correlation results
        """
        logger.info(f"🔍 Starting historical news analysis: {pair} ({days} days)")

        try:
            # 1. Fetch price data
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            price_data = await self._fetch_price_data(pair, start_date, end_date)
            logger.info(f"📊 Fetched {len(price_data)} price candles")

            # 2. Fetch news
            news_articles = await self._fetch_news(pair, start_date, end_date)
            logger.info(f"📰 Found {len(news_articles)} news articles")

            if not news_articles:
                logger.warning("No news articles found for analysis")
                return []

            # 3. Correlate each news with price movement
            correlations = []

            for i, article in enumerate(news_articles, 1):
                logger.debug(
                    f"Processing article {i}/{len(news_articles)}: {article.get('title', 'Untitled')[:50]}"
                )

                correlation = await self._correlate_article(article, price_data, pair)

                if correlation:
                    correlations.append(correlation)

            logger.info(f"✅ Analyzed {len(correlations)} news-price correlations")

            # 4. Learn and store coefficients
            await self._update_coefficients(pair, correlations)

            return correlations

        except Exception as e:
            logger.error(f"❌ Historical analysis failed: {e}", exc_info=True)
            return []

    async def _fetch_price_data(self, pair: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Fetch OHLCV data from exchange"""
        try:
            exchange = ccxt.kucoin({"enableRateLimit": True})

            # Fetch 1h candles
            since = int(start.timestamp() * 1000)
            candles = await exchange.fetch_ohlcv(pair, "1h", since=since, limit=1000)

            await exchange.close()

            if not candles:
                logger.warning(f"No price data received for {pair}")
                return pd.DataFrame()

            df = pd.DataFrame(
                candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            return df

        except Exception as e:
            logger.error(f"Failed to fetch price data: {e}")
            return pd.DataFrame()

    async def _fetch_news(self, pair: str, start: datetime, end: datetime) -> List[Dict]:
        """Fetch news from Perplexica"""
        try:
            # Extract base currency (BTC from BTC/USDT)
            base = pair.split("/")[0]

            # Build query
            query = f"{base} cryptocurrency news latest"

            logger.info(f"Searching Perplexica: '{query}'")

            # Search Perplexica
            results = await self.perplexica.search(
                query=query,
                focus_mode="news",
                time_range="month",  # Last month
            )

            # Filter by date range
            filtered = []
            for article in results:
                pub_date = article.get("published_at")
                if pub_date and start <= pub_date <= end:
                    filtered.append(article)

            return filtered

        except Exception as e:
            logger.error(f"Failed to fetch news: {e}")
            return []

    async def _correlate_article(
        self, article: Dict, price_data: pd.DataFrame, pair: str
    ) -> Dict | None:
        """
        Correlate single article with price movement.

        Looks at price change after news publication at 1h, 4h, 24h intervals.
        """
        try:
            pub_time = article.get("published_at")

            if not pub_time or price_data.empty:
                return None

            # Find closest candle before publication
            price_before_mask = price_data["timestamp"] <= pub_time
            if not price_before_mask.any():
                return None

            price_before = price_data[price_before_mask].iloc[-1]

            # Track price at 1h, 4h, 24h after
            changes = {}

            for hours in [1, 4, 24]:
                target_time = pub_time + timedelta(hours=hours)
                price_after_mask = price_data["timestamp"] >= target_time

                if not price_after_mask.any():
                    continue

                price_after = price_data[price_after_mask].iloc[0]

                pct_change = (
                    (price_after["close"] - price_before["close"]) / price_before["close"]
                ) * 100

                changes[f"{hours}h"] = pct_change

            if not changes:
                return None

            # Use LLM to classify news type and sentiment
            classification = await self._classify_news(article)

            # Save article to database
            await self._save_article(article, classification, pair)

            return {
                "article": article,
                "news_type": classification["type"],
                "sentiment": classification["sentiment"],
                "summary": classification["summary"],
                "price_changes": changes,
                "impact_score": abs(changes.get("1h", 0)),
            }

        except Exception as e:
            logger.error(f"Failed to correlate article: {e}")
            return None

    async def _classify_news(self, article: Dict) -> Dict:
        """
        Use LLM to classify news type and sentiment.
        """
        try:
            title = article.get("title", "")
            content = article.get("content", "")[:500]

            prompt = f"""Classify this cryptocurrency news article:

Title: {title}
Content: {content}

Provide classification in JSON format:
{{
  "news_type": "<one of: regulation, partnership, hack, exchange_listing, market_analysis, whale_movement, technical_update, celebrity_mention>",
  "sentiment": "<positive, negative, or neutral>",
  "summary": "<brief 1-sentence summary>"
}}

Output only valid JSON, no other text."""

            response = await self.llm.generate(prompt)

            # Parse JSON from response
            import json

            # Extract JSON from markdown if present
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            result = json.loads(response.strip())

            return {
                "type": result.get("news_type", "market_analysis"),
                "sentiment": result.get("sentiment", "neutral"),
                "summary": result.get("summary", title[:100]),
            }

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return {
                "type": "unknown",
                "sentiment": "neutral",
                "summary": article.get("title", "Unknown")[:100],
            }

    async def _save_article(self, article: Dict, classification: Dict, pair: str):
        """Save article to database"""
        try:
            from .database import db
            from .news_models import NewsArticle

            # Create hash for deduplication
            url = article.get("url", "")
            pub_date = article.get("published_at", datetime.utcnow())
            url_hash = hashlib.sha256(f"{url}{pub_date}".encode()).hexdigest()

            with db.get_session() as session:
                # Check if exists
                existing = (
                    session.query(NewsArticle).filter(NewsArticle.url_hash == url_hash).first()
                )

                if existing:
                    return

                # Create new
                news = NewsArticle(
                    url_hash=url_hash,
                    title=article.get("title", ""),
                    url=url,
                    source=article.get("source", "Perplexica"),
                    published_at=pub_date,
                    content=article.get("content", ""),
                    summary=classification["summary"],
                    analyzed=True,
                    news_type=classification["type"],
                    sentiment=classification["sentiment"],
                    related_pair=pair,
                )

                session.add(news)
                session.commit()

        except Exception as e:
            logger.error(f"Failed to save article: {e}")

    async def _update_coefficients(self, pair: str, correlations: List[Dict]):
        """
        Update learned coefficients in database and Graphiti.
        """
        try:
            from .database import db
            from .news_models import NewsImpactCoefficient

            # Group by news type
            by_type = {}
            for corr in correlations:
                if not corr:
                    continue

                news_type = corr["news_type"]
                if news_type not in by_type:
                    by_type[news_type] = []

                by_type[news_type].append(corr)

            # Calculate averages per type
            with db.get_session() as session:
                for news_type, items in by_type.items():
                    # Get or create coefficient
                    coeff = (
                        session.query(NewsImpactCoefficient)
                        .filter(
                            NewsImpactCoefficient.pair == pair,
                            NewsImpactCoefficient.news_type == news_type,
                        )
                        .first()
                    )

                    if not coeff:
                        coeff = NewsImpactCoefficient(pair=pair, news_type=news_type)
                        session.add(coeff)

                    # Calculate averages
                    changes_1h = [
                        i["price_changes"].get("1h", 0) for i in items if "1h" in i["price_changes"]
                    ]
                    changes_4h = [
                        i["price_changes"].get("4h", 0) for i in items if "4h" in i["price_changes"]
                    ]
                    changes_24h = [
                        i["price_changes"].get("24h", 0)
                        for i in items
                        if "24h" in i["price_changes"]
                    ]

                    if changes_1h:
                        coeff.impact_1h = sum(changes_1h) / len(changes_1h)
                    if changes_4h:
                        coeff.impact_4h = sum(changes_4h) / len(changes_4h)
                    if changes_24h:
                        coeff.impact_24h = sum(changes_24h) / len(changes_24h)

                    coeff.sample_count = len(items)
                    coeff.confidence = min(len(items) / 10.0, 1.0)  # Max confidence at 10 samples
                    coeff.avg_price_change = coeff.impact_1h if coeff.impact_1h else 0

                    session.commit()

                    logger.info(
                        f"📈 {pair} {news_type}: "
                        f"1h={coeff.impact_1h:+.2f}%, "
                        f"4h={coeff.impact_4h:+.2f}%, "
                        f"24h={coeff.impact_24h:+.2f}% "
                        f"(n={coeff.sample_count}, confidence={coeff.confidence:.2f})"
                    )

            # Store in Graphiti
            await self._store_graphiti(pair, by_type)

        except Exception as e:
            logger.error(f"Failed to update coefficients: {e}")

    async def _store_graphiti(self, pair: str, coefficients: Dict):
        """Store coefficients in Graphiti memory (per trading pair)"""
        try:
            # Build knowledge text
            knowledge = f"News impact analysis for {pair}:\n\n"

            for news_type, items in coefficients.items():
                if not items:
                    continue

                changes_1h = [
                    i["price_changes"].get("1h", 0) for i in items if "1h" in i["price_changes"]
                ]
                if changes_1h:
                    avg_1h = sum(changes_1h) / len(changes_1h)
                    knowledge += (
                        f"- {news_type}: {avg_1h:+.2f}% average impact in 1h (n={len(items)})\n"
                    )

            knowledge += f"\nLast updated: {datetime.utcnow().isoformat()}"

            # Store using pair as user_id (per-pair memory)
            await self.graphiti.add_episode(
                user_id=pair.replace("/", "_"),  # BTC_USDT
                content=knowledge,
                metadata={
                    "type": "news_coefficients",
                    "pair": pair,
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )

            logger.info(f"💾 Stored coefficients in Graphiti for {pair}")

        except Exception as e:
            logger.error(f"Failed to store in Graphiti: {e}")
