"""Entry point for JARVIS MK1 Lite.

This module provides the main entry point for the JARVIS MK1 Lite bot,
including structured logging configuration and graceful shutdown handling.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

from jarvis_mk1_lite.bot import JarvisBot
from jarvis_mk1_lite.config import get_settings

if TYPE_CHECKING:
    from jarvis_mk1_lite.config import Settings


def configure_structlog(log_level: str) -> None:
    """Configure structlog for structured logging.

    Args:
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR).
    """
    # Configure standard logging first
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def setup_logging(level: str) -> None:
    """Configure logging (legacy function for backward compatibility).

    Args:
        level: Logging level string.
    """
    configure_structlog(level)


async def shutdown(bot: JarvisBot, timeout: int = 30) -> None:
    """Gracefully shutdown the bot with timeout.

    Args:
        bot: The JarvisBot instance to shut down.
        timeout: Maximum time to wait for shutdown in seconds (default: 30).
    """
    logger = structlog.get_logger(__name__)
    logger.info("Initiating graceful shutdown...", timeout=timeout)

    try:
        await asyncio.wait_for(bot.stop(), timeout=timeout)
        logger.info("Bot stopped successfully")
    except TimeoutError:
        logger.warning("Shutdown timed out after seconds", seconds=timeout)
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


async def main() -> None:
    """Main entry point for JARVIS MK1 Lite.

    Initializes settings, configures logging, sets up signal handlers,
    and starts the bot with graceful shutdown support.
    """
    # Load settings
    try:
        settings: Settings = get_settings()
    except Exception as e:
        print(f"Failed to load settings: {e}")
        print("Make sure .env file exists with required variables.")
        sys.exit(1)

    # Configure structured logging
    configure_structlog(settings.log_level)
    logger = structlog.get_logger(__name__)

    # Log startup information
    logger.info(
        "Starting JARVIS MK1 Lite",
        app_name=settings.app_name,
        version=settings.app_version,
        model=settings.claude_model,
        workspace=settings.workspace_dir,
        allowed_users=len(settings.allowed_user_ids),
    )

    # Create bot instance
    bot = JarvisBot(settings)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler(sig: signal.Signals) -> None:
        logger.info("Received signal", signal=sig.name)
        shutdown_event.set()

    # Register signal handlers (Unix signals)
    def make_handler(s: signal.Signals) -> Callable[[], None]:
        return lambda: signal_handler(s)

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            # Windows doesn't support add_signal_handler
            loop.add_signal_handler(sig, make_handler(sig))

    try:
        # Start bot polling in background
        bot_task = asyncio.create_task(bot.start())

        # Wait for shutdown signal or bot completion
        done, pending = await asyncio.wait(
            [bot_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        raise
    finally:
        await shutdown(bot, timeout=settings.shutdown_timeout)
        logger.info("Shutdown complete")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
