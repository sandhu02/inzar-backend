"""Worker entrypoint for background jobs."""

import asyncio
import logging
import signal
from typing import Any

from app.core.config import settings
from app.core.logging import setup_logging

logger = logging.getLogger("inzar.worker")


async def run_worker() -> None:
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting Inzar background job worker...")

    stop_event = asyncio.Event()

    def handle_stop(*_: Any) -> None:
        logger.info("Shutdown signal received. Stopping worker...")
        stop_event.set()

    # Note: On Windows signal handlers have limited support for SIGTERM/SIGINT in asyncio
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, handle_stop)
            except (NotImplementedError, AttributeError):
                pass
    except Exception:
        pass

    logger.info("Worker initialized and listening for jobs.")
    try:
        while not stop_event.is_set():
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Worker cancelled.")


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass
