"""
Perplexica Client - Complete Implementation

Async client for Perplexica news search API.
"""

import aiohttp
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PerplexicaClient:
    """
    Async client for Perplexica API.

    Usage:
        client = PerplexicaClient(base_url="http://perplexica-search:3000")
        results = await client.search("Bitcoin news", focus_mode="news")
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        logger.info(f"Perplexica client initialized: {self.base_url}")

    async def search(
        self, query: str, focus_mode: str = "news", time_range: str = "week", limit: int = 10
    ) -> List[Dict]:
        """
        Search for news articles using Perplexica.

        Args:
            query: Search query
            focus_mode: Focus mode (news, web, academic, etc.)
            time_range: Time range (day, week, month, year)
            limit: Maximum results

        Returns:
            List of articles with title, url, published_at, content
        """
        url = f"{self.base_url}/api/search"

        # Perplexica requires 'sources' parameter - use default news sources
        payload = {
            "query": query,
            "focusMode": focus_mode,
            "timeRange": time_range,
            "limit": limit,
            "sources": [],  # Empty array - Perplexica will use default sources for focus mode
        }

        try:
            logger.debug(f"Perplexica search: '{query}' (mode={focus_mode}, range={time_range})")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Perplexica API error {response.status}: {error_text}")
                        return []

                    result = await response.json()

                    # Parse results - Perplexica returns various formats
                    articles = []

                    if isinstance(result, dict):
                        results_data = result.get(
                            "results", result.get("sources", result.get("articles", []))
                        )
                    elif isinstance(result, list):
                        results_data = result
                    else:
                        logger.warning(f"Unexpected Perplexica response type: {type(result)}")
                        results_data = []

                    for item in results_data[:limit]:
                        try:
                            article = {
                                "title": item.get("title", "Untitled"),
                                "url": item.get("url", item.get("link", "")),
                                "content": item.get(
                                    "content", item.get("snippet", item.get("description", ""))
                                ),
                                "source": item.get("source", item.get("domain", "Unknown")),
                                "published_at": self._parse_date(
                                    item.get(
                                        "published_at", item.get("publishedTime", item.get("date"))
                                    )
                                ),
                            }

                            if article["url"]:
                                articles.append(article)
                        except Exception as e:
                            logger.warning(f"Failed to parse article: {e}")
                            continue

                    logger.info(f"Perplexica returned {len(articles)} articles for '{query}'")
                    return articles

        except aiohttp.ClientError as e:
            logger.error(f"Perplexica connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"Perplexica search failed: {e}", exc_info=True)
            return []

    def _parse_date(self, date_value) -> datetime:
        """Parse date from various formats"""
        if isinstance(date_value, datetime):
            return date_value

        if isinstance(date_value, str):
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(date_value.split(".")[0].split("+")[0], fmt)
                except:
                    continue

        return datetime.utcnow()

    async def close(self):
        """Cleanup resources"""
        logger.debug("Perplexica client closed")
