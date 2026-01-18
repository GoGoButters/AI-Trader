"""
Centralized Logging Configuration

Configures DEBUG-level logging for all components with:
- Detailed formatters
- File rotation
- Color-coded console output
"""

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(log_level: str = "DEBUG"):
    """
    Setup comprehensive logging for the entire application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Create logs directory
    log_dir = Path("/app/logs")
    log_dir.mkdir(exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # 1. Console Handler (with colors)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    console_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. File Handler (rotating, 10MB per file, keep 5 files)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "orchestrator.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-40s | %(funcName)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 3. Separate file for errors only
    error_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "errors.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)

    # 4. Component-specific loggers
    _configure_component_loggers()

    logging.info("=" * 80)
    logging.info("🚀 Logging system initialized")
    logging.info(f"📊 Log level: {log_level}")
    logging.info(f"📁 Log directory: {log_dir}")
    logging.info("=" * 80)


def _configure_component_loggers():
    """Configure specific loggers for different components"""

    # Paper Trading
    paper_logger = logging.getLogger("backend.paper_trading")
    paper_logger.setLevel(logging.DEBUG)

    paper_manager_logger = logging.getLogger("backend.paper_trading_manager")
    paper_manager_logger.setLevel(logging.DEBUG)

    # News Analysis
    news_corr_logger = logging.getLogger("backend.news_correlation")
    news_corr_logger.setLevel(logging.DEBUG)

    news_proc_logger = logging.getLogger("backend.news_processor")
    news_proc_logger.setLevel(logging.DEBUG)

    # Docker Manager
    docker_logger = logging.getLogger("backend.docker_manager")
    docker_logger.setLevel(logging.DEBUG)

    # API
    api_logger = logging.getLogger("backend.api")
    api_logger.setLevel(logging.DEBUG)

    # LLM Client
    llm_logger = logging.getLogger("backend.llm_client")
    llm_logger.setLevel(logging.DEBUG)

    # External libraries (reduce noise)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.INFO)

    logging.debug("✅ Component loggers configured")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Module name (usually __name__)

    Returns:
        Configured logger
    """
    return logging.getLogger(name)
