"""
Test script to verify Polymarket client connection and authentication.
Run this to ensure API keys are configured correctly.
"""

import asyncio
import structlog
from config.settings import get_settings
from src.core.client import PolymarketClient

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)


async def test_connection():
    """Test Polymarket client connection and basic operations."""
    try:
        # Load settings from .env
        logger.info("loading_configuration")
        settings = get_settings()
        
        # Initialize client
        logger.info("initializing_polymarket_client")
        client = PolymarketClient(settings.polymarket)
        
        # Connect to API
        logger.info("connecting_to_polymarket_api")
        await client.connect()
        
        # Test: Fetch markets
        logger.info("testing_market_fetch")
        markets = await client.get_markets()
        logger.info(
            "markets_fetched_successfully",
            market_count=len(markets.get("data", []))
        )
        
        # Display first 3 markets as example
        if markets.get("data"):
            logger.info("sample_markets")
            for market in markets["data"][:3]:
                logger.info(
                    "market",
                    question=market.get("question"),
                    condition_id=market.get("condition_id")
                )
        
        # Disconnect
        client.disconnect()
        logger.info("test_completed_successfully")
        
    except ValueError as e:
        logger.exception(
            "configuration_error",
            hint="Make sure POLYMARKET_PRIVATE_KEY is set in .env file"
        )
        return False
    except Exception as e:
        logger.exception(
            "test_failed",
        )
        return False
    
    return True


if __name__ == "__main__":
    logger.info("starting_connection_test")
    success = asyncio.run(test_connection())
    if success:
        logger.info("All tests passed! Configuration is correct.")
    else:
        logger.error("Tests failed. Check configuration and API keys.")
