"""
Polymarket CLOB client wrapper with authentication.
Handles connection to Polymarket API using py-clob-client.
"""

from typing import Optional, Dict, Any, List, Callable, TypeVar
import asyncio
from functools import wraps
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, MarketOrderArgs, ApiCreds
import structlog

from config.settings import PolymarketConfig

logger = structlog.get_logger(__name__)

T = TypeVar('T')


def async_retry(max_retries: int = 3, delays: Optional[List[float]] = None):
    """
    Retry decorator with exponential backoff for async functions.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        delays: List of delays in seconds between retries (default: [1, 2, 4])
    """
    if delays is None:
        delays = [1.0, 2.0, 4.0]

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt < max_retries - 1:
                        delay = delays[min(attempt, len(delays) - 1)]
                        logger.warning(
                            "retry_attempt",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay,
                            error=str(e)
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            max_retries=max_retries,
                            error=str(e)
                        )

            # If all retries failed, raise the last exception
            raise last_exception

        return wrapper
    return decorator


class PolymarketClient:
    """
    Wrapper around py-clob-client for Polymarket CLOB API.
    Handles authentication and provides high-level trading methods.
    """
    
    def __init__(self, config: PolymarketConfig):
        """
        Initialize Polymarket client with authentication.

        Args:
            config: Polymarket configuration with API credentials
        """
        self.config = config
        self._client: Optional[ClobClient] = None
        logger.info(
            "initializing_polymarket_client",
            host=config.host,
            chain_id=config.chain_id
        )
    
    async def connect(self) -> None:
        """
        Connect to Polymarket CLOB API.
        Creates authenticated client instance.
        Runs blocking ClobClient construction off the event loop.
        """
        try:
            # Initialize client with L1 authentication (blocking, run in executor)
            self._client = await asyncio.to_thread(
                ClobClient,
                host=self.config.host,
                key=self.config.private_key,
                chain_id=self.config.chain_id,
                funder=self.config.funder,
            )
            
            # If L2 credentials are provided, set them (blocking, run in executor)
            if self.config.api_key and self.config.secret and self.config.passphrase:
                api_creds = ApiCreds(
                    api_key=self.config.api_key,
                    api_secret=self.config.secret,
                    api_passphrase=self.config.passphrase,
                )
                await asyncio.to_thread(self._client.set_api_creds, api_creds)
                logger.info(
                    "polymarket_client_connected",
                    host=self.config.host,
                    auth_mode="L2"
                )
            else:
                logger.info(
                    "polymarket_client_connected",
                    host=self.config.host,
                    auth_mode="L1"
                )
        except Exception as e:
            logger.error(
                "failed_to_connect_polymarket_client",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    @property
    def client(self) -> ClobClient:
        """Get the underlying CLOB client instance."""
        if self._client is None:
            raise RuntimeError(
                "Client not connected. Call connect() first."
            )
        return self._client
    
    @async_retry(max_retries=3, delays=[1.0, 2.0, 4.0])
    async def get_markets(self, next_cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Get list of available markets.

        Args:
            next_cursor: Pagination cursor for next page

        Returns:
            Market data including condition_id, question, tokens, etc.
        """
        try:
            # Call get_markets (blocking, run in executor)
            if next_cursor:
                markets = await asyncio.to_thread(self.client.get_markets, next_cursor=next_cursor)
            else:
                markets = await asyncio.to_thread(self.client.get_markets)

            # Handle different return types
            if isinstance(markets, dict):
                logger.debug("fetched_markets", count=len(markets.get("data", [])))
                return markets
            else:
                # If it's not a dict, wrap it
                return {"data": markets if isinstance(markets, list) else []}
        except Exception as e:
            logger.error(
                "failed_to_fetch_markets",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    @async_retry(max_retries=3, delays=[1.0, 2.0, 4.0])
    async def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """
        Get order book for a specific token.

        Args:
            token_id: Token ID to fetch order book for

        Returns:
            Order book with bids and asks
        """
        try:
            # Run blocking call in executor
            order_book = await asyncio.to_thread(self.client.get_order_book, token_id)
            logger.debug(
                "fetched_order_book",
                token_id=token_id,
                bids=len(order_book.get("bids", [])),
                asks=len(order_book.get("asks", []))
            )
            return order_book
        except Exception as e:
            logger.error(
                "failed_to_fetch_order_book",
                token_id=token_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    @async_retry(max_retries=3, delays=[1.0, 2.0, 4.0])
    async def get_last_trade_price(self, token_id: str) -> Optional[float]:
        """
        Get last trade price for a token.

        Args:
            token_id: Token ID to fetch price for

        Returns:
            Last trade price or None if no trades
        """
        try:
            # Run blocking call in executor (semaphore handles concurrency limiting)
            result = await asyncio.to_thread(self.client.get_last_trade_price, token_id)

            if result:
                # API returns dict with 'price' key
                if isinstance(result, dict):
                    price_str = result.get('price')
                    if price_str:
                        try:
                            price = float(price_str)
                            logger.debug("fetched_last_price", token_id=token_id, price=price)
                            return price
                        except (ValueError, TypeError) as conv_err:
                            logger.error(
                                "invalid_price_conversion",
                                token_id=token_id,
                                price_str=price_str,
                                error=str(conv_err)
                            )
                            return None
                else:
                    # Fallback if API changes to return string/float directly
                    try:
                        price = float(result)
                        logger.debug("fetched_last_price", token_id=token_id, price=price)
                        return price
                    except (ValueError, TypeError) as conv_err:
                        logger.error(
                            "invalid_result_type",
                            token_id=token_id,
                            result_type=type(result).__name__,
                            result=str(result),
                            error=str(conv_err)
                        )
                        return None
            return None
        except Exception as e:
            error_msg = str(e).lower()

            # Detect rate limiting (429 status or "rate limit" in message)
            if "429" in error_msg or "rate limit" in error_msg:
                logger.warning(
                    "rate_limit_detected",
                    token_id=token_id,
                    error=str(e),
                    sleeping_for=1.0
                )
                await asyncio.sleep(1.0)
                return None

            # Log with more details including the cause
            error_details = {
                "token_id": token_id,
                "error": str(e),
                "error_type": type(e).__name__,
            }

            # If the exception has a cause, log it too
            if hasattr(e, '__cause__') and e.__cause__:
                error_details["underlying_error"] = str(e.__cause__)
                error_details["underlying_error_type"] = type(e.__cause__).__name__

            # For debugging, log the full exception chain
            if hasattr(e, '__context__') and e.__context__:
                error_details["context_error"] = str(e.__context__)
                error_details["context_error_type"] = type(e.__context__).__name__

            # Log traceback for first occurrence only (to avoid spam)
            logger.error("failed_to_fetch_last_price", **error_details, exc_info=False)

            # Don't re-raise, just return None to allow other markets to continue
            return None
    
    async def place_market_order(
        self,
        token_id: str,
        side: str,
        amount: float,
    ) -> Dict[str, Any]:
        """
        Place a market order (immediate execution).
        
        Args:
            token_id: Token ID to trade
            side: "BUY" or "SELL"
            amount: Amount in USD to trade
            
        Returns:
            Order response with order ID and status
        """
        try:
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=side,
            )
            
            logger.info(
                "placing_market_order",
                token_id=token_id,
                side=side,
                amount=amount
            )
            
            # Run blocking call in executor
            response = await asyncio.to_thread(self.client.create_market_order, order_args)
            
            logger.info(
                "market_order_placed",
                token_id=token_id,
                side=side,
                amount=amount,
                order_id=response.get("orderID")
            )
            
            return response
        except Exception as e:
            logger.error(
                "failed_to_place_market_order",
                token_id=token_id,
                side=side,
                amount=amount,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    async def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
    ) -> Dict[str, Any]:
        """
        Place a limit order.
        
        Args:
            token_id: Token ID to trade
            side: "BUY" or "SELL"
            price: Limit price
            size: Order size
            
        Returns:
            Order response with order ID and status
        """
        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
            )
            
            logger.info(
                "placing_limit_order",
                token_id=token_id,
                side=side,
                price=price,
                size=size
            )
            
            # Run blocking call in executor
            response = await asyncio.to_thread(self.client.create_order, order_args)
            
            logger.info(
                "limit_order_placed",
                token_id=token_id,
                side=side,
                price=price,
                size=size,
                order_id=response.get("orderID")
            )
            
            return response
        except Exception as e:
            logger.error(
                "failed_to_place_limit_order",
                token_id=token_id,
                side=side,
                price=price,
                size=size,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an open order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            Cancellation response
        """
        try:
            logger.info("cancelling_order", order_id=order_id)
            # Run blocking call in executor
            response = await asyncio.to_thread(self.client.cancel, order_id)
            logger.info("order_cancelled", order_id=order_id)
            return response
        except Exception as e:
            logger.error(
                "failed_to_cancel_order",
                order_id=order_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get all open orders for the authenticated account.
        
        Returns:
            List of open orders
        """
        try:
            # Run blocking call in executor
            orders = await asyncio.to_thread(self.client.get_orders)
            logger.debug("fetched_open_orders", count=len(orders))
            return orders
        except Exception as e:
            logger.error(
                "failed_to_fetch_open_orders",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def disconnect(self) -> None:
        """Disconnect from Polymarket API."""
        self._client = None
        logger.info("polymarket_client_disconnected")
