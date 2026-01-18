"""
Docker Manager for Freqtrade Bot Instances

Manages lifecycle of Freqtrade Docker containers.
"""

import docker
import os
from docker.errors import DockerException, NotFound
from typing import Dict, List, Optional, Any
import logging
import json
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth

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
        trading_mode: str = "spot",
        leverage: int = 1,
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
        # Calculate unique port
        listen_port = 8080 + int(bot_id)
        # Store trading mode in params for config generation
        params["trading_mode"] = trading_mode
        params["leverage"] = leverage
        params["listen_port"] = listen_port

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
            "image": "freqtradeorg/freqtrade:stable",  # Switched to stable
            "name": f"freqtrade-{bot_name}",
            "detach": True,
            "ports": {f"{listen_port}/tcp": listen_port},
            "command": [
                "trade",
                "--strategy",
                "GraphitiHybridStrategy",
                "--config",
                f"/freqtrade/user_data/configs/{bot_name}_config.json",
            ],
            "volumes": {
                f"{os.getenv('HOST_PROJECT_PATH', str(Path.cwd()))}/user_data": {
                    "bind": "/freqtrade/user_data",
                    "mode": "rw",
                }
            },
            "environment": {"BOT_ID": str(bot_id), "BOT_NAME": bot_name},
            "network": "orchestrator_ai-trader-network",  # Connect to orchestrator network
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

        # Extract exchange keys and trading params
        exchange_config = params.get("exchange_config", {})
        trading_mode = params.get("trading_mode", "spot")
        leverage = params.get("leverage", 1)

        config = {
            "strategy": "GraphitiHybridStrategy",
            "exchange": {
                "name": "kucoin",
                "key": exchange_config.get("api_key", ""),
                "secret": exchange_config.get("api_secret", ""),
                "password": exchange_config.get("api_passphrase", ""),
                "ccxt_config": {},
                "ccxt_async_config": {},
                "pair_whitelist": [pair],
                "pair_blacklist": [],
                "options": {"defaultType": "future" if trading_mode == "futures" else "spot"},
            },
            "pairlists": [
                {"method": "StaticPairList"},
            ],
            "entry_pricing": {
                "price_side": "same",
                "use_order_book": True,
                "order_book_top": 1,
                "price_last_balance": 0.0,
                "check_depth_of_market": {
                    "enabled": False,
                    "bids_to_ask_delta": 1,
                },
            },
            "exit_pricing": {
                "price_side": "same",
                "use_order_book": True,
                "order_book_top": 1,
            },
            "dry_run": is_dry_run,
            "dry_run_wallet": params.get("dry_run_wallet", 1000),
            "stake_currency": "USDT",
            "stake_amount": params.get("max_position_size", 100.0),
            "tradable_balance_ratio": 0.99,
            "timeframe": timeframe,
            "startup_candle_count": 1000,
            # Trading mode configuration
            "trading_mode": trading_mode,
            "margin_mode": "isolated" if trading_mode != "spot" else None,
            "collateral_currency": "USDT" if trading_mode != "spot" else None,
            "liquidation_buffer": 0.05 if trading_mode == "futures" else None,
            # Leverage configuration
            "leverage": leverage if leverage > 1 else None,
            # Order types
            "order_types": {
                "entry": "limit",
                "exit": "limit",
                "stoploss": "market",
                "stoploss_on_exchange": trading_mode == "futures",
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
                "listen_port": params.get("listen_port", 8080),  # Use calculated port
                "username": "freqtrade",
                "password": "freqtrade",
                "enable_openapi": True,
                "jwt_secret_key": "supersecretjwtkey",
            },
            # Logging
            "verbosity": 3,
            # Auto-start trading when bot spawns
            "initial_state": "running",
        }

        return config

    def _get_bot_api_url(self, bot_id: int, container_id: str) -> str:
        """
        Get the API URL for a bot container

        Args:
            bot_id: Bot database ID
            container_id: Docker container ID

        Returns:
            Base API URL for the bot
        """
        try:
            container = self.client.containers.get(container_id)
            container_name = container.name
            # Use SAME port internally as externally (8080 + bot_id)
            # Freqtrade API server binds to this specific port
            port = 8080 + bot_id
            return f"http://{container_name}:{port}"
        except Exception as e:
            logger.warning(
                f"Could not get container name for {container_id}, falling back to localhost: {e}"
            )
            port = 8080 + bot_id
            return f"http://localhost:{port}"

    def send_bot_command(self, bot_id: int, command: str, container_id: str = None) -> dict:
        """
        Send command to Freqtrade bot API

        Args:
            bot_id: Bot database ID
            command: API command (start, stop, etc.)
            container_id: Optional container ID for network routing

        Returns:
            API response dict
        """
        if container_id:
            base_url = self._get_bot_api_url(bot_id, container_id)
        else:
            port = 8080 + bot_id
            base_url = f"http://localhost:{port}"

        url = f"{base_url}/api/v1/{command}"
        auth = HTTPBasicAuth("freqtrade", "freqtrade")

        try:
            response = requests.post(url, auth=auth, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to send command {command} to bot {bot_id}: {e}")
            raise

    def get_bot_candles(
        self, bot_id: int, pair: str, timeframe: str, limit: int = 500, container_id: str = None
    ) -> dict:
        """
        Get candlestick data from Freqtrade bot

        Args:
            bot_id: Bot database ID
            pair: Trading pair (e.g., BTC/USDT)
            timeframe: Candle timeframe (e.g., 1h)
            limit: Number of candles
            container_id: Optional container ID for network routing

        Returns:
            Candle data dict
        """
        if container_id:
            base_url = self._get_bot_api_url(bot_id, container_id)
        else:
            port = 8080 + bot_id
            base_url = f"http://localhost:{port}"

        url = f"{base_url}/api/v1/pair_candles"
        auth = HTTPBasicAuth("freqtrade", "freqtrade")
        params = {"pair": pair, "timeframe": timeframe, "limit": limit}

        try:
            response = requests.get(url, params=params, auth=auth, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get candles from bot {bot_id}: {e}")
            raise

    def get_bot_trades(self, bot_id: int, limit: int = 100, container_id: str = None) -> dict:
        """
        Get trade history from Freqtrade bot

        Args:
            bot_id: Bot database ID
            limit: Number of trades to fetch
            container_id: Optional container ID for network routing

        Returns:
            Trade history dict
        """
        if container_id:
            base_url = self._get_bot_api_url(bot_id, container_id)
        else:
            port = 8080 + bot_id
            base_url = f"http://localhost:{port}"

        url = f"{base_url}/api/v1/trades"
        auth = HTTPBasicAuth("freqtrade", "freqtrade")
        params = {"limit": limit}

        try:
            response = requests.get(url, params=params, auth=auth, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get trades from bot {bot_id}: {e}")
            raise
