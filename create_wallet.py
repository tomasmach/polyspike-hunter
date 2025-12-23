"""
Helper script to create a new Polygon wallet for testing.
WARNING: Use this ONLY for testing with small amounts!
"""

from eth_account import Account
import secrets

def create_new_wallet():
    """Create a new Ethereum/Polygon wallet."""
    print()
    print("=" * 70)
    print("POLYMARKET WALLET GENERATOR")
    print("=" * 70)
    print()
    print("⚠️  WARNING: This creates a NEW wallet for testing!")
    print("⚠️  Save the private key securely - you cannot recover it later!")
    print()
    
    # Generate random private key
    private_key = "0x" + secrets.token_hex(32)
    
    # Create account from private key
    account = Account.from_key(private_key)
    
    print("✅ New wallet created!")
    print()
    print("=" * 70)
    print("WALLET DETAILS (SAVE THIS SECURELY!)")
    print("=" * 70)
    print(f"Address:     {account.address}")
    print(f"Private Key: {private_key}")
    print("=" * 70)
    print()
    print("📝 NEXT STEPS:")
    print()
    print("1. Add this private key to your .env file:")
    print(f"   POLYMARKET_PRIVATE_KEY={private_key}")
    print()
    print("2. Update Chain ID to Polygon Mainnet:")
    print(f"   POLYMARKET_CHAIN_ID=137")
    print()
    print("3. Fund this wallet with USDC on Polygon:")
    print(f"   • Send USDC to: {account.address}")
    print(f"   • You can bridge from Ethereum or buy directly on Polygon")
    print(f"   • Minimum: ~$10-20 for testing")
    print()
    print("4. Make sure you have MATIC for gas fees:")
    print(f"   • Send ~0.1 MATIC to: {account.address}")
    print()
    print("=" * 70)
    print()
    print("⚠️  SECURITY WARNINGS:")
    print("   • NEVER share your private key with anyone!")
    print("   • This is a TEST wallet - don't store large amounts!")
    print("   • Private key = full access to your funds!")
    print()
    
    return {
        "address": account.address,
        "private_key": private_key
    }


if __name__ == "__main__":
    wallet = create_new_wallet()
    
    print("💡 TIP: To use with Polymarket, you need:")
    print("   1. USDC on Polygon (for trading)")
    print("   2. MATIC on Polygon (for gas fees)")
    print()
