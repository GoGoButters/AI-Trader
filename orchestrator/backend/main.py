"""
AI-Trader Orchestrator - FastAPI Main Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .database import db
from .config_parser

 import get_config
from .api import bots

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AI-Trader Orchestrator",
    description="Orchestrator for managing AI-powered trading bots",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("Starting AI-Trader Orchestrator...")
    
    # Load configuration
    try:
        config = get_config()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise
    
    # Initialize database
    try:
        db.init()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # TODO: Auto-restart bots that were running
    logger.info("Orchestrator ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down AI-Trader Orchestrator...")


# Include routers
app.include_router(bots.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI-Trader Orchestrator API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    
    config = get_config()
    port = config.orchestrator.api_port
    
    uvicorn.run(
        "orchestrator.backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
