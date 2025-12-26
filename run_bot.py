#!/usr/bin/env python3
"""
Quick launcher for PolySpike Hunter bot.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run main
from main import main
import asyncio

if __name__ == "__main__":
    print("PolySpike Hunter - Paper Trading Mode")
    print("=" * 60)
    print("Configuration:")
    print(f"  Initial Balance: ${os.getenv('INITIAL_BALANCE', '100.0')}")
    print(f"  Spike Threshold: {float(os.getenv('SPIKE_THRESHOLD', '0.03'))*100:.0f}%")
    print(f"  Position Size: ${os.getenv('POSITION_SIZE', '5.0')}")
    print(f"  Max Markets: {os.getenv('MAX_MONITORED_MARKETS', '50')}")
    print("=" * 60)
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
