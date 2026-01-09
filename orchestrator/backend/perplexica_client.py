"""
Perplexica News Client

Client for querying the Perplexica AI news search service.
"""

import aiohttp
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class NewsResult(BaseModel):
    """News search result"""

    title: str
    content: str
    url: Optional[str] = None
    published_at: Optional[str] = None
    relevance_score: float = 0.0


class PerplexicaClient:
    """
    Async client for Perplexica News Search API

    Usage:
        client = PerplexicaClient(url="http://localhost:3001")
        results = await client.search_news("BTC price analysis")
    """

    def __init__(self, url: str, api_key: Optional[str] = None):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def search_news(
        self,
        query: str,
        limit: int = 5,
        focus: str = "news",  # news, academic, reddit, youtube
    ) -> List[NewsResult]:
        """
        Search for news using Perplexica

        Args:
            query: Search query (e.g., "Bitcoin price movement analysis")
            limit: Maximum number of results
            focus: Search focus type

        Returns:
            List of news results
        """
        search_data = {"query": query, "focus": focus, "limit": limit}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/api/search",
                    json=search_data,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    # Parse response
                    results = []
                    for item in data.get("results", [])[:limit]:
                        results.append(
                            NewsResult(
                                title=item.get("title", ""),
                                content=item.get("content", ""),
                                url=item.get("url"),
                                published_at=item.get("published_at"),
                                relevance_score=item.get("relevance_score", 0.0),
                            )
                        )

                    return results

        except Exception as e:
            logger.error(f"Error searching Perplexica: {e}")
            return []

    async def search_crypto_news(self, pair: str, timeframe: str = "24h") -> List[NewsResult]:
        """
        Search for crypto-specific news

        Args:
            pair: Trading pair (e.g., BTC/USDT)
            timeframe: Time window (e.g., 24h, 7d)

        Returns:
            List of news results
        """
        # Extract base currency
        base_currency = pair.split("/")[0]

        query = f"{base_currency} cryptocurrency news price analysis last {timeframe}"

        return await self.search_news(query, limit=5)

    async def summarize_news(self, news_results: List[NewsResult]) -> str:
        """
        Create a concise summary of news results

        Args:
            news_results: List of news results

        Returns:
            Summary string
        """
        if not news_results:
            return "No recent news found."

        summary_parts = []
        for i, result in enumerate(news_results[:3], 1):
            summary_parts.append(f"{i}. {result.title}: {result.content[:150]}...")

        return "\n".join(summary_parts)
