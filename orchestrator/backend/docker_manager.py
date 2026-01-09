"""
Docker Manager for Freqtrade Bot Instances

Manages lifecycle of Freqtrade Docker containers.
"""

import docker
from docker.errors import DockerException, NotFound
from typing import Dict, List, Optional, Any
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class DockerManager:
    """
    Manages Docker containers for Freqtrade bot instances
    """

    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
            logger.info("Docker client connected successfully")
        except DockerException as e:
            logger.error(f"Failed to connect to Docker: {e}")
            raise

    def spawn_bot(
        self,
        bot_id: int,
        bot_name: str,
        pair: str,
        timeframe: str,
        mode: str,
        params: Dict[str, Any],
    ) -> str:
        """
        Spawn a new Freqtrade bot container

        Args:
            bot_id: Database ID of the bot
            bot_name: Unique name for the bot
            pair: Trading pair (e.g., BTC/USDT)
            timeframe: Timeframe (e.g., 15m, 1h)
            mode: demo or real
            params: Bot parameters (RSI, stop-loss, etc.)

        Returns:
            Container ID
        """
        # Generate bot config
        bot_config = self._generate_bot_config(
            pair=pair, timeframe=timeframe, mode=mode, params=params
        )

        # Save config to volume
        config_path = Path(f"user_data/configs/{bot_name}_config.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(bot_config, f, indent=2)

        # Container configuration
        container_config = {
            "image": "freqtrade/freqtrade:stable",
            "name": f"freqtrade-{bot_name}",
            "detach": True,
            "command": [
                "trade",
                "--strategy",
                "GraphitiHybridStrategy",
                "--config",
                f"/freqtrade/user_data/configs/{bot_name}_config.json",
            ],
            "volumes": {str(Path.cwd()): {"bind": "/freqtrade", "mode": "rw"}},
            "environment": {"BOT_ID": str(bot_id), "BOT_NAME": bot_name},
            "network_mode": "host",  # For local API access
        }

        try:
            container = self.client.containers.run(**container_config)
            logger.info(f"Started bot container: {container.id[:12]} for {bot_name}")
            return container.id

        except Exception as e:
            logger.error(f"Failed to spawn bot {bot_name}: {e}")
            raise

    def stop_bot(self, container_id: str) -> bool:
        """
        Stop a running bot container

        Args:
            container_id: Container ID

        Returns:
            True if stopped successfully
        """
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=10)
            logger.info(f"Stopped bot container: {container_id[:12]}")
            return True

        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            return False
        except Exception as e:
            logger.error(f"Error stopping container {container_id}: {e}")
            return False

    def remove_bot(self, container_id: str) -> bool:
        """
        Remove a bot container

        Args:
            container_id: Container ID

        Returns:
            True if removed successfully
        """
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True)
            logger.info(f"Removed bot container: {container_id[:12]}")
            return True

        except NotFound:
            logger.warning(f"Container not found: {container_id}")
            return True  # Already removed
        except Exception as e:
            logger.error(f"Error removing container {container_id}: {e}")
            return False

    def get_bot_status(self, container_id: str) -> Dict[str, Any]:
        """
        Get status of a bot container

        Args:
            container_id: Container ID

        Returns:
            Status information
        """
        try:
            container = self.client.containers.get(container_id)

            return {
                "status": container.status,
                "running": container.status == "running",
                "created": container.attrs["Created"],
                "started_at": container.attrs["State"].get("StartedAt"),
                "logs_tail": container.logs(tail=50).decode("utf-8"),
            }

        except NotFound:
            return {"status": "not_found", "running": False}
        except Exception as e:
            logger.error(f"Error getting status for {container_id}: {e}")
            return {"status": "error", "running": False, "error": str(e)}

    def list_all_bots(self) -> List[Dict[str, Any]]:
        """
        List all Freqtrade bot containers

        Returns:
            List of container info
        """
        try:
            containers = self.client.containers.list(all=True, filters={"name": "freqtrade-"})

            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                }
                for c in containers
            ]

        except Exception as e:
            logger.error(f"Error listing containers: {e}")
            return []

    def _generate_bot_config(
        self, pair: str, timeframe: str, mode: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate Freqtrade configuration for a bot

        Returns:
            Bot configuration dict
        """
        is_dry_run = mode == "demo"

        config = {
            "strategy": "GraphitiHybridStrategy",
            "exchange": {
                "name": "kucoin",
                "key": "",  # Will be loaded from global config
                "secret": "",
                "password": "",
                "ccxt_config": {},
                "ccxt_async_config": {},
                "pair_whitelist": [pair],
                "pair_blacklist": [],
            },
            "dry_run": is_dry_run,
            "stake_currency": "USDT",
            "stake_amount": params.get("max_position_size", 100.0),
            "tradable_balance_ratio": 0.99,
            "timeframe": timeframe,
            # Order types
            "order_types": {
                "entry": "limit",
                "exit": "limit",
                "stoploss": "market",
                "stoploss_on_exchange": False,
            },
            # Strategy-specific parameters
            "strategy_opts": {
                "rsi_period": params.get("rsi_period", 14),
                "rsi_oversold": params.get("rsi_oversold", 30),
                "rsi_overbought": params.get("rsi_overbought", 70),
                "min_impact_score": params.get("min_impact_score", 0.3),
                "news_check_interval": params.get("news_check_interval", 3600),
            },
            # Risk management
            "stoploss": params.get("stop_loss", -0.05),
            "trailing_stop": True,
            "trailing_stop_positive": 0.01,
            "trailing_stop_positive_offset": 0.02,
            # API
            "api_server": {
                "enabled": True,
                "listen_ip_address": "0.0.0.0",
                "listen_port": 8080 + int(params.get("bot_id", 0)),  # Unique port per bot
                "username": "freqtrade",
                "password": "freqtrade",
            },
            # Logging
            "verbosity": 3,
        }

        return config
