"""
FastAPI Routes for Bot Management

Refactored to use custom trading engine (PaperTradingManager) instead of Freqtrade/Docker.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import asyncio
import logging

from ..database import get_db
from ..models import BotInstance, BotParams
from ..paper_trading_manager import paper_trading_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots", tags=["bots"])


class ExchangeConfig(BaseModel):
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""


class BotParamsSchema(BaseModel):
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    stop_loss: float = -0.05
    take_profit: float = 0.10
    max_position_size: float = 100.0
    enable_ai_analysis: bool = True
    news_check_interval: int = 3600
    min_impact_score: float = 0.3
    initial_balance: float = 1000.0
    exchange_config: ExchangeConfig = ExchangeConfig()


class CreateBotRequest(BaseModel):
    name: str
    pair: str
    timeframe: str = "1h"
    mode: str = "demo"  # All bots are now paper trading
    trading_mode: str = "spot"  # spot, margin, futures
    leverage: int = 1  # 1-125x
    params: BotParamsSchema = BotParamsSchema()


class BotResponse(BaseModel):
    id: int
    name: str
    pair: str
    timeframe: str
    status: str
    mode: str
    current_profit: float
    total_trades: int
    created_at: datetime
    container_id: Optional[str] = None  # Kept for compatibility but unused

    class Config:
        from_attributes = True


@router.post("/create", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(request: CreateBotRequest, db: Session = Depends(get_db)):
    """
    Create and start a new bot instance using custom trading engine.
    """
    # Check if bot name already exists
    existing = db.query(BotInstance).filter(BotInstance.name == request.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bot with name '{request.name}' already exists",
        )

    # Create bot instance in database
    bot = BotInstance(
        name=request.name,
        pair=request.pair,
        timeframe=request.timeframe,
        mode="demo",  # All bots run in paper trading mode
        trading_mode=request.trading_mode,
        leverage=request.leverage,
        status="starting",
    )

    db.add(bot)
    db.flush()  # Get bot ID

    # Create bot parameters
    params = BotParams(
        bot_id=bot.id,
        rsi_period=request.params.rsi_period,
        rsi_oversold=request.params.rsi_oversold,
        rsi_overbought=request.params.rsi_overbought,
        stop_loss=request.params.stop_loss,
        take_profit=request.params.take_profit,
        max_position_size=request.params.max_position_size,
        enable_ai_analysis=request.params.enable_ai_analysis,
        news_check_interval=request.params.news_check_interval,
        min_impact_score=request.params.min_impact_score,
        custom_params=request.params.exchange_config.dict(),
    )

    db.add(params)
    db.commit()

    # Start paper trading bot
    try:
        await paper_trading_manager.start_bot(
            bot_id=bot.id,
            pair=bot.pair,
            timeframe=bot.timeframe,
            initial_balance=request.params.initial_balance,
            trading_mode=bot.trading_mode,
            leverage=bot.leverage,
            params=request.params.dict(),
        )

        bot.status = "running"
        bot.started_at = datetime.utcnow()
        db.commit()

        # Trigger Historical Analysis (Background Task)
        try:
            from ..history_analyzer import start_historical_analysis

            # Store task reference to prevent garbage collection
            task = asyncio.create_task(
                start_historical_analysis(bot_id=bot.id, pair=bot.pair, days=10)
            )
            # Don't await - let it run in background
            logger.info(f"📜 Triggered 10-day historical analysis for bot {bot.id}")
        except Exception as e:
            logger.error(f"❌ Failed to trigger history analysis: {e}")

        db.refresh(bot)
        return bot

    except Exception as e:
        bot.status = "error"
        db.commit()
        logger.error(f"Failed to start bot {bot.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start trading bot: {str(e)}",
        )


@router.get("/list", response_model=List[BotResponse])
async def list_bots(db: Session = Depends(get_db)):
    """
    List all bot instances
    """
    bots = db.query(BotInstance).all()
    return bots


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Get a specific bot instance
    """
    bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot with ID {bot_id} not found"
        )

    return bot


@router.post("/{bot_id}/start")
async def start_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Start a stopped bot
    """
    bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot with ID {bot_id} not found"
        )

    if bot.status == "running":
        return {"message": "Bot is already running", "status": "running"}

    # Reload params
    params_obj = db.query(BotParams).filter(BotParams.bot_id == bot_id).first()

    # Convert SQLAlchemy model to dict
    params_dict = {}
    if params_obj:
        for key, value in params_obj.__dict__.items():
            if not key.startswith("_"):
                params_dict[key] = value

    try:
        await paper_trading_manager.start_bot(
            bot_id=bot.id,
            pair=bot.pair,
            timeframe=bot.timeframe,
            initial_balance=params_dict.get("max_position_size", 1000),
            trading_mode=bot.trading_mode,
            leverage=bot.leverage,
            params=params_dict,
        )

        bot.status = "running"
        bot.started_at = datetime.utcnow()
        db.commit()

        return {"message": "Bot started successfully", "status": "running"}

    except Exception as e:
        bot.status = "error"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start bot: {str(e)}",
        )


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Stop a running bot
    """
    bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot with ID {bot_id} not found"
        )

    if bot.status != "running":
        return {"message": "Bot is not running", "status": bot.status}

    try:
        await paper_trading_manager.stop_bot(bot_id)

        bot.status = "stopped"
        bot.stopped_at = datetime.utcnow()
        db.commit()

        return {"message": "Bot stopped successfully", "status": "stopped"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop bot: {str(e)}",
        )


@router.delete("/{bot_id}")
async def delete_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Delete a bot instance
    """
    bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot with ID {bot_id} not found"
        )

    # Stop bot if running
    if bot.status == "running":
        try:
            await paper_trading_manager.stop_bot(bot_id)
        except Exception:
            pass  # Ignore errors during cleanup

    # Delete from database (cascade will delete params)
    db.delete(bot)
    db.commit()

    return {"message": f"Bot {bot.name} deleted successfully"}


@router.get("/{bot_id}/status")
async def get_bot_status(bot_id: int, db: Session = Depends(get_db)):
    """
    Get detailed status of a bot
    """
    bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot with ID {bot_id} not found"
        )

    # Get paper trading status
    engine = paper_trading_manager.get_engine(bot_id)

    trading_status = None
    if engine:
        try:
            portfolio = await engine.get_portfolio_value()
            trading_status = {
                "is_running": bot_id in paper_trading_manager.running_bots,
                "portfolio_value": portfolio,
            }
        except Exception:
            trading_status = {"is_running": False, "error": "Failed to get status"}

    return {"bot": bot, "trading_status": trading_status}


@router.get("/{bot_id}/candles")
async def get_bot_candles(
    bot_id: int,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    """
    Get candlestick data for a bot's trading pair
    """
    bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot with ID {bot_id} not found"
        )

    # Use bot's pair and timeframe if not provided
    pair = pair or bot.pair
    timeframe = timeframe or bot.timeframe

    try:
        candles = await paper_trading_manager.get_candles(bot_id, limit)

        # If no candles from manager (bot not running), fetch directly
        if not candles:
            candles = await paper_trading_manager.fetch_candles_direct(pair, timeframe, limit)

        return candles
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch candles: {str(e)}",
        )


@router.get("/{bot_id}/trades")
async def get_bot_trades(bot_id: int, limit: int = 100, db: Session = Depends(get_db)):
    """
    Get trade history for a bot
    """
    bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()

    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Bot with ID {bot_id} not found"
        )

    try:
        trades = await paper_trading_manager.get_bot_trades(bot_id, limit)
        return {"trades": trades}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch trades: {str(e)}",
        )
