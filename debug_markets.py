#!/usr/bin/env python3
"""
Debug script to check what markets are available and their volumes.
"""

import asyncio
import structlog
from config.settings import get_settings
from src.core.client import PolymarketClient

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)


async def main():
    """Check available markets and their properties."""
    try:
        # Load settings
        settings = get_settings()
        
        # Initialize client
        client = PolymarketClient(settings.polymarket)
        await client.connect()
        
        print("\nFetching markets from Polymarket API...\n")
        
        # Fetch markets
        markets_data = await client.get_markets()
        all_markets = markets_data.get("data", [])
        
        print(f"Total markets fetched: {len(all_markets)}\n")
        
        # Analyze markets
        active_count = 0
        with_volume = 0
        with_tokens = 0
        volume_samples = []
        
        for market in all_markets[:100]:  # Check first 100
            active = market.get("active", False)
            if active:
                active_count += 1
            
            volume = market.get("volume", 0) or market.get("volume24hr", 0) or 0
            if volume and float(volume) > 0:
                with_volume += 1
                volume_samples.append(float(volume))
            
            tokens = market.get("tokens", [])
            if tokens and len(tokens) > 0:
                with_tokens += 1
        
        print("Market Analysis (first 100):")
        print(f"  Active markets:        {active_count}")
        print(f"  Markets with volume:   {with_volume}")
        print(f"  Markets with tokens:   {with_tokens}")
        
        if volume_samples:
            volume_samples.sort(reverse=True)
            print("\nVolume samples (top 10):")
            for i, vol in enumerate(volume_samples[:10], 1):
                print(f"  {i}. ${vol:,.2f}")
        
        # Show sample active market with tokens
        print("\nSample active markets with tokens:\n")
        count = 0
        for market in all_markets:
            if not market.get("active", False):
                continue
            
            tokens = market.get("tokens", [])
            if not tokens:
                continue
            
            question = market.get("question", "N/A")
            volume = market.get("volume", 0) or 0
            
            print(f"  [OK] {question[:60]}")
            print(f"    Volume: ${float(volume):,.2f}")
            print(f"    Tokens: {len(tokens)}")
            
            for token in tokens[:2]:  # Show first 2 tokens
                token_id = token.get("token_id", "")
                outcome = token.get("outcome", "")
                print(f"      - {outcome}: {token_id[:16]}...")
            print()
            
            count += 1
            if count >= 5:
                break
        
        client.disconnect()
        
    except Exception as e:
        logger.error("debug_failed", error=str(e), error_type=type(e).__name__)
        raise
    finally:
        if 'client' in locals() and client._client is not None:
            client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
