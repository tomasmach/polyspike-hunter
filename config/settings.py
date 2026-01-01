"""
Configuration settings for PolySpike Hunter bot.
Loads environment variables from .env file and provides typed configuration.
"""

import os
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
import structlog

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)


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


class PaperTradingConfig(BaseModel):
    """Paper trading configuration."""
    
    enabled: bool = Field(default=True, description="Enable paper trading mode")
    initial_balance: float = Field(
        default=100.0,
        description="Initial balance for paper trading",
        gt=0.0
    )
    min_position_size: float = Field(
        default=1.0,
        description="Minimum position size",
        gt=0.0
    )
    max_open_positions: int = Field(
        default=10,
        description="Maximum concurrent positions",
        gt=0
    )


class MarketMonitoringConfig(BaseModel):
    """Market monitoring configuration."""

    strategy: str = Field(default="volume", description="Market selection strategy")
    max_monitored_markets: int = Field(
        default=50,
        description="Maximum markets to monitor",
        gt=0
    )
    min_market_volume: float = Field(
        default=0.0,
        description="Minimum market volume filter",
        ge=0.0
    )
    price_history_window: int = Field(
        default=60,
        description="Price history window in seconds",
        gt=0
    )
    max_concurrent_requests: int = Field(
        default=40,
        description="Maximum concurrent API requests to avoid rate limiting",
        gt=0,
        le=100
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
    paper_trading: PaperTradingConfig
    monitoring: MarketMonitoringConfig
    logging: LoggingConfig
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables with robust error handling."""
        # Parse polymarket config with error handling
        try:
            chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
        except ValueError:
            logger.warning("invalid_env_var", var="POLYMARKET_CHAIN_ID", using_default=137)
            chain_id = 137

        # Parse trading config with error handling
        try:
            poll_interval = float(os.getenv("POLL_INTERVAL", "1.0"))
        except ValueError:
            logger.warning("invalid_env_var", var="POLL_INTERVAL", using_default=1.0)
            poll_interval = 1.0

        try:
            spike_threshold = float(os.getenv("SPIKE_THRESHOLD", "0.03"))
        except ValueError:
            logger.warning("invalid_env_var", var="SPIKE_THRESHOLD", using_default=0.03)
            spike_threshold = 0.03

        try:
            position_size = float(os.getenv("POSITION_SIZE", "5.0"))
        except ValueError:
            logger.warning("invalid_env_var", var="POSITION_SIZE", using_default=5.0)
            position_size = 5.0

        try:
            stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "0.02"))
        except ValueError:
            logger.warning("invalid_env_var", var="STOP_LOSS_PCT", using_default=0.02)
            stop_loss_pct = 0.02

        try:
            take_profit_pct = float(os.getenv("TAKE_PROFIT_PCT", "0.04"))
        except ValueError:
            logger.warning("invalid_env_var", var="TAKE_PROFIT_PCT", using_default=0.04)
            take_profit_pct = 0.04

        try:
            max_drawdown = float(os.getenv("MAX_DRAWDOWN", "50.0"))
        except ValueError:
            logger.warning("invalid_env_var", var="MAX_DRAWDOWN", using_default=50.0)
            max_drawdown = 50.0

        # Parse paper trading config with error handling
        try:
            initial_balance = float(os.getenv("INITIAL_BALANCE", "100.0"))
        except ValueError:
            logger.warning("invalid_env_var", var="INITIAL_BALANCE", using_default=100.0)
            initial_balance = 100.0

        try:
            min_position_size = float(os.getenv("MIN_POSITION_SIZE", "1.0"))
        except ValueError:
            logger.warning("invalid_env_var", var="MIN_POSITION_SIZE", using_default=1.0)
            min_position_size = 1.0

        try:
            max_open_positions = int(os.getenv("MAX_OPEN_POSITIONS", "10"))
        except ValueError:
            logger.warning("invalid_env_var", var="MAX_OPEN_POSITIONS", using_default=10)
            max_open_positions = 10

        # Parse monitoring config with error handling
        try:
            max_monitored_markets = int(os.getenv("MAX_MONITORED_MARKETS", "50"))
        except ValueError:
            logger.warning("invalid_env_var", var="MAX_MONITORED_MARKETS", using_default=50)
            max_monitored_markets = 50

        try:
            min_market_volume = float(os.getenv("MIN_MARKET_VOLUME", "1000.0"))
        except ValueError:
            logger.warning("invalid_env_var", var="MIN_MARKET_VOLUME", using_default=1000.0)
            min_market_volume = 1000.0

        try:
            price_history_window = int(os.getenv("PRICE_HISTORY_WINDOW", "60"))
        except ValueError:
            logger.warning("invalid_env_var", var="PRICE_HISTORY_WINDOW", using_default=60)
            price_history_window = 60

        try:
            max_concurrent_requests = int(os.getenv("MAX_CONCURRENT_REQUESTS", "40"))
        except ValueError:
            logger.warning("invalid_env_var", var="MAX_CONCURRENT_REQUESTS", using_default=40)
            max_concurrent_requests = 40

        # Validate and clamp poll_interval
        if poll_interval <= 0 or poll_interval >= 60:
            logger.warning(
                "invalid_poll_interval",
                value=poll_interval,
                clamping_to=1.0,
                reason="must be > 0 and < 60"
            )
            poll_interval = max(0.1, min(poll_interval, 59.9))

        # Validate and clamp spike_threshold
        if spike_threshold <= 0 or spike_threshold >= 1.0:
            logger.warning(
                "invalid_spike_threshold",
                value=spike_threshold,
                clamping_to=0.03,
                reason="must be > 0 and < 1.0"
            )
            spike_threshold = max(0.001, min(spike_threshold, 0.99))

        return cls(
            polymarket=PolymarketConfig(
                private_key=os.getenv("POLYMARKET_PRIVATE_KEY", ""),
                chain_id=chain_id,
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
                poll_interval=poll_interval,
                spike_threshold=spike_threshold,
                position_size=position_size,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                max_drawdown=max_drawdown,
            ),
            paper_trading=PaperTradingConfig(
                enabled=os.getenv("PAPER_TRADING", "true").lower() == "true",
                initial_balance=initial_balance,
                min_position_size=min_position_size,
                max_open_positions=max_open_positions,
            ),
            monitoring=MarketMonitoringConfig(
                strategy=os.getenv("MONITOR_STRATEGY", "volume"),
                max_monitored_markets=max_monitored_markets,
                min_market_volume=min_market_volume,
                price_history_window=price_history_window,
                max_concurrent_requests=max_concurrent_requests,
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
