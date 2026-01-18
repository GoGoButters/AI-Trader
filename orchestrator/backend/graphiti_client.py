"""
Graphiti Memory Client - Updated for correct API endpoints

Client for interacting with the Graphiti graph memory service.
Uses pair names as user_id for data isolation.
"""

import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GraphitiClient:
    """
    Async client for Graphiti Memory API

    Uses trading pair as user_id for data isolation.
    Example: pair="BTC/USDT" becomes user_id="BTC_USDT"

    Usage:
        client = GraphitiClient(url="http://192.168.1.107:8001", api_key="adapter-secret-api-key")
        await client.add_impact_memory(pair="BTC/USDT", news_data={...}, impact_score=0.75)
    """

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.headers = {"Content-Type": "application/json", "X-API-KEY": api_key}

    def _pair_to_user_id(self, pair: str) -> str:
        """Convert trading pair to user_id format: BTC/USDT -> BTC_USDT

        Note: Graphiti uses this as group_id for entity isolation.
        Must be consistent across all add/search operations.
        """
        if not pair:
            return ""
        # Normalize: BTC/USDT -> BTC_USDT, btc-usdt -> BTC_USDT
        normalized = pair.upper().replace("/", "_").replace("-", "_")
        return normalized

    async def add_impact_memory(
        self,
        pair: str,
        news_title: str,
        impact_score: float,
        news_category: str,
        source: str,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add news impact analysis to Graphiti memory

        Args:
            pair: Trading pair (e.g., BTC/USDT)
            news_title: News headline
            impact_score: Calculated impact score (-1.0 to 1.0)
            news_category: Category (listing, regulation, partnership, etc.)
            source: News source
            additional_data: Additional metadata

        Returns:
            Response from Graphiti API
        """
        user_id = self._pair_to_user_id(pair)

        # Format text for memory
        text = f"News Impact: {news_title}. Category: {news_category}. Impact Score: {impact_score:.3f}"

        memory_data = {
            "user_id": user_id,
            "text": text,
            "role": "system",  # system role for automated memories
            "metadata": {
                "source": "ai_trader_bot",
                "news_category": news_category,
                "impact_score": impact_score,
                "news_source": source,
                "pair": pair,
                "timestamp": datetime.utcnow().isoformat(),
                **(additional_data or {}),
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/memory/append", json=memory_data, headers=self.headers
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    logger.info(f"Added memory for {pair}: {result.get('episode_id')}")
                    return result
        except Exception as e:
            logger.error(f"Error adding memory to Graphiti: {e}")
            raise

    async def query_impact_memories(
        self, pair: str, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query historical impact memories for a trading pair

        Args:
            pair: Trading pair (e.g., BTC/USDT)
            query: Search query
            limit: Maximum number of results

        Returns:
            List of relevant memories
        """
        user_id = self._pair_to_user_id(pair)

        logger.debug(f"Graphiti query: user_id='{user_id}' (from pair='{pair}')")

        query_data = {"user_id": user_id, "query": query, "limit": limit}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/memory/query", json=query_data, headers=self.headers
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    return result.get("results", [])
        except Exception as e:
            logger.error(f"Error querying Graphiti: {e}")
            return []

    async def get_category_coefficients(self, pair: str, category: str) -> List[float]:
        """
        Get historical impact scores for a specific news category

        Args:
            pair: Trading pair
            category: News category (listing, regulation, etc.)

        Returns:
            List of impact scores for that category
        """
        query = f"news impact {category}"
        memories = await self.query_impact_memories(pair, query, limit=50)

        scores = []
        for memory in memories:
            fact = memory.get("fact", "")
            # Extract impact score from fact text
            if "Impact Score:" in fact:
                try:
                    score_str = fact.split("Impact Score:")[1].split()[0]
                    scores.append(float(score_str))
                except:
                    pass

        return scores

    async def get_average_category_impact(self, pair: str, category: str) -> float:
        """
        Calculate average impact score for a category

        Args:
            pair: Trading pair
            category: News category

        Returns:
            Average impact score
        """
        scores = await self.get_category_coefficients(pair, category)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    async def get_user_episodes(
        self, pair: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent episodes for a pair

        Args:
            pair: Trading pair
            limit: Maximum episodes to return

        Returns:
            List of episodes
        """
        user_id = self._pair_to_user_id(pair)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.url}/memory/users/{user_id}/episodes",
                    params={"limit": limit},
                    headers=self.headers,
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    return result.get("episodes", [])
        except Exception as e:
            logger.error(f"Error getting episodes: {e}")
            return []

    # Compatibility methods for news_processor/history_analyzer
    async def add_fact(self, source: str, fact: str, user_id: str) -> Dict[str, Any]:
        """
        Add a fact to memory - compatibility alias for add_impact_memory

        Args:
            source: Source URL
            fact: Fact text to store
            user_id: User/pair identifier (will be normalized to uppercase with underscores)
        """
        # Normalize user_id to ensure consistent format: ETH_USDT -> ETH_USDT, eth-usdt -> ETH_USDT
        normalized_user_id = (
            user_id.upper().replace("/", "_").replace("-", "_") if user_id else ""
        )

        memory_data = {
            "user_id": normalized_user_id,
            "text": fact,
            "role": "system",
            "metadata": {
                "source": source,
                "timestamp": datetime.utcnow().isoformat(),
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/memory/append", json=memory_data, headers=self.headers
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    logger.debug(f"Added fact for {user_id}")
                    return result
        except Exception as e:
            logger.warning(f"Error adding fact to Graphiti: {e}")
            return {}

    async def search(
        self, pair: str = None, query: str = "", limit: int = 10, user_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Search memories - compatibility alias for query_impact_memories
        Supports both (pair, query, limit) and (user_id=, query=, limit=) calling patterns
        """
        # Support user_id kwarg for news_processor compatibility
        # If user_id is passed directly (e.g. "ETH_USDT"), convert to pair format first
        if user_id and not pair:
            # Normalize: ETH_USDT -> ETH/USDT for internal consistency
            pair = user_id.replace("_", "/")
        # query_impact_memories will use _pair_to_user_id to normalize
        return await self.query_impact_memories(pair or "", query, limit)
