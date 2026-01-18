"""
News Analysis Service
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

from .database import db
from .models import BotInstance
from .news_models import NewsImpact
from .perplexica_client import PerplexicaClient
from .graphiti_client import GraphitiClient
from .llm_client import LLMClient
from .config_parser import get_config

logger = logging.getLogger(__name__)


class NewsAnalyzer:
    def __init__(self):
        self.config = get_config()
        self.running = False
        self._init_clients()

    def _init_clients(self):
        # Perplexica
        p_conf = self.config.get_service("perplexica")
        self.perplexica = PerplexicaClient(p_conf.url)

        # Graphiti
        g_conf = self.config.get_service("graphiti")
        self.graphiti = GraphitiClient(g_conf.url, g_conf.api_key)

        # LLM
        m_conf = self.config.get_model("primary_analysis")
        # Fallback if primary_analysis not found, use openrouter/xiaomi/mimo-v2-flash:free default
        api_base = m_conf.api_base if m_conf else "https://openrouter.ai/api/v1"
        api_key = m_conf.api_key if m_conf else "sk-or-..."

        self.llm = LLMClient(api_base, api_key)
        self.model_name = m_conf.model if m_conf else "openrouter/xiaomi/mimo-v2-flash:free"

    async def start(self):
        """Start background analysis loop"""
        self.running = True
        logger.info("Starting News Analyzer Service...")

        while self.running:
            try:
                await self.analyze_cycle()
            except Exception as e:
                logger.error(f"Error in news analysis cycle: {e}")

            # Wait for 15 minutes before next cycle
            await asyncio.sleep(900)

    async def analyze_cycle(self):
        """Run one analysis cycle for all active pairs"""
        pairs = self._get_active_pairs()
        if not pairs:
            pairs = ["BTC/USDT"]  # Default

        for pair in pairs:
            await self._process_pair(pair)

    def _get_active_pairs(self) -> List[str]:
        """Get unique pairs from active bots"""
        try:
            with db.get_session() as session:
                bots = session.query(BotInstance).filter(BotInstance.status == "running").all()
                return list(set(b.pair for b in bots))
        except Exception as e:
            logger.error(f"DB Error getting pairs: {e}")
            return []

    async def _process_pair(self, pair: str):
        logger.info(f"Analyzing news for {pair}...")

        # 1. Search News
        news_items = await self.perplexica.search_crypto_news(pair)
        if not news_items:
            return

        for item in news_items:
            # Check if already processed (simple check by loading recent)
            # In a real app we'd check DB by URL or title hash

            # Analyze
            analysis = await self._analyze_news_item(pair, item)

            if analysis["impact_score"] == 0.0 and analysis["confidence"] == 0.0:
                continue

            # Save to DB
            self._save_result(pair, item, analysis)

            # Save to Graphiti
            await self.graphiti.add_impact_memory(
                pair=pair,
                news_title=item.title,
                impact_score=analysis["impact_score"],
                news_category=analysis["news_category"],
                source=item.url or "unknown",
                additional_data=analysis,
            )

    async def _analyze_news_item(self, pair: str, item) -> dict:
        prompt = f"""Analyze this crypto news for {pair}:

Title: {item.title}
Content: {item.content[:1000]}

Provide JSON output with:
1. "impact_score": float (-1.0 to 1.0)
2. "confidence": float (0.0 to 1.0)
3. "news_category": string (listing/regulation/partnership/hack/macro/tech/other)
4. "summary": string (1 sentence)
5. "ai_sentiment": string (positive/negative/neutral)
"""
        return await self.llm.analyze_json(prompt, self.model_name)

    def _save_result(self, pair: str, item, analysis: dict):
        try:
            with db.get_session() as session:
                # Check for duplicate by title recently
                exists = (
                    session.query(NewsImpact)
                    .filter(NewsImpact.pair == pair, NewsImpact.title == item.title)
                    .first()
                )

                if exists:
                    return

                news = NewsImpact(
                    pair=pair,
                    title=item.title,
                    summary=analysis.get("summary"),
                    source_url=item.url,
                    source_name="Perplexica Search",
                    impact_score=analysis.get("impact_score", 0.0),
                    confidence=analysis.get("confidence", 0.0),
                    news_category=analysis.get("news_category", "other"),
                    ai_sentiment=analysis.get("ai_sentiment", "neutral"),
                    raw_data=analysis,
                )
                session.add(news)
                session.commit()
                logger.info(f"Saved news impact: {item.title} ({analysis.get('impact_score')})")
        except Exception as e:
            logger.error(f"Error saving news to DB: {e}")
