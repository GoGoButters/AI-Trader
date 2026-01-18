"""
LLM Client - OpenAI-compatible API

Supports any OpenAI-compatible endpoint (LiteLLM, vLLM, etc.)
"""

import aiohttp
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Async LLM client for OpenAI-compatible APIs.

    Usage:
        client = LLMClient(
            provider="openai",
            api_key="sk-...",
            model="gpt-3.5-turbo",
            api_base="http://192.168.1.107:4000/v1"
        )
        response = await client.generate("Classify this news...")
    """

    def __init__(self, provider: str, api_key: str, model: str, api_base: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.api_base = api_base or "https://api.openai.com/v1"

        logger.info(f"LLM Client initialized: {model} @ {self.api_base}")

    async def generate(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Generate text from prompt using chat completions API.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text
        """
        url = f"{self.api_base}/chat/completions"

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful AI assistant that provides concise, accurate responses.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"LLM API error {response.status}: {error_text}")
                        raise Exception(f"LLM API returned {response.status}: {error_text}")

                    result = await response.json()

                    # Extract response
                    if "choices" in result and len(result["choices"]) > 0:
                        message = result["choices"][0].get("message", {})
                        content = message.get("content", "")

                        logger.debug(f"LLM response: {content[:100]}...")
                        return content
                    else:
                        logger.error(f"Unexpected LLM response format: {result}")
                        raise Exception("Invalid response format from LLM")

        except aiohttp.ClientError as e:
            logger.error(f"LLM API connection error: {e}")
            raise Exception(f"Failed to connect to LLM API: {e}")
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    async def close(self):
        """Cleanup resources"""
        logger.debug("LLM client closed")
