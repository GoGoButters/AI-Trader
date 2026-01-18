"""Create paper trading bot from inside container"""

import sys

sys.path.insert(0, "/app")

from backend.database import db
from backend.models import BotInstance
from backend.paper_trading_manager import paper_trading_manager
import asyncio


async def create_bot():
    # Initialize DB
    db.init()

    # Create bot record
    with db.get_session() as session:
        bot = BotInstance(
            name="Paper ETH Bot",
            pair="ETH/USDT",
            timeframe="15m",
            mode="demo",
            trading_mode="spot",
            leverage=1,
            status="running",
        )
        session.add(bot)
        session.commit()
        session.refresh(bot)
        bot_id = bot.id
        print(f"✅ Created bot ID: {bot_id}")

    # Start paper trading
    await paper_trading_manager.start_bot(
        bot_id=bot_id,
        pair="ETH/USDT",
        timeframe="15m",
        initial_balance=1000.0,
        trading_mode="spot",
        leverage=1,
        params={},
    )
    print(f"✅ Paper trading started for bot {bot_id}")


if __name__ == "__main__":
    asyncio.run(create_bot())
