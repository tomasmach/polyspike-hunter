"""
Configuration settings for PolySpike Hunter bot.
Loads environment variables from .env file and provides typed configuration.
"""

import os
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class PolymarketConfig(BaseModel):
    """Polymarket API configuration."""
    
    private_key: str = Field(..., description="Private key for signing transactions")
    chain_id: int = Field(default=137, description="Chain ID (137 for Polygon mainnet)")
    host: str = Field(default="https://clob.polymarket.com", description="CLOB API host")
    funder: str = Field(
        default="0x0000000000000000000000000000000000000000",
        description="Funder address"
    )
    
    # L2 Authentication (Optional)
    api_key: Optional[str] = Field(default=None, description="API Key for L2 authentication")
    secret: Optional[str] = Field(default=None, description="API Secret for L2 authentication")
    passphrase: Optional[str] = Field(default=None, description="API Passphrase for L2 authentication")
    
    @field_validator("private_key")
    @classmethod
    def validate_private_key(cls, v: str) -> str:
        """Validate that private key is not empty."""
        if not v or v == "your_private_key_here":
            raise ValueError(
                "POLYMARKET_PRIVATE_KEY must be set in .env file. "
                "Never commit your private key to version control!"
            )
        return v


class TradingConfig(BaseModel):
    """Trading strategy configuration."""
    
    poll_interval: float = Field(
        default=1.0,
        description="Polling interval in seconds",
        gt=0.0
    )
    spike_threshold: float = Field(
        default=0.02,
        description="Price change threshold to trigger trade (2%)",
        gt=0.0,
        lt=1.0
    )
    position_size: float = Field(
        default=5.0,
        description="Position size in USD",
        gt=0.0,
        le=10.0
    )
    stop_loss_pct: float = Field(
        default=0.02,
        description="Stop loss percentage",
        gt=0.0,
        lt=1.0
    )
    take_profit_pct: float = Field(
        default=0.04,
        description="Take profit percentage",
        gt=0.0,
        lt=1.0
    )
    max_drawdown: float = Field(
        default=50.0,
        description="Maximum drawdown in USD before bot stops",
        gt=0.0
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: str = Field(default="INFO", description="Log level")
    log_to_file: bool = Field(default=True, description="Whether to log to file")
    
    @field_validator("level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v


class Settings(BaseModel):
    """Main application settings."""
    
    polymarket: PolymarketConfig
    trading: TradingConfig
    logging: LoggingConfig
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        return cls(
            polymarket=PolymarketConfig(
                private_key=os.getenv("POLYMARKET_PRIVATE_KEY", ""),
                chain_id=int(os.getenv("POLYMARKET_CHAIN_ID", "137")),
                host=os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com"),
                funder=os.getenv(
                    "POLYMARKET_FUNDER",
                    "0x0000000000000000000000000000000000000000"
                ),
                api_key=os.getenv("CLOB_API_KEY"),
                secret=os.getenv("CLOB_SECRET"),
                passphrase=os.getenv("CLOB_PASSPHRASE"),
            ),
            trading=TradingConfig(
                poll_interval=float(os.getenv("POLL_INTERVAL", "1.0")),
                spike_threshold=float(os.getenv("SPIKE_THRESHOLD", "0.02")),
                position_size=float(os.getenv("POSITION_SIZE", "5.0")),
                stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.02")),
                take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.04")),
                max_drawdown=float(os.getenv("MAX_DRAWDOWN", "50.0")),
            ),
            logging=LoggingConfig(
                level=os.getenv("LOG_LEVEL", "INFO"),
                log_to_file=os.getenv("LOG_TO_FILE", "true").lower() == "true",
            ),
        )


# Global settings instance
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global settings
    if settings is None:
        settings = Settings.from_env()
    return settings
