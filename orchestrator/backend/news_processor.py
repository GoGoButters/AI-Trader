"""
Real-time News Processor

Periodically fetches, analyzes, and responds to news in real-time.
Adjusts bot strategies based on learned impact coefficients.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class NewsProcessor:
    """
    Real-time news processing and strategy adjustment.

    Runs periodic tasks to:
    - Fetch new news from Perplexica
    - Filter already processed articles
    - Score impact using learned coefficients
    - Adjust bot strategies dynamically
    """

    def __init__(self, llm_client, perplexica_client, graphiti_client):
        self.llm = llm_client
        self.perplexica = perplexica_client
        self.graphiti = graphiti_client

        self.tasks: Dict[int, asyncio.Task] = {}

        logger.info("📰 NewsProcessor initialized")

    async def start_for_bot(
        self,
        bot_id: int,
        pair: str,
        timeframe: str,
        enable_hard_influence: bool = False,
    ):
        """Start real-time news processing for a bot"""
        if bot_id in self.tasks:
            logger.warning(f"📰 Bot {bot_id}: News processor already running")
            return

        logger.info(
            f"📰 Bot {bot_id}: Starting news processor "
            f"(pair={pair}, timeframe={timeframe}, hard_influence={enable_hard_influence})"
        )

        task = asyncio.create_task(
            self._processing_loop(bot_id, pair, timeframe, enable_hard_influence)
        )

        self.tasks[bot_id] = task
        logger.info(f"✅ Bot {bot_id}: News processor started")

    async def stop_for_bot(self, bot_id: int):
        """Stop news processing for a bot"""
        if bot_id not in self.tasks:
            logger.debug(f"📰 Bot {bot_id}: News processor not running")
            return

        logger.info(f"⏹️  Bot {bot_id}: Stopping news processor")

        self.tasks[bot_id].cancel()

        try:
            await self.tasks[bot_id]
        except asyncio.CancelledError:
            pass

        del self.tasks[bot_id]
        logger.info(f"✅ Bot {bot_id}: News processor stopped")

    async def _processing_loop(
        self, bot_id: int, pair: str, timeframe: str, enable_hard_influence: bool
    ):
        """
        Main processing loop - runs periodically based on timeframe.
        """
        interval = self._timeframe_to_seconds(timeframe)

        logger.info(
            f"📰 Bot {bot_id}: Processing loop started "
            f"(check every {interval}s = {interval // 60}min)"
        )

        iteration = 0

        while True:
            try:
                iteration += 1
                logger.debug(f"📰 Bot {bot_id}: Processing iteration #{iteration}")

                # 1. Fetch recent news
                lookback_minutes = interval // 60 + 5  # Add 5min buffer
                news = await self._fetch_recent_news(pair, lookback_minutes)

                logger.debug(f"📰 Bot {bot_id}: Fetched {len(news)} articles")

                if not news:
                    logger.debug(
                        f"📰 Bot {bot_id}: No news in last {lookback_minutes}min"
                    )
                    await asyncio.sleep(interval)
                    continue

                # 2. Filter new articles (dedup)
                new_articles = await self._filter_new(news)

                if not new_articles:
                    logger.debug(f"📰 Bot {bot_id}: All articles already processed")
                    await asyncio.sleep(interval)
                    continue

                logger.info(
                    f"📰 Bot {bot_id}: Processing {len(new_articles)} new articles "
                    f"({len(news) - len(new_articles)} duplicates filtered)"
                )

                # 3. Process each article
                for i, article in enumerate(new_articles, 1):
                    logger.debug(
                        f"📰 Bot {bot_id}: Article {i}/{len(new_articles)}: "
                        f"{article.get('title', 'Untitled')[:60]}"
                    )

                    await self._process_article(
                        bot_id, pair, article, enable_hard_influence
                    )

                logger.info(f"✅ Bot {bot_id}: Processed {len(new_articles)} articles")

                # 4. Sleep until next cycle
                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info(f"📰 Bot {bot_id}: Processing loop cancelled")
                raise
            except Exception as e:
                logger.error(
                    f"❌ Bot {bot_id}: Error in processing loop: {e}", exc_info=True
                )
                # Wait before retry
                await asyncio.sleep(60)

    async def _fetch_recent_news(self, pair: str, minutes: int) -> List[Dict]:
        """Fetch news from last N minutes"""
        try:
            base = pair.split("/")[0]
            query = f"{base} cryptocurrency news"

            start_time = datetime.utcnow() - timedelta(minutes=minutes)

            logger.debug(
                f"📰 Fetching news: query='{query}', since={start_time.isoformat()}"
            )

            results = await self.perplexica.search(
                query=query, focus_mode="news", time_range="week"
            )

            # Filter by time
            filtered = []
            for article in results:
                pub_date = article.get("published_at")
                if pub_date and pub_date >= start_time:
                    filtered.append(article)

            logger.debug(
                f"📰 Perplexica returned {len(results)} articles, {len(filtered)} within timeframe"
            )

            return filtered

        except Exception as e:
            logger.error(f"❌ Failed to fetch news: {e}")
            return []

    async def _filter_new(self, articles: List[Dict]) -> List[Dict]:
        """Filter out already processed articles"""
        from .database import db
        from .news_models import NewsArticle

        new_articles = []

        try:
            with db.get_session() as session:
                for article in articles:
                    # Create hash
                    url = article.get("url", "")
                    pub_date = article.get("published_at", datetime.utcnow())
                    url_hash = hashlib.sha256(f"{url}{pub_date}".encode()).hexdigest()

                    # Check if exists
                    exists = (
                        session.query(NewsArticle)
                        .filter(NewsArticle.url_hash == url_hash)
                        .first()
                    )

                    if not exists:
                        new_articles.append(article)
                        logger.debug(f"📰 New article: {article.get('title', '')[:60]}")
                    else:
                        logger.debug(f"📰 Duplicate (hash={url_hash[:8]}...)")

            return new_articles

        except Exception as e:
            logger.error(f"❌ Failed to filter articles: {e}")
            return articles  # Return all if filter fails

    async def _process_article(
        self, bot_id: int, pair: str, article: Dict, enable_hard_influence: bool
    ):
        """Process single article and adjust strategy if needed"""
        try:
            title = article.get("title", "Untitled")
            logger.debug(f"📰 Bot {bot_id}: Processing '{title[:60]}'")

            # 1. Classify with Graphiti context
            classification = await self._classify_with_context(pair, article)

            logger.debug(
                f"📰 Bot {bot_id}: Classification: "
                f"type={classification['type']}, "
                f"sentiment={classification['sentiment']}, "
                f"predicted_impact={classification.get('predicted_impact', 'unknown')}"
            )

            # 2. Get learned coefficient
            from .database import db
            from .news_models import NewsImpactCoefficient

            impact_1h = 0
            confidence = 0

            with db.get_session() as session:
                coeff = (
                    session.query(NewsImpactCoefficient)
                    .filter(
                        NewsImpactCoefficient.pair == pair,
                        NewsImpactCoefficient.news_type == classification["type"],
                    )
                    .first()
                )

                if coeff:
                    impact_1h = float(coeff.impact_1h or 0)
                    confidence = float(coeff.confidence or 0)

                    logger.debug(
                        f"📊 Bot {bot_id}: Coefficient found: "
                        f"impact_1h={impact_1h:+.2f}%, "
                        f"confidence={confidence:.2f}, "
                        f"samples={coeff.sample_count}"
                    )
                else:
                    logger.debug(
                        f"📊 Bot {bot_id}: No coefficient for {classification['type']}"
                    )

            # 3. Decide if adjustment needed
            if confidence < 0.3:
                logger.debug(
                    f"📰 Bot {bot_id}: Skipping adjustment (low confidence: {confidence:.2f})"
                )
                # Still save article for future learning
                await self._save_article(article, classification, pair)
                return

            # 4. Adjust strategy if significant impact
            abs_impact = abs(impact_1h)

            if (
                abs_impact > 0.2
            ):  # >0.2% expected movement (lowered from 1.5% for realistic data)
                logger.info(
                    f"💡 Bot {bot_id}: Adjusting strategy "
                    f"(impact={impact_1h:+.2f}%, confidence={confidence:.2f})"
                )

                await self._adjust_strategy(
                    bot_id, classification, impact_1h, enable_hard_influence
                )
            else:
                logger.debug(
                    f"📰 Bot {bot_id}: Impact too low ({abs_impact:.2f}% < 0.2% threshold)"
                )

            # 5. Save article
            await self._save_article(article, classification, pair)

        except Exception as e:
            logger.error(
                f"❌ Bot {bot_id}: Failed to process article: {e}", exc_info=True
            )

    async def _classify_with_context(self, pair: str, article: Dict) -> Dict:
        """Classify news with Graphiti historical context"""
        try:
            title = article.get("title", "")
            content = article.get("content", "")[:500]

            # Load context from Graphiti
            logger.debug(f"🔍 Loading Graphiti context for {pair}")

            context_results = await self.graphiti.search(
                user_id=pair.replace("/", "_"), query=title, limit=3
            )

            context = (
                "\n".join([r.get("content", "") for r in context_results])
                if context_results
                else "No historical context"
            )

            logger.debug(f"💾 Graphiti context: {len(context)} chars")

            # LLM classification with context
            prompt = f"""You are analyzing cryptocurrency news with historical context.

