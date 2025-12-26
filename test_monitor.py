"""
Test script for market monitoring system.
Monitors a few markets and logs price updates.
"""

import asyncio
import structlog
from config.settings import get_settings
from src.core.client import PolymarketClient
from src.core.market_selector import MarketSelector, SelectionStrategy
from src.core.market_monitor import MarketMonitor, PriceUpdate

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)


def on_price_update(update: PriceUpdate) -> None:
    """Handle price update events."""
    if update.price_change_pct is not None:
        change_pct = update.price_change_pct * 100
        logger.info(
            "price_update",
            token_id=update.token_id[:16] + "...",
            price=f"{update.price:.4f}",
            change_pct=f"{change_pct:+.2f}%"
        )


async def main():
    """Run market monitoring test."""
    try:
        # Load settings
        logger.info("loading_configuration")
        settings = get_settings()
        
        # Initialize client
        logger.info("initializing_client")
        client = PolymarketClient(settings.polymarket)
        await client.connect()
        
        # Create market selector (start with random for testing)
        logger.info("creating_market_selector", strategy="random", max_markets=5)
        selector = MarketSelector(
            strategy=SelectionStrategy.RANDOM,
            max_markets=5  # Start with just 5 for testing
        )
        
        # Create monitor
        logger.info("creating_market_monitor")
        monitor = MarketMonitor(
            client=client,
            selector=selector,
            poll_interval=settings.trading.poll_interval,
            price_history_window=60
        )
        
        # Register price update callback
        monitor.on_price_update(on_price_update)
        
        # Start monitoring
        logger.info("starting_monitor", duration_seconds=30)
        logger.info("press_ctrl_c_to_stop")
        
        # Run for 30 seconds
        monitor_task = asyncio.create_task(monitor.start())
        
        try:
            await asyncio.wait_for(monitor_task, timeout=30.0)
        except asyncio.TimeoutError:
            logger.info("test_duration_complete")
            await monitor.stop()
        
        logger.info("test_completed")
        
    except KeyboardInterrupt:
        logger.info("interrupted_by_user")
    except Exception as e:
        logger.error(
            "test_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        raise


if __name__ == "__main__":
    asyncio.run(main())
