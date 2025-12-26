"""
Script to generate/derive API credentials for Polymarket CLOB.
This creates the apiKey, secret, and passphrase needed for L2 authentication.
"""

import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

# Load environment variables from .env
load_dotenv()

def get_api_credentials():
    """Generate or derive API credentials for Polymarket CLOB."""
    
    # Load configuration from .env
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    host = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")
    funder = os.getenv("POLYMARKET_FUNDER", "0x0000000000000000000000000000000000000000")
    
    # Validate private key
    if not private_key or private_key == "your_private_key_here":
        print("ERROR: POLYMARKET_PRIVATE_KEY not set in .env file")
        print("Please add your private key to the .env file")
        return None
    
    try:
        print("Connecting to Polymarket CLOB...")
        print(f"   Host: {host}")
        print(f"   Chain ID: {chain_id}")
        print(f"   Funder: {funder}")
        print()
        
        # Initialize client
        client = ClobClient(
            host=host,
            chain_id=chain_id,
            key=private_key,
            funder=funder
        )
        
        print("Generating/Deriving API credentials...")
        api_creds = client.create_or_derive_api_creds()
        
        print("API Credentials Generated Successfully!")
        print()
        print("=" * 70)
        print("API CREDENTIALS (Keep these secure!)")
        print("=" * 70)
        print(f"API Key:    {api_creds.api_key}")
        print(f"Secret:     {api_creds.api_secret}")
        print(f"Passphrase: {api_creds.api_passphrase}")
        print("=" * 70)
        print()
        print("You can add these to your .env file for L2 authentication:")
        print(f"   CLOB_API_KEY={api_creds.api_key}")
        print(f"   CLOB_SECRET={api_creds.api_secret}")
        print(f"   CLOB_PASSPHRASE={api_creds.api_passphrase}")
        print()
        
        return api_creds
        
    except Exception as e:
        print(f"ERROR: Failed to generate API credentials")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Error message: {str(e)}")
        print()
        print("Make sure your POLYMARKET_PRIVATE_KEY is valid")
        return None


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("POLYMARKET API CREDENTIAL GENERATOR")
    print("=" * 70)
    print()
    
    api_creds = get_api_credentials()
    
    if api_creds:
        print("Done! You can now use these credentials for trading.")
    else:
        print("Failed to generate credentials. Please check the errors above.")
    
    print()