Historical patterns for {pair}:
{context}

New article:
Title: {title}
Content: {content}

Classify and predict impact:

Output JSON:
{{
  "news_type": "<regulation|partnership|hack|exchange_listing|market_analysis|whale_movement|technical_update|celebrity_mention>",
  "sentiment": "<positive|negative|neutral>",
  "summary": "<1 sentence summary>",
  "predicted_impact": "<high|medium|low>"
}}

Output ONLY valid JSON, no other text."""

            logger.debug("🤖 Calling LLM for classification")

            response = await self.llm.generate(prompt)

            # Parse JSON
            import json

            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            result = json.loads(response.strip())

            logger.debug(
                f"✅ LLM classification: "
                f"type={result.get('news_type')}, "
                f"sentiment={result.get('sentiment')}"
            )

            return {
                "type": result.get("news_type", "market_analysis"),
                "sentiment": result.get("sentiment", "neutral"),
                "summary": result.get("summary", title[:100]),
                "predicted_impact": result.get("predicted_impact", "low"),
            }

        except Exception as e:
            logger.error(f"❌ LLM classification failed: {e}")
            return {
                "type": "unknown",
                "sentiment": "neutral",
                "summary": article.get("title", "Unknown")[:100],
                "predicted_impact": "low",
            }

    async def _adjust_strategy(
        self,
        bot_id: int,
        classification: Dict,
        impact: float,
        enable_hard_influence: bool,
    ):
        """Adjust bot strategy based on news impact"""
        try:
            from .database import db
            from .models import BotParams
            from .news_models import NewsStrategyAdjustment

            with db.get_session() as session:
                params = (
                    session.query(BotParams).filter(BotParams.bot_id == bot_id).first()
                )

                if not params:
                    logger.warning(f"⚠️  Bot {bot_id}: No params found")
                    return

                # Soft influence: Adjust RSI thresholds
                adjustment_made = False
                adj_type = "soft"
                action = ""
                old_value = 0
                new_value = 0

                if impact > 0.2:  # Positive news (lowered from 1.5%)
                    # Lower buy threshold (buy earlier)
                    old_value = params.rsi_oversold
                    new_value = max(20, old_value - 5)

                    if new_value != old_value:
                        params.rsi_oversold = new_value
                        action = "rsi_oversold_decrease"
                        adjustment_made = True

                        logger.info(
                            f"📈 Bot {bot_id}: RSI oversold {old_value} → {new_value} "
                            f"(positive {classification['type']})"
                        )

                elif impact < -0.2:  # Negative news (lowered from -1.5%)
                    # Raise sell threshold (sell earlier)
                    old_value = params.rsi_overbought
                    new_value = min(80, old_value - 5)

                    if new_value != old_value:
                        params.rsi_overbought = new_value
                        action = "rsi_overbought_decrease"
                        adjustment_made = True

                        logger.info(
                            f"📉 Bot {bot_id}: RSI overbought {old_value} → {new_value} "
                            f"(negative {classification['type']})"
                        )

                # Hard influence: Force action for critical news
                if enable_hard_influence and abs(impact) > 1.0:  # Lowered from 4.0%
                    adj_type = "hard"

                    if impact > 0:
                        action = "force_buy_signal"
                        logger.warning(
                            f"🚨 Bot {bot_id}: FORCE BUY signal "
                            f"(critical positive news: impact={impact:+.2f}%)"
                        )
                    else:
                        action = "force_sell_signal"
                        logger.warning(
                            f"🚨 Bot {bot_id}: FORCE SELL signal "
                            f"(critical negative news: impact={impact:+.2f}%)"
                        )

                    adjustment_made = True
                    # TODO: Implement force action via API call to paper_trading_manager

                # Log adjustment
                if adjustment_made:
                    adjustment = NewsStrategyAdjustment(
                        bot_id=bot_id,
                        adjustment_type=adj_type,
                        action=action,
                        old_value=old_value,
                        new_value=new_value,
                    )
                    session.add(adjustment)

                session.commit()

        except Exception as e:
            logger.error(
                f"❌ Bot {bot_id}: Failed to adjust strategy: {e}", exc_info=True
            )

    async def _save_article(self, article: Dict, classification: Dict, pair: str):
        """Save article to database"""
        try:
            from .database import db
            from .news_models import NewsArticle

            url = article.get("url", "")
            pub_date = article.get("published_at", datetime.utcnow())
            url_hash = hashlib.sha256(f"{url}{pub_date}".encode()).hexdigest()

            with db.get_session() as session:
                # Double-check existence
                existing = (
                    session.query(NewsArticle)
                    .filter(NewsArticle.url_hash == url_hash)
                    .first()
                )

                if existing:
                    logger.debug(f"📰 Article already exists: {url_hash[:8]}")
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

                logger.debug(f"💾 Saved article: {news.title[:60]}")

        except Exception as e:
            logger.error(f"❌ Failed to save article: {e}")

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        """Convert timeframe string to seconds"""
        try:
            if not timeframe or len(timeframe) < 2:
                logger.warning(f"⚠️  Invalid timeframe '{timeframe}', using default 15m")
                return 900

            value = int(timeframe[:-1])
            unit = timeframe[-1].lower()

            multipliers = {"m": 60, "h": 3600, "d": 86400}

            if unit not in multipliers:
                logger.warning(f"⚠️  Unknown timeframe unit '{unit}', using default")
                return 900

            seconds = value * multipliers[unit]
            logger.debug(f"⏱️  Timeframe {timeframe} = {seconds}s")

            return seconds

        except Exception as e:
            logger.error(f"❌ Failed to parse timeframe '{timeframe}': {e}")
            return 900  # Default 15 minutes

    async def cleanup(self):
        """Stop all processors"""
        logger.info("🧹 Cleaning up news processors")

        for bot_id in list(self.tasks.keys()):
            await self.stop_for_bot(bot_id)

        logger.info("✅ News processors cleaned up")


# Global instance - will be initialized with clients
news_processor: Optional[NewsProcessor] = None


def init_news_processor(llm_client, perplexica_client, graphiti_client):
    """Initialize global news processor"""
    global news_processor

    if news_processor is None:
        news_processor = NewsProcessor(llm_client, perplexica_client, graphiti_client)
        logger.info("✅ Global news processor initialized")

    return news_processor
