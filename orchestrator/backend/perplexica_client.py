"""
Perplexica Client - Real AI-Powered Search Integration

Uses the actual Perplexica API for AI-enhanced news search.
https://github.com/ItzCrazyKns/Perplexica
"""

import aiohttp
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class PerplexicaClient:
    """
    Real Perplexica AI-powered search client.

    Perplexica provides AI-enhanced search that:
    - Uses LLMs to understand queries
    - Synthesizes answers from multiple sources
    - Returns structured results with sources
    """

    def __init__(
        self,
        base_url: str = "http://perplexica-search:3000",
        chat_provider_id: str = None,
        chat_model_key: str = "gpt-4o-mini",
        embedding_provider_id: str = None,
        embedding_model_key: str = "text-embedding-3-small",
    ):
        self.base_url = base_url.rstrip("/")
        self.chat_provider_id = chat_provider_id
        self.chat_model_key = chat_model_key
        self.embedding_provider_id = embedding_provider_id
        self.embedding_model_key = embedding_model_key

        # Will be populated by discover_providers
        self._providers_cache = None

        logger.info(
            f"🔍 Perplexica client initialized: {self.base_url} "
            f"(chat: {chat_model_key}, embedding: {embedding_model_key})"
        )

    async def discover_providers(self) -> Dict:
        """
        Discover available providers and their models from Perplexica.

        Returns:
            Dict with 'providers' list containing available models
        """
        url = f"{self.base_url}/api/providers"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to get providers: {response.status}")
                        return {"providers": []}

                    data = await response.json()
                    self._providers_cache = data

                    # Auto-configure provider IDs and models if not set
                    for provider in data.get("providers", []):
                        # Find provider with chat models for chat
                        if not self.chat_provider_id and provider.get("chatModels"):
                            self.chat_provider_id = provider["id"]
                            # Also auto-select the first chat model
                            first_chat = provider["chatModels"][0]
                            self.chat_model_key = first_chat["key"]
                            logger.info(
                                f"\ud83d\udccc Auto-selected chat: {provider['name']} / {self.chat_model_key}"
                            )

                        # Find provider with embedding models
                        if not self.embedding_provider_id and provider.get(
                            "embeddingModels"
                        ):
                            self.embedding_provider_id = provider["id"]
                            # Also auto-select the first embedding model
                            first_embed = provider["embeddingModels"][0]
                            self.embedding_model_key = first_embed["key"]
                            logger.info(
                                f"\ud83d\udccc Auto-selected embedding: {provider['name']} / {self.embedding_model_key}"
                            )

                    return data

        except Exception as e:
            logger.error(f"Failed to discover providers: {e}")
            return {"providers": []}

    async def search(
        self,
        query: str,
        sources: List[str] = None,
        optimization_mode: str = "speed",
        focus_mode: str = None,  # Backward compatibility
        time_range: str = None,  # For compatibility, not used by Perplexica
        limit: int = 10,  # For compatibility
    ) -> List[Dict]:
        """
        Perform AI-enhanced search using Perplexica.

        Args:
            query: Search query
            sources: Sources to search (web, academic, discussions)
            optimization_mode: speed, balanced, or quality
            focus_mode: Backward compatibility (maps to sources)

        Returns:
            List of articles with title, url, content, source, and AI summary
        """
        # Auto-discover providers if not configured
        if not self.chat_provider_id or not self.embedding_provider_id:
            await self.discover_providers()

        if not self.chat_provider_id:
            logger.error("No chat provider available in Perplexica")
            return []

        # Default sources
        if sources is None:
            sources = ["web"]

        # Map focus_mode for backward compatibility
        if focus_mode == "news":
            sources = ["web"]  # Perplexica doesn't have "news" category

        url = f"{self.base_url}/api/search"

        payload = {
            "chatModel": {
                "providerId": self.chat_provider_id,
                "key": self.chat_model_key,
            },
            "embeddingModel": {
                "providerId": self.embedding_provider_id or self.chat_provider_id,
                "key": self.embedding_model_key,
            },
            "sources": sources,
            "query": query,
            "optimizationMode": optimization_mode,
            "stream": False,
        }

        try:
            logger.debug(f"🔍 Perplexica search: '{query}' (sources={sources})")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),  # AI search can be slow
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            f"Perplexica API error {response.status}: {error_text[:500]}"
                        )
                        return []

                    result = await response.json()

                    # Parse Perplexica response
                    articles = []

                    # The AI-generated message is the main result
                    ai_message = result.get("message", "")
                    sources_data = result.get("sources", [])

                    # Convert sources to article format
                    for source in sources_data[:limit]:
                        try:
                            metadata = source.get("metadata", {})
                            article = {
                                "title": metadata.get("title", "Untitled"),
                                "url": metadata.get("url", ""),
                                "content": source.get("content", ""),
                                "source": "Perplexica",
                                "published_at": datetime.utcnow(),  # Perplexica doesn't provide dates
                                "ai_summary": ai_message[:500] if ai_message else None,
                            }

                            if article["url"]:
                                articles.append(article)
                        except Exception as e:
                            logger.warning(f"Failed to parse source: {e}")
                            continue

                    logger.info(
                        f"✅ Perplexica returned {len(articles)} sources for '{query}' "
                        f"(AI summary: {len(ai_message)} chars)"
                    )
                    return articles

        except aiohttp.ClientError as e:
            logger.error(f"Perplexica connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"Perplexica search failed: {e}", exc_info=True)
            return []

    async def close(self):
        """Cleanup resources"""
        logger.debug("Perplexica client closed")


# For backward compatibility with existing code
SearXNGClient = PerplexicaClient
