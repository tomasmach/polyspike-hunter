"""
Debug script to investigate failing token_ids.
"""
import asyncio
from py_clob_client.client import ClobClient
from config.settings import get_settings

# One of the consistently failing token_ids from the logs
FAILING_TOKEN = "74723706519877609373623799208202568829122196737291324809410942080543598808002"

async def debug_token():
    """Debug a specific token to see why it fails."""
    settings = get_settings()

    print(f"Investigating token: {FAILING_TOKEN}")
    print(f"Using host: {settings.polymarket.host}")
    print()

    # Create client
    print("Creating CLOB client...")
    client = ClobClient(
        host=settings.polymarket.host,
        key=settings.polymarket.private_key,
        chain_id=settings.polymarket.chain_id,
    )
    print("Client created successfully")
    print()

    # Try to get last trade price
    print("Attempting to fetch last trade price...")
    try:
        result = client.get_last_trade_price(FAILING_TOKEN)
        print(f"Success! Result: {result}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

        # Print the full exception chain
        if hasattr(e, '__cause__') and e.__cause__:
            print(f"  Caused by: {type(e.__cause__).__name__}: {e.__cause__}")

        if hasattr(e, '__context__') and e.__context__:
            print(f"  Context: {type(e.__context__).__name__}: {e.__context__}")

        # Print traceback
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_token())
