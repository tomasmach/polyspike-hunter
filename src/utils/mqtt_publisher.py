"""
MQTT Publisher for PolySpike Hunter trading bot.

Provides async-friendly MQTT client for publishing real-time trading events,
market data, and bot status updates to MQTT broker with automatic reconnection.
"""

import json
import time
import threading
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from paho.mqtt.client import Client as MQTTClient
import structlog

logger = structlog.get_logger(__name__)


class MQTTPublisher:
    """
    Async-friendly MQTT publisher with automatic reconnection.
    
    Thread-safe implementation that can be called from asyncio event loops.
    Uses paho-mqtt client in sync mode with dedicated thread for network loop.
    Provides convenience methods for publishing structured trading events.
    
    Topics:
    - status/bot/heartbeat: Bot heartbeat signals (QoS 0, retain=True)
    - status/bot/events: Bot lifecycle events (QoS 0, retain=False)
    - market/snapshots: Market data snapshots (QoS 0, retain=False)
    - market/events: Market-related events (QoS 0, retain=False)
    - trading/events: Trading execution events (QoS 1, retain=False)
    - trading/positions: Position updates (QoS 1, retain=False)
    - balance/current: Current balance (QoS 1, retain=True)
    - stats/session: Session statistics (QoS 1, retain=True)
    """
    
    def __init__(
        self,
        host: str,
        port: int = 1883,
        client_id: Optional[str] = None,
        keepalive: int = 60,
        reconnect_delay: float = 5.0,
        reconnect_backoff: float = 2.0,
        max_reconnect_delay: float = 60.0
    ):
        """
        Initialize MQTT publisher.
        
        Args:
            host: MQTT broker hostname or IP address
            port: MQTT broker port (default: 1883)
            client_id: Unique client identifier (auto-generated if None)
            keepalive: Keepalive interval in seconds
            reconnect_delay: Initial delay before reconnection attempt (seconds)
            reconnect_backoff: Exponential backoff multiplier
            max_reconnect_delay: Maximum reconnection delay (seconds)
        """
        self.host = host
        self.port = port
        self.client_id = client_id or f"polyspike_bot_{int(time.time())}"
        self.keepalive = keepalive
        
        self.reconnect_delay = reconnect_delay
        self.reconnect_backoff = reconnect_backoff
        self.max_reconnect_delay = max_reconnect_delay
        
        self._client: Optional[MQTTClient] = None
        self._connected = False
        self._connect_lock = threading.Lock()
        self._publish_lock = threading.Lock()
        
        logger.info(
            "mqtt_publisher_initialized",
            client_id=self.client_id,
            broker=f"{host}:{port}"
        )
    
    async def connect(self) -> None:
        """
        Connect to MQTT broker with retry logic.
        
        Raises:
            RuntimeError: If connection fails after multiple retries
        """
        if self._connected:
            logger.warning("mqtt_already_connected", client_id=self.client_id)
            return
        
        with self._connect_lock:
            if self._connected:
                return
            
            self._client = MQTTClient(
                client_id=self.client_id,
                protocol=MQTTClient.MQTTv311,
                transport="tcp"
            )
            
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_publish = self._on_publish
            
            current_delay = self.reconnect_delay
            max_retries = 10
            attempt = 0
            
            while attempt < max_retries:
                attempt += 1
                try:
                    logger.info(
                        "mqtt_connecting",
                        broker=f"{self.host}:{self.port}",
                        attempt=attempt
                    )
                    
                    self._client.connect(
                        self.host,
                        port=self.port,
                        keepalive=self.keepalive
                    )
                    
                    self._client.loop_start()
                    
                    timeout = 10
                    start_time = time.time()
                    while not self._connected:
                        if time.time() - start_time > timeout:
                            raise TimeoutError("Connection timeout")
                        await self._async_sleep(0.1)
                    
                    logger.info(
                        "mqtt_connected",
                        broker=f"{self.host}:{self.port}",
                        client_id=self.client_id
                    )
                    return
                    
                except (OSError, TimeoutError, Exception) as e:
                    logger.warning(
                        "mqtt_connect_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        attempt=attempt,
                        retry_delay=current_delay
                    )
                    
                    if attempt >= max_retries:
                        raise RuntimeError(
                            f"Failed to connect to MQTT broker after {max_retries} attempts"
                        )
                    
                    await self._async_sleep(current_delay)
                    current_delay = min(
                        current_delay * self.reconnect_backoff,
                        self.max_reconnect_delay
                    )
    
    async def disconnect(self) -> None:
        """Disconnect from MQTT broker gracefully."""
        with self._connect_lock:
            if self._client is None:
                return
            
            self._connected = False
            
            try:
                self._client.loop_stop()
                self._client.disconnect()
                logger.info("mqtt_disconnected", client_id=self.client_id)
            except Exception as e:
                logger.error(
                    "mqtt_disconnect_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
            finally:
                self._client = None
    
    def publish(
        self,
        topic: str,
        payload: Optional[Dict[str, Any]],
        qos: int = 0,
        retain: bool = False
    ) -> None:
        """
        Publish message to MQTT topic.
        
        Args:
            topic: MQTT topic to publish to
            payload: Message payload dictionary (will be JSON serialized)
            qos: QoS level (0=at most once, 1=at least once, 2=exactly once)
            retain: Whether broker should retain message
            
        Raises:
            ValueError: If topic is empty or invalid
        """
        if not topic or not topic.strip():
            raise ValueError("Topic cannot be empty")
        
        if not self._connected or self._client is None:
            logger.debug("mqtt_not_connected", topic=topic, action="skipped")
            return
        
        if payload is None:
            logger.warning("mqtt_payload_none", topic=topic, action="skipped")
            return
        
        if not isinstance(payload, dict):
            logger.warning(
                "mqtt_payload_not_dict",
                topic=topic,
                payload_type=type(payload).__name__,
                action="serializing_as_is"
            )
        
        try:
            payload_copy = dict(payload) if isinstance(payload, dict) else payload
            
            if isinstance(payload_copy, dict) and "timestamp" not in payload_copy:
                payload_copy["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            message = json.dumps(payload_copy, default=str)
            
            with self._publish_lock:
                info = self._client.publish(
                    topic,
                    payload=message,
                    qos=qos,
                    retain=retain
                )
                
                info.wait_for_publish()
                
                logger.debug(
                    "mqtt_message_published",
                    topic=topic,
                    qos=qos,
                    retain=retain,
                    mid=info.mid
                )
                
        except Exception as e:
            logger.error(
                "mqtt_publish_failed",
                topic=topic,
                error=str(e),
                error_type=type(e).__name__
            )
    
    def publish_bot_status(self, event: str, data: Dict[str, Any]) -> None:
        """
        Publish bot lifecycle event.
        
        Topics:
        - status/bot/events: General bot events (started, stopped, error)
        - status/bot/heartbeat: Heartbeat signals (retain=True)
        
        Args:
            event: Event type (e.g., "started", "stopped", "error", "heartbeat")
            data: Event data dictionary
        """
        if event == "heartbeat":
            topic = "status/bot/heartbeat"
            qos = 0
            retain = True
        else:
            topic = f"status/bot/events/{event}"
            qos = 0
            retain = False
        
        payload = {
            "event": event,
            "client_id": self.client_id,
            **data
        }
        
        self.publish(topic, payload, qos=qos, retain=retain)
    
    def publish_market_event(self, event: str, data: Dict[str, Any]) -> None:
        """
        Publish market-related event.
        
        Topics:
        - market/events: Market events (spike_detected, liquidity_issue, etc.)
        - market/snapshots: Market data snapshots
        
        Args:
            event: Event type (e.g., "spike_detected", "snapshot", "error")
            data: Event data dictionary (should include token_id, market_name, price, etc.)
        """
        if event == "snapshot":
            topic = "market/snapshots"
            qos = 0
            retain = False
        else:
            topic = f"market/events/{event}"
            qos = 0
            retain = False
        
        payload = {
            "event": event,
            **data
        }
        
        self.publish(topic, payload, qos=qos, retain=retain)
    
    def publish_trading_event(self, event: str, data: Dict[str, Any]) -> None:
        """
        Publish trading execution event.
        
        Topics:
        - trading/events: Trading events (signal, order_placed, trade_completed, etc.)
        - trading/positions: Position updates
        
        Args:
            event: Event type (e.g., "signal", "order_placed", "trade_completed",
                  "position_opened", "position_closed", "error")
            data: Event data dictionary (should include token_id, market_name,
                  price, pnl, etc. for trade events)
        """
        if event in ("position_opened", "position_closed", "position_updated"):
            topic = f"trading/positions/{event}"
            qos = 1
            retain = False
        else:
            topic = f"trading/events/{event}"
            qos = 1
            retain = False
        
        payload = {
            "event": event,
            **data
        }
        
        self.publish(topic, payload, qos=qos, retain=retain)
    
    def publish_balance_update(self, data: Dict[str, Any]) -> None:
        """
        Publish balance update.
        
        Topic: balance/current (QoS 1, retain=True)
        
        Args:
            data: Balance data dictionary (should include balance, available_balance,
                  total_pnl, position_count, etc.)
        """
        payload = {
            "client_id": self.client_id,
            **data
        }
        
        self.publish("balance/current", payload, qos=1, retain=True)
    
    def publish_stats(self, event: str, data: Dict[str, Any]) -> None:
        """
        Publish session statistics.
        
        Topics:
        - stats/session: Session statistics (retain=True)
        - stats/periodic: Periodic stats updates
        
        Args:
            event: Stats event type (e.g., "session", "periodic", "summary")
            data: Statistics data dictionary
        """
        if event == "session":
            topic = "stats/session"
            qos = 1
            retain = True
        else:
            topic = f"stats/{event}"
            qos = 1
            retain = False
        
        payload = {
            "event": event,
            "client_id": self.client_id,
            **data
        }
        
        self.publish(topic, payload, qos=qos, retain=retain)
    
    def _on_connect(self, client: MQTTClient, userdata, flags, rc) -> None:
        """MQTT on_connect callback."""
        if rc == 0:
            self._connected = True
            logger.info(
                "mqtt_connection_established",
                client_id=self.client_id,
                rc=rc
            )
        else:
            self._connected = False
            logger.error(
                "mqtt_connection_refused",
                client_id=self.client_id,
                rc=rc
            )
    
    def _on_disconnect(self, client: MQTTClient, userdata, rc) -> None:
        """MQTT on_disconnect callback with automatic reconnection."""
        self._connected = False
        
        if rc == 0:
            logger.info("mqtt_disconnected_cleanly", client_id=self.client_id)
        else:
            logger.warning(
                "mqtt_unexpected_disconnect",
                client_id=self.client_id,
                rc=rc,
                reason=self._get_disconnect_reason(rc)
            )
    
    def _on_publish(self, client: MQTTClient, userdata, mid) -> None:
        """MQTT on_publish callback."""
        logger.debug("mqtt_message_acknowledged", mid=mid)
    
    def _get_disconnect_reason(self, rc: int) -> str:
        """Get human-readable disconnect reason code."""
        reasons = {
            1: "Connection refused - incorrect protocol version",
            2: "Connection refused - invalid client identifier",
            3: "Connection refused - server unavailable",
            4: "Connection refused - bad username or password",
            5: "Connection refused - not authorized",
        }
        return reasons.get(rc, f"Unknown reason code: {rc}")
    
    async def _async_sleep(self, seconds: float) -> None:
        """Async sleep helper."""
        import asyncio
        await asyncio.sleep(seconds)
