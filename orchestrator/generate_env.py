#!/usr/bin/env python3
"""
Generate Environment Files for Docker Services

Reads config.yml and generates .env files for Perplexica and other services
that need configuration before container startup.

Usage:
    python generate_env.py

This should be run before `docker-compose up` to ensure all services
have the correct configuration from the centralized config.yml.
"""

import sys
import json
import uuid
import hashlib
import yaml
from pathlib import Path


def load_config(config_path: str = "config.yml") -> dict:
    """Load configuration from config.yml"""
    # Try paths relative to script location and project root
    paths_to_try = [
        config_path,
        Path(__file__).parent / config_path,
        Path(__file__).parent.parent / config_path,
        Path(__file__).parent.parent.parent / config_path,
    ]

    for path in paths_to_try:
        if Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)

    raise FileNotFoundError(f"config.yml not found in any of: {paths_to_try}")


def generate_perplexica_env(config: dict, output_dir: str = "orchestrator") -> str:
    """
    Generate .env file for Perplexica container.

    Perplexica uses these environment variables:
    - OPENAI_API_KEY / OPENAI_BASE_URL for LLM
    - Transformers for local embeddings (or custom OpenAI-compatible)
    - SEARXNG_URL for search backend
    """
    services = config.get("services", {})
    perplexica = services.get("perplexica", {})
    searxng = services.get("searxng", "")

    # Parse SearXNG URL
    if isinstance(searxng, str):
        # Parse "url: http://...; api_key: ..." format
        searxng_url = "http://searxng:8080"
        for part in searxng.split(";"):
            if "url:" in part:
                searxng_url = part.split("url:")[1].strip()
    else:
        searxng_url = searxng.get("url", "http://searxng:8080")

    # Get Perplexica LLM config
    llm_config = perplexica.get("llm", {}) if isinstance(perplexica, dict) else {}
    embedding_config = (
        perplexica.get("embeddings", {}) if isinstance(perplexica, dict) else {}
    )

    env_lines = [
        "# Perplexica Environment Configuration",
        "# Auto-generated from config.yml - DO NOT EDIT MANUALLY",
        "",
        "# SearXNG Backend",
        f"SEARXNG_API_URL={searxng_url}",
        "",
        "# LLM Configuration (OpenAI-compatible)",
        f"OPENAI_API_KEY={llm_config.get('api_key', '')}",
        f"OPENAI_BASE_URL={llm_config.get('base_url', 'https://api.openai.com/v1')}",
        "",
    ]

    # Write to file
    output_path = Path(output_dir) / "perplexica.env"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(env_lines))

    print(f"[OK] Generated: {output_path}")
    return str(output_path)


def generate_perplexica_config(config: dict, output_dir: str = "orchestrator") -> str:
    """
    Generate config.json for Perplexica with custom models.

    This pre-configures Perplexica with:
    - OpenAI provider pointing to LiteLLM proxy
    - Custom chat and embedding models from config.yml
    """
    services = config.get("services", {})
    perplexica = services.get("perplexica", {})
    searxng = services.get("searxng", "")

    # Parse SearXNG URL
    if isinstance(searxng, str):
        searxng_url = "http://searxng:8080"
        for part in searxng.split(";"):
            if "url:" in part:
                searxng_url = part.split("url:")[1].strip()
    else:
        searxng_url = searxng.get("url", "http://searxng:8080")

    # Get model configs
    llm_config = perplexica.get("llm", {}) if isinstance(perplexica, dict) else {}
    embedding_config = (
        perplexica.get("embeddings", {}) if isinstance(perplexica, dict) else {}
    )

    # Generate deterministic UUID from config hash
    config_hash = hashlib.md5(
        f"{llm_config.get('base_url', '')}{llm_config.get('api_key', '')}".encode()
    ).hexdigest()
    provider_id = str(uuid.UUID(config_hash[:32]))

    # Build Perplexica config.json
    perplexica_config = {
        "version": 1,
        "setupComplete": True,
        "preferences": {"theme": "dark"},
        "personalization": {},
        "modelProviders": [
            {
                "id": provider_id,
                "name": "AI-Trader LLM",
                "type": "openai",
                "config": {
                    "apiKey": llm_config.get("api_key", ""),
                    "baseURL": llm_config.get("base_url", "https://api.openai.com/v1"),
                },
                "chatModels": [
                    {
                        "name": llm_config.get("model", "openai/openai-reasoning"),
                        "key": llm_config.get("model", "openai/openai-reasoning"),
                    }
                ],
                "embeddingModels": [
                    {
                        "name": embedding_config.get("model", "text-embedding-3-small"),
                        "key": embedding_config.get("model", "text-embedding-3-small"),
                    }
                ],
                "hash": config_hash,
            }
        ],
        "search": {"searxngURL": searxng_url},
    }

    # Write to perplexica data directory
    output_path = Path(output_dir) / "perplexica-config" / "config.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(perplexica_config, f, indent=2)

    print(f"[OK] Generated: {output_path}")
    print(f"     - Provider: AI-Trader LLM ({llm_config.get('base_url', '')})")
    print(f"     - Chat Model: {llm_config.get('model', 'N/A')}")
    print(f"     - Embedding Model: {embedding_config.get('model', 'N/A')}")

    return str(output_path)


def generate_orchestrator_env(config: dict, output_dir: str = "orchestrator") -> str:
    """
    Generate .env file for Orchestrator container.
    """
    env_lines = [
        "# Orchestrator Environment Configuration",
        "# Auto-generated from config.yml - DO NOT EDIT MANUALLY",
        "",
        "PYTHONUNBUFFERED=1",
        "",
    ]

    output_path = Path(output_dir) / "orchestrator.env"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(env_lines))

    print(f"[OK] Generated: {output_path}")
    return str(output_path)


def main():
    """Generate all environment files from config.yml"""
    print("[*] Generating environment files from config.yml...")
    print()

    try:
        # Find project root (where config.yml is)
        script_dir = Path(__file__).parent
        project_root = script_dir.parent  # orchestrator -> AI-Trader-develop

        config_path = project_root / "config.yml"
        if not config_path.exists():
            config_path = script_dir / "config.yml"

        config = load_config(str(config_path))

        # Generate files in orchestrator directory
        output_dir = script_dir

        generate_perplexica_env(config, output_dir)
        generate_perplexica_config(config, output_dir)
        generate_orchestrator_env(config, output_dir)

        print()
        print("[OK] All environment files generated successfully!")
        print()
        print("Now run: docker-compose up -d --build")

    except FileNotFoundError as e:
        print(f"[ERROR] Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
