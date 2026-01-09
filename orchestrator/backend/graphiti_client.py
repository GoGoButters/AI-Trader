"""
Graphiti Memory Client

Client for interacting with the Graphiti graph memory service.
"""

import aiohttp
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class GraphitiMemory(BaseModel):
    """Graphiti memory entry"""

    content: str
    entity: str
    relation: Optional[str] = None
    metadata: Dict[str, Any] = {}


class GraphitiClient:
    """
    Async client for Graphiti Memory API

    Usage:
        client = GraphitiClient(url="http://localhost:8000", token="your_token")
        await client.add_memory(pair="BTC/USDT", content="...", impact_score=0.75)
    """

    def __init__(self, url: str, token: Optional[str] = None):
        self.url = url.rstrip("/")
        self.token = token
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def add_memory(
        self,
        pair: str,
        content: str,
        impact_score: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a memory entry to Graphiti

        Args:
            pair: Trading pair (e.g., BTC/USDT)
            content: Memory content (news + analysis)
            impact_score: Calculated impact score
            metadata: Additional metadata

        Returns:
            Response from Graphiti API
        """
        memory_data = {
            "entity": pair,
            "content": content,
            "metadata": {
                "impact_score": impact_score,
                "type": "trading_signal",
                **(metadata or {}),
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/api/memory", json=memory_data, headers=self.headers
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Error adding memory to Graphiti: {e}")
            raise

    async def query_memory(self, pair: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Query historical memories for a trading pair

        Args:
            pair: Trading pair (e.g., BTC/USDT)
            limit: Maximum number of results

        Returns:
            List of memory entries
        """
        params = {"entity": pair, "limit": limit}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.url}/api/memory/search", params=params, headers=self.headers
                ) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Error querying Graphiti: {e}")
            return []

    async def get_impact_scores(self, pair: str) -> List[float]:
        """
        Get historical impact scores for a pair

        Args:
            pair: Trading pair

        Returns:
            List of impact scores
        """
        memories = await self.query_memory(pair, limit=50)

        scores = []
        for memory in memories:
            if "metadata" in memory and "impact_score" in memory["metadata"]:
                scores.append(memory["metadata"]["impact_score"])

        return scores

    async def get_average_impact(self, pair: str) -> float:
        """Calculate average impact score for a pair"""
        scores = await self.get_impact_scores(pair)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)
