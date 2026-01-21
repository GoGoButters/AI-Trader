"""
AI-Trader Orchestrator - FastAPI Main Application

Simplified version that works with existing config_parser.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config_parser import get_config
from .database import db
from .api import bots

# Initialize logging
from .logging_config import setup_logging

setup_logging(log_level="DEBUG")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting...")

    try:
        config = get_config()
        logger.info(f"✅ Config loaded: port={config.orchestrator.api_port}")

        db.init()
        logger.info("✅ Database initialized")

        # Initialize paper trading manager (always available)
        from .paper_trading_manager import paper_trading_manager

        logger.info("✅ Paper trading ready")

        # Auto-restart running demo bots
        try:
            from .models import BotInstance

            with db.get_session() as session:
                running_bots = (
                    session.query(BotInstance)
                    .filter(BotInstance.status == "running", BotInstance.mode == "demo")
                    .all()
                )

                for bot in running_bots:
                    try:
                        await paper_trading_manager.start_bot(
                            bot_id=bot.id,
                            pair=bot.pair,
                            timeframe=bot.timeframe,
                            initial_balance=1000,
                            trading_mode=bot.trading_mode or "spot",
                            leverage=bot.leverage or 1,
                            params={},
                        )
                        logger.info(f"✅ Restarted paper bot {bot.id}: {bot.name}")
                    except Exception as e:
                        logger.error(f"❌ Failed to restart bot {bot.id}: {e}")
        except Exception as e:
            logger.warning(f"⚠️  Bot auto-restart failed: {e}")

        # Initialize AI clients if configured
        global llm_client, perplexica_client, graphiti_client
        llm_client = None
        perplexica_client = None
        graphiti_client = None

        try:
            # Try to get model config for LLM
            try:
                from .llm_client import LLMClient

                primary_model = config.get_model("primary_analysis")
                llm_client = LLMClient(
                    provider="openai",
                    api_key=primary_model.api_key,
                    model=primary_model.model,
                    api_base=primary_model.api_base,
                )
                logger.info(f"✅ LLM client: {primary_model.model}")
            except Exception as e:
                logger.warning(f"⚠️  LLM client not initialized: {e}")

            # Initialize Perplexica AI-powered search
            try:
                from .perplexica_client import PerplexicaClient

                # Get Perplexica service config
                perplexica_svc = config.get_service("perplexica")
                perplexica_url = (
                    perplexica_svc.url
                    if perplexica_svc
                    else "http://perplexica-search:3000"
                )

                # Use GPT-4o-mini for fast searches, text-embedding-3-small for embeddings
                perplexica_client = PerplexicaClient(
                    base_url=perplexica_url,
                    chat_model_key="gpt-4o-mini",
                    embedding_model_key="text-embedding-3-small",
                )

                # Auto-discover and configure providers
                await perplexica_client.discover_providers()
                logger.info(f"✅ Perplexica AI search: {perplexica_url}")
            except Exception as e:
                logger.warning(f"⚠️  Perplexica client not initialized: {e}")

            # Try to get Graphiti config
            try:
                from .graphiti_client import GraphitiClient

                graphiti_svc = config.get_service("graphiti")
                graphiti_client = GraphitiClient(
                    url=graphiti_svc.url,
                    api_key=graphiti_svc.token or graphiti_svc.api_key or "",
                )
                logger.info(f"✅ Graphiti client: {graphiti_svc.url}")
            except Exception as e:
                logger.warning(f"⚠️  Graphiti client not initialized: {e}")

            # Log AI status
            if llm_client and perplexica_client and graphiti_client:
                logger.info("✅ All AI clients ready - news analysis enabled")

                # Initialize Global News Processor
                from .news_processor import init_news_processor

                news_proc = init_news_processor(
                    llm_client, perplexica_client, graphiti_client
                )

                # CRITICAL: Link news processor to paper trading manager
                paper_trading_manager.set_news_processor(news_proc)
                logger.info("🔗 News processor linked to paper trading")

            else:
                logger.info("⚠️  Some AI clients missing - news analysis disabled")
                from .news_processor import news_processor  # Ensure it exists as None

        except Exception as e:
            logger.warning(f"⚠️  AI client initialization failed: {e}")
            from .news_processor import news_processor  # Safe fallback

        logger.info("✅ READY")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise

    yield

    logger.info("⏹️  Stopping...")
    try:
        from .paper_trading_manager import paper_trading_manager

        await paper_trading_manager.cleanup()

        # Cleanup news processor
        if news_processor:
            await news_processor.cleanup()
    except:
        pass
    logger.info("👋 Stopped")


app = FastAPI(title="AI-Trader Orchestrator", version="2.0.0", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(bots.router)

# Add news router
from .api import news

app.include_router(news.router)

# Add logs router for real-time logging
from .api import logs

app.include_router(logs.router)

# Add keys router for API keys management
from .api import keys

app.include_router(keys.router)


@app.get("/")
async def root():
    return {"message": "AI-Trader Orchestrator", "version": "2.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
