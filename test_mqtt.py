#!/usr/bin/env python3
"""
MQTT Test Script for PolySpike Hunter

Usage:
    # Publisher mode (send test messages)
    python test_mqtt.py publish
    
    # Subscriber mode (listen to all messages)
    python test_mqtt.py subscribe
    
    # Test specific event
    python test_mqtt.py publish --event bot_started
"""

import asyncio
import sys
import time
import json
from typing import Optional
import paho.mqtt.client as mqtt

# MQTT Configuration
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "polyspike"


class MQTTTester:
    """Test MQTT functionality."""
    
    def __init__(self, host: str = MQTT_HOST, port: int = MQTT_PORT):
        self.host = host
        self.port = port
        self.client_id = "polyspike_tester"
        self.topic_prefix = MQTT_TOPIC_PREFIX
        self.client: Optional[mqtt.Client] = None
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback on connection."""
        if rc == 0:
            print(f"✅ Connected to MQTT broker at {self.host}:{self.port}")
            # Subscribe to all topics in subscriber mode
            if hasattr(self, '_subscriber_mode') and self._subscriber_mode:
                topic = f"{self.topic_prefix}/#"
                client.subscribe(topic)
                print(f"📡 Subscribed to: {topic}")
        else:
            print(f"❌ Connection failed with code: {rc}")
    
    def on_message(self, client, userdata, msg):
        """Callback on message received."""
        try:
            payload = json.loads(msg.payload.decode())
            timestamp = payload.get('timestamp', 0)
            time_str = time.strftime('%H:%M:%S', time.localtime(timestamp))
            
            print(f"\n📨 Message received:")
            print(f"   Topic: {msg.topic}")
            print(f"   Time: {time_str}")
            print(f"   QoS: {msg.qos}")
            print(f"   Retain: {msg.retain}")
            print(f"   Payload:")
            print(json.dumps(payload, indent=4))
        except Exception as e:
            print(f"❌ Error parsing message: {e}")
            print(f"   Raw payload: {msg.payload}")
    
    def connect(self) -> None:
        """Connect to MQTT broker."""
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, self.client_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        print(f"🔌 Connecting to {self.host}:{self.port}...")
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()
        time.sleep(1)
    
    def disconnect(self) -> None:
        """Disconnect from broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            print("👋 Disconnected")
    
    def publish(self, topic: str, payload: dict, qos: int = 0, retain: bool = False) -> None:
        """Publish test message."""
        full_topic = f"{self.topic_prefix}/{topic}"
        
        # Add timestamp if not present
        if 'timestamp' not in payload:
            payload['timestamp'] = time.time()
        
        payload_json = json.dumps(payload)
        
        result = self.client.publish(full_topic, payload_json, qos=qos, retain=retain)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"✅ Published to {full_topic}")
            print(f"   QoS: {qos}, Retain: {retain}")
            print(f"   Payload: {json.dumps(payload, indent=4)}")
        else:
            print(f"❌ Publish failed: {result.rc}")
    
    def test_bot_started(self) -> None:
        """Test bot started event."""
        print("\n🧪 Testing: Bot Started Event")
        self.publish("status/bot/started", {
            "session_id": "test_session_20260102",
            "config": {
                "initial_balance": 100.0,
                "spike_threshold": 0.03,
                "position_size": 5.0,
                "monitored_markets": 50,
            }
        }, qos=1)
    
    def test_heartbeat(self) -> None:
        """Test heartbeat event."""
        print("\n🧪 Testing: Heartbeat")
        self.publish("status/bot/heartbeat", {
            "uptime_seconds": 3600,
            "balance": 105.23,
            "open_positions": 2,
            "total_trades": 15,
        }, qos=0, retain=True)
    
    def test_spike_detected(self) -> None:
        """Test spike detection event."""
        print("\n🧪 Testing: Spike Detected")
        self.publish("market/spike_detected", {
            "token_id": "0x1234abcd5678...",
            "market_name": "Will Trump win 2024?",
            "price": 0.4800,
            "spike_pct": -0.032,
            "direction": "down",
            "reason": "spike_down",
        }, qos=0)
    
    def test_position_opened(self) -> None:
        """Test position opened event."""
        print("\n🧪 Testing: Position Opened")
        self.publish("trading/position/opened", {
            "token_id": "0x1234abcd5678...",
            "market_name": "Will Trump win 2024?",
            "entry_price": 0.4800,
            "position_size": 5.0,
            "reason": "spike_down",
            "spike_magnitude": 0.032,
        }, qos=1)
    
    def test_position_closed(self) -> None:
        """Test position closed event."""
        print("\n🧪 Testing: Position Closed")
        self.publish("trading/position/closed", {
            "token_id": "0x1234abcd5678...",
            "market_name": "Will Trump win 2024?",
            "entry_price": 0.4800,
            "exit_price": 0.4992,
            "position_size": 5.0,
            "pnl": 0.20,
            "pnl_pct": 0.04,
            "duration_seconds": 30,
            "exit_reason": "take_profit",
        }, qos=1)
    
    def test_balance_update(self) -> None:
        """Test balance update event."""
        print("\n🧪 Testing: Balance Update")
        self.publish("balance/update", {
            "balance": 100.20,
            "equity": 100.45,
            "available_balance": 90.20,
            "locked_in_positions": 10.0,
            "unrealized_pnl": 0.25,
            "total_pnl": 0.20,
            "update_reason": "periodic",
        }, qos=1, retain=True)
    
    def test_all_events(self) -> None:
        """Test all event types."""
        self.test_bot_started()
        time.sleep(0.5)
        
        self.test_heartbeat()
        time.sleep(0.5)
        
        self.test_spike_detected()
        time.sleep(0.5)
        
        self.test_position_opened()
        time.sleep(0.5)
        
        self.test_position_closed()
        time.sleep(0.5)
        
        self.test_balance_update()
    
    def subscribe_mode(self) -> None:
        """Run in subscriber mode (listen to all messages)."""
        self._subscriber_mode = True
        self.connect()
        
        print("\n👂 Listening to all MQTT messages...")
        print("   Press Ctrl+C to stop\n")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopping subscriber...")
            self.disconnect()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_mqtt.py publish [--event <event_name>]")
        print("  python test_mqtt.py subscribe")
        print("\nAvailable events:")
        print("  bot_started, heartbeat, spike_detected,")
        print("  position_opened, position_closed, balance_update, all")
        sys.exit(1)
    
    mode = sys.argv[1]
    tester = MQTTTester()
    
    if mode == "subscribe":
        tester.subscribe_mode()
    
    elif mode == "publish":
        tester.connect()
        
        event = "all"
        if len(sys.argv) > 3 and sys.argv[2] == "--event":
            event = sys.argv[3]
        
        # Publish based on event type
        if event == "all":
            tester.test_all_events()
        elif event == "bot_started":
            tester.test_bot_started()
        elif event == "heartbeat":
            tester.test_heartbeat()
        elif event == "spike_detected":
            tester.test_spike_detected()
        elif event == "position_opened":
            tester.test_position_opened()
        elif event == "position_closed":
            tester.test_position_closed()
        elif event == "balance_update":
            tester.test_balance_update()
        else:
            print(f"❌ Unknown event: {event}")
            sys.exit(1)
        
        time.sleep(1)
        tester.disconnect()
    
    else:
        print(f"❌ Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
