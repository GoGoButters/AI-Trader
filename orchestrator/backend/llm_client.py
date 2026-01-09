"""
LLM Client with Fallback Support

Unified client for making LLM requests with automatic fallback handling.
"""

import aiohttp
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import logging
import json

logger = logging.getLogger(__name__)


class LLMMessage(BaseModel):
    """Chat message"""

    role: str  # system, user, assistant
    content: str


class LLMResponse(BaseModel):
    """LLM response"""

    content: str
    model: str
    usage: Optional[Dict[str, int]] = None


class LLMClient:
    """
    Unified LLM client with fallback support

    Supports OpenRouter-compatible APIs and local LLM servers.
    Automatically falls back to alternative models on failure.
    """

    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str,
        fallback_model: Optional[Dict[str, str]] = None,
    ):
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.fallback_model = fallback_model

        self.headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    async def chat_completion(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        use_fallback: bool = True,
    ) -> Optional[LLMResponse]:
        """
        Send a chat completion request

        Args:
            messages: List of chat messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            use_fallback: Whether to use fallback model on failure

        Returns:
            LLM response or None on failure
        """
        request_data = {
            "model": self.model,
            "messages": [msg.dict() for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_base}/v1/chat/completions",
                    json=request_data,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    # Parse response
                    content = data["choices"][0]["message"]["content"]

                    return LLMResponse(content=content, model=self.model, usage=data.get("usage"))

        except Exception as e:
            logger.error(f"Error calling LLM {self.model}: {e}")

            # Try fallback if available
            if use_fallback and self.fallback_model:
                logger.info(f"Attempting fallback to {self.fallback_model['model']}")
                fallback_client = LLMClient(
                    model=self.fallback_model["model"],
                    api_base=self.fallback_model["api_base"],
                    api_key=self.fallback_model["api_key"],
                )
                return await fallback_client.chat_completion(
                    messages, temperature, max_tokens, use_fallback=False
                )

            return None

    async def analyze_correlation(
        self, news_summary: str, rsi_value: float, price_change: float, pair: str
    ) -> Dict[str, Any]:
        """
        Analyze correlation between news and price movement

        Args:
            news_summary: Summary of recent news
            rsi_value: Current RSI value
            price_change: Recent price change percentage
            pair: Trading pair

        Returns:
            Analysis result with impact score
        """
        prompt = f"""Analyze the correlation between news and price movement for {pair}.

News Summary:
{news_summary}

Technical Indicators:
- RSI: {rsi_value}
- Price Change: {price_change:.2f}%

Task: Determine the IMPACT SCORE (0.0 to 1.0) of how much the news influenced the price movement.
Consider:
1. News sentiment (positive/negative/neutral)
2. News relevance to {pair}
3. Correlation with price movement direction
4. RSI confirmation of trend

Respond in JSON format:
{{
  "impact_score": <float 0.0-1.0>,
  "sentiment": "<positive|negative|neutral>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<brief explanation>"
}}"""

        messages = [
            LLMMessage(
                role="system",
                content="You are a crypto market analyst. Respond only with valid JSON.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        response = await self.chat_completion(messages, temperature=0.3, max_tokens=500)

        if not response:
            return {
                "impact_score": 0.0,
                "sentiment": "neutral",
                "confidence": 0.0,
                "reasoning": "Analysis failed",
            }

        try:
            # Try to parse JSON response
            result = json.loads(response.content)
            return result
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response: {response.content}")
            return {
                "impact_score": 0.0,
                "sentiment": "neutral",
                "confidence": 0.0,
                "reasoning": "Failed to parse response",
            }

    async def generate_trading_signal(
        self,
        pair: str,
        rsi: float,
        news_summary: str,
        impact_score: float,
        historical_avg_impact: float,
    ) -> Dict[str, Any]:
        """
        Generate trading decision based on all available data

        Returns:
            Trading signal with recommendation
        """
        prompt = f"""Generate a trading signal for {pair}.

Technical Analysis:
- RSI: {rsi}

AI Analysis:
- Recent News: {news_summary[:200]}...
- Current Impact Score: {impact_score:.2f}
- Historical Average Impact: {historical_avg_impact:.2f}

Based on this data, should we BUY, SELL, or HOLD?

Respond in JSON:
{{
  "action": "<buy|sell|hold>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<brief explanation>"
}}"""

        messages = [
            LLMMessage(
                role="system",
                content="You are a crypto trading advisor. Respond only with valid JSON.",
            ),
            LLMMessage(role="user", content=prompt),
        ]

        response = await self.chat_completion(messages, temperature=0.2, max_tokens=300)

        if not response:
            return {"action": "hold", "confidence": 0.0, "reasoning": "Analysis failed"}

        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"action": "hold", "confidence": 0.0, "reasoning": "Failed to parse response"}
