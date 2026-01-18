"""
SearXNG Client - Direct API integration for news search

Replaces Perplexica with direct SearXNG API calls for better reliability.
"""

import aiohttp
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


class SearXNGClient:
    """
    Async client for SearXNG API.

    Directly queries SearXNG for news instead of going through Perplexica.
    """

    def __init__(self, base_url: str = "http://searxng:8080"):
        self.base_url = base_url.rstrip("/")
        logger.info(f"🔍 SearXNG client initialized: {self.base_url}")

    async def search(
        self,
        query: str,
        categories: str = "news",
        time_range: str = "week",
        language: str = "en",
        limit: int = 10,
        # Perplexica compatibility parameters
        focus_mode: str = None,  # Alias for categories (Perplexica API compatibility)
    ) -> list[dict]:
        """
        Search for news articles using SearXNG.

        Args:
            query: Search query
            categories: Categories to search (news, general, etc.)
            time_range: Time range (day, week, month, year)
            language: Language code
            limit: Maximum results
            focus_mode: Perplexica API compatibility - maps to categories

        Returns:
            List of articles with title, url, content, etc.
        """
        # Map focus_mode to categories for Perplexica compatibility
        if focus_mode:
            categories = focus_mode  # "news" -> "news"

        url = f"{self.base_url}/search"

        params = {
            "q": query,
            "categories": categories,
            "format": "json",
            "language": language,
            "time_range": time_range,
        }

        try:
            logger.debug(f"🔍 SearXNG search: '{query}' (categories={categories})")

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"SearXNG API error {response.status}: {error_text[:200]}")
                        return []

                    result = await response.json()

                    # Parse SearXNG results
                    articles = []
                    results_data = result.get("results", [])

                    for item in results_data[:limit]:
                        try:
                            article = {
                                "title": item.get("title", "Untitled"),
                                "url": item.get("url", ""),
                                "content": item.get("content", item.get("snippet", "")),
                                "source": item.get("engine", "SearXNG"),
                                "published_at": self._parse_date(item.get("publishedDate")),
                            }

                            if article["url"]:
                                articles.append(article)
                        except Exception as e:
                            logger.warning(f"Failed to parse article: {e}")
                            continue

                    logger.info(f"✅ SearXNG returned {len(articles)} articles for '{query}'")
                    return articles

        except aiohttp.ClientError as e:
            logger.error(f"SearXNG connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}", exc_info=True)
            return []

    def _parse_date(self, date_value) -> datetime:
        """Parse date from various formats"""
        if isinstance(date_value, datetime):
            return date_value

        if isinstance(date_value, str):
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(date_value.split(".")[0].split("+")[0], fmt)
                except ValueError:
                    continue

        return datetime.utcnow()

    async def close(self):
        """Cleanup resources"""
        logger.debug("SearXNG client closed")


# Alias for backward compatibility
PerplexicaClient = SearXNGClient
