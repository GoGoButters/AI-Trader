"""
FastAPI Routes for Bot Management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db
from ..models import BotInstance, BotParams, TradingSignal
from ..docker_manager import DockerManager

router = APIRouter(prefix="/api/bots", tags=["bots"])
docker_manager = DockerManager()


# Pydantic schemas for API
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


class CreateBotRequest(BaseModel):
    name: str
    pair: str
    timeframe: str = "15m"
    mode: str = "demo"  # demo or real
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
    container_id: str | None

    class Config:
        from_attributes = True


@router.post("/create", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(request: CreateBotRequest, db: Session = Depends(get_db)):
    """
    Create and start a new bot instance
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
        mode=request.mode,
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
    )

    db.add(params)
    db.commit()

    # Start Docker container
    try:
        container_id = docker_manager.spawn_bot(
            bot_id=bot.id,
            bot_name=bot.name,
            pair=bot.pair,
            timeframe=bot.timeframe,
            mode=bot.mode,
            params=request.params.dict(),
        )

        # Update bot with container ID
        bot.container_id = container_id
        bot.status = "running"
        bot.started_at = datetime.utcnow()
        db.commit()

        db.refresh(bot)
        return bot

    except Exception as e:
        # Update status to error
        bot.status = "error"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start bot: {str(e)}",
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
    params = db.query(BotParams).filter(BotParams.bot_id == bot_id).first()

    try:
        container_id = docker_manager.spawn_bot(
            bot_id=bot.id,
            bot_name=bot.name,
            pair=bot.pair,
            timeframe=bot.timeframe,
            mode=bot.mode,
            params=params.__dict__ if params else {},
        )

        bot.container_id = container_id
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

    if not bot.container_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Bot has no associated container"
        )

    # Stop Docker container
    success = docker_manager.stop_bot(bot.container_id)

    if success:
        bot.status = "stopped"
        bot.stopped_at = datetime.utcnow()
        db.commit()
        return {"message": "Bot stopped successfully", "status": "stopped"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to stop bot container"
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

    # Stop and remove container if running
    if bot.container_id:
        docker_manager.stop_bot(bot.container_id)
        docker_manager.remove_bot(bot.container_id)

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

    # Get Docker status if container exists
    docker_status = None
    if bot.container_id:
        docker_status = docker_manager.get_bot_status(bot.container_id)

    return {"bot": bot, "docker_status": docker_status}
