# PolySpike Hunter - MQTT API Documentation

**Version:** 1.0
**Date:** 2026-01-02
**For:** Discord Bot Integration

---

## 📡 Overview

PolySpike Hunter trading bot publishes real-time events via MQTT for monitoring and notifications.

### MQTT Broker

- **Host:** `localhost` (running on the same Raspberry Pi as the bot)
- **Port:** 1883
- **Authentication:** NO (local network, no password)
- **Protocol:** MQTT v3.1.1
- **Topic Prefix:** `polyspike/`
- **Message Format:** JSON

---

## 📋 Topic Structure

```
polyspike/
├── status/
│   ├── bot/started              # Bot started
│   ├── bot/stopped              # Bot stopped
│   ├── bot/heartbeat            # Heartbeat (every 30s)
│   └── bot/error                # Critical error
│
├── market/
│   └── spike_detected           # Price spike detected
│
├── trading/
│   ├── position/opened          # Position opened
│   ├── position/closed          # Position closed
│   └── trade/completed          # Trade completed (+ P&L)
│
├── balance/
│   └── update                   # Balance update (12h or change)
│
└── stats/
    ├── periodic                 # Periodic stats (10s)
    └── session                  # Session summary (on shutdown)
```

---

## 🔒 QoS Levels

| Topic Pattern | QoS | Retain | Description |
|--------------|-----|--------|-------------|
| `status/bot/*` | 1 | heartbeat=YES | Critical status messages |
| `market/*` | 0 | NO | Market events (high-frequency) |
| `trading/*` | 1 | NO | Trading events (MUST NOT miss) |
| `balance/*` | 1 | YES | Balance updates |
| `stats/*` | 1 | session=YES | Statistics |

### QoS Explanation

- **QoS 0:** At most once (may be lost)
- **QoS 1:** At least once (guaranteed delivery, possible duplicates)

### Retained Messages

Subscriber receives the last message even when connecting after publish:

- `status/bot/heartbeat` - last bot state
- `balance/update` - last balance
- `stats/session` - last session summary

---

## 📨 Message Payloads

### 1. Bot Status Events

#### `polyspike/status/bot/started`

**When:** Bot started
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833600.123,
  "session_id": "20260102_180000",
  "config": {
    "initial_balance": 100.0,
    "spike_threshold": 0.03,
    "position_size": 5.0,
    "monitored_markets": 50
  }
}
```

**Fields:**

- `timestamp` (float): Unix timestamp
- `session_id` (string): Unique session ID
- `config.initial_balance` (float): Starting balance in USD
- `config.spike_threshold` (float): Spike detection threshold (0.03 = 3%)
- `config.position_size` (float): Position size in USD
- `config.monitored_markets` (int): Number of monitored markets

---

#### `polyspike/status/bot/heartbeat`

**When:** Every 30 seconds
**QoS:** 0
**Retain:** YES

```json
{
  "timestamp": 1735833630.456,
  "uptime_seconds": 3600,
  "balance": 105.23,
  "open_positions": 2,
  "total_trades": 15
}
```

**Fields:**

- `uptime_seconds` (int): Uptime in seconds
- `balance` (float): Current balance
- `open_positions` (int): Number of open positions
- `total_trades` (int): Total number of trades

**Usage:** Health check (if heartbeat missing >60s, bot is probably down)

---

#### `polyspike/status/bot/stopped`

**When:** Bot stopped (graceful shutdown)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735837200.789,
  "session_id": "20260102_180000",
  "final_stats": {
    "total_pnl": 5.23,
    "total_trades": 25,
    "win_rate": 0.72
  }
}
```

---

#### `polyspike/status/bot/error`

**When:** Critical error (connection loss, crash)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833650.789,
  "error_type": "ConnectionError",
  "error_message": "Failed to connect to Polymarket API",
  "severity": "critical"
}
```

**Fields:**

- `error_type` (string): Python exception type
- `error_message` (string): Error description
- `severity` (string): "critical" | "error" | "warning"

---

### 2. Market Events

#### `polyspike/market/spike_detected`

**When:** Price spike detected (±3%+)
**QoS:** 0
**Retain:** NO

```json
{
  "timestamp": 1735833700.123,
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "price": 0.4800,
  "spike_pct": -0.032,
  "direction": "down",
  "reason": "spike_down"
}
```

**Fields:**

- `token_id` (string): Polymarket token ID (hash)
- `market_name` (string): Human-readable market name
- `price` (float): Current price (0.0 - 1.0)
- `spike_pct` (float): Spike magnitude (absolute, -0.032 = -3.2%)
- `direction` (string): "up" | "down"
- `reason` (string): "spike_up" | "spike_down"

**Note:** Spike detection does NOT mean the bot opened a position (may be rejected by risk manager)

---

### 3. Trading Events

#### `polyspike/trading/position/opened`

**When:** Position opened (BUY executed)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833715.789,
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "entry_price": 0.4800,
  "position_size": 5.0,
  "reason": "spike_down",
  "spike_magnitude": 0.032
}
```

**Fields:**

- `entry_price` (float): Entry price
- `position_size` (float): Position size in USD
- `spike_magnitude` (float): Spike magnitude that triggered entry

---

#### `polyspike/trading/position/closed`

**When:** Position closed (SELL executed)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833745.012,
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "entry_price": 0.4800,
  "exit_price": 0.4992,
  "position_size": 5.0,
  "pnl": 0.20,
  "pnl_pct": 0.04,
  "duration_seconds": 30,
  "exit_reason": "take_profit"
}
```

**Fields:**

- `exit_price` (float): Exit price
- `pnl` (float): Profit & Loss in USD
- `pnl_pct` (float): P&L percentage (0.04 = 4%)
- `duration_seconds` (int): Position holding duration
- `exit_reason` (string): "take_profit" | "stop_loss"

---

#### `polyspike/trading/trade/completed`

**When:** Trade fully completed (summary)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833745.012,
  "trade_id": "a1b2c3d4-5678-...",
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "entry_price": 0.4800,
  "exit_price": 0.4992,
  "size": 5.0,
  "pnl": 0.20,
  "pnl_pct": 0.04,
  "duration_seconds": 30,
  "reason": "take_profit"
}
```

**Fields:**

- `trade_id` (string): Unique trade ID (UUID)
- Other fields same as `position/closed`

**Difference `position/closed` vs `trade/completed`:**

- `position/closed` - immediate event after SELL
- `trade/completed` - summary with `trade_id` (for logging/analytics)

---

### 4. Balance Updates

#### `polyspike/balance/update`

**When:**

- Every 12 hours (43200s)
- When balance changes by >5%
- After every completed trade

**QoS:** 1
**Retain:** YES

```json
{
  "timestamp": 1735833750.345,
  "balance": 100.20,
  "equity": 100.45,
  "available_balance": 90.20,
  "locked_in_positions": 10.0,
  "unrealized_pnl": 0.25,
  "total_pnl": 0.20,
  "update_reason": "periodic"
}
```

**Fields:**

- `balance` (float): Cash balance
- `equity` (float): Balance + unrealized P&L
- `available_balance` (float): Balance - locked capital
- `locked_in_positions` (float): Capital in open positions
- `unrealized_pnl` (float): Unrealized profit/loss
- `total_pnl` (float): Total realized P&L (from start)
- `update_reason` (string): "periodic" | "significant_change" | "trade"

---

### 5. Statistics

#### `polyspike/stats/periodic`

**When:** Every 10 seconds (during runtime)
**QoS:** 0
**Retain:** NO

```json
{
  "timestamp": 1735833760.678,
  "balance": 100.20,
  "equity": 100.45,
  "open_positions": 2,
  "total_trades": 16,
  "winning_trades": 12,
  "losing_trades": 4,
  "win_rate": 0.75,
  "total_pnl": 0.20,
  "max_drawdown": 5.0
}
```

---

#### `polyspike/stats/session`

**When:** On bot shutdown
**QoS:** 1
**Retain:** YES

```json
{
  "timestamp": 1735837200.901,
  "session_id": "20260102_180000",
  "duration_seconds": 3600,
  "initial_balance": 100.0,
  "final_balance": 105.23,
  "total_pnl": 5.23,
  "total_pnl_pct": 0.0523,
  "total_trades": 25,
  "winning_trades": 18,
  "losing_trades": 7,
  "win_rate": 0.72,
  "max_drawdown": 8.5,
  "avg_win": 0.45,
  "avg_loss": -0.30
}
```

---

## 🔌 Discord Bot Integration Guide

### Connecting to MQTT

#### Python (paho-mqtt)

```python
import paho.mqtt.client as mqtt
import json

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
        # Subscribe to all topics
        client.subscribe("polyspike/#")
    else:
        print(f"Connection failed: {rc}")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = json.loads(msg.payload.decode())

    # Handle different event types
    if "position/opened" in topic:
        handle_position_opened(payload)
    elif "trade/completed" in topic:
        handle_trade_completed(payload)
    # ...

client = mqtt.Client("discord_bot")
client.on_connect = on_connect
client.on_message = on_message

client.connect("localhost", 1883, 60)
client.loop_forever()
```

#### Node.js (mqtt.js)

```javascript
const mqtt = require('mqtt');
const client = mqtt.connect('mqtt://localhost:1883');

client.on('connect', () => {
  console.log('Connected to MQTT broker');
  client.subscribe('polyspike/#');
});

client.on('message', (topic, message) => {
  const payload = JSON.parse(message.toString());

  if (topic.includes('position/opened')) {
    handlePositionOpened(payload);
  }
  // ...
});
```

---

### Recommended Discord Notifications

**Critical (always send):**

- ✅ `status/bot/started` - Bot started
- ✅ `status/bot/stopped` - Bot stopped
- ✅ `status/bot/error` - Critical error
- ✅ `trading/position/opened` - Position opened
- ✅ `trading/trade/completed` - Trade completed (+ P&L)

**Optional:**

- ⚠️ `market/spike_detected` - May be spammy
- ⚠️ `stats/periodic` - Every 10s (too frequent?)
- ✅ `balance/update` - Every 12h (OK)
- ✅ `stats/session` - Session summary (on shutdown)

**Heartbeat:**

- ❌ DO NOT send to Discord (every 30s = spam)
- ✅ Use for monitoring (if missing >60s -> alert)

---

### Discord Embed Examples

#### Position Opened

```python
embed = discord.Embed(
    title="🟢 Position Opened",
    description=payload["market_name"],
    color=0x00ff00,  # Green
    timestamp=datetime.fromtimestamp(payload["timestamp"])
)
embed.add_field(name="Entry Price", value=f"{payload['entry_price']:.4f}")
embed.add_field(name="Size", value=f"${payload['position_size']:.2f}")
embed.add_field(name="Reason", value=payload["reason"])
```

#### Trade Completed

```python
color = 0x00ff00 if payload["pnl"] > 0 else 0xff0000  # Green/Red

embed = discord.Embed(
    title="💰 Trade Completed",
    description=payload["market_name"],
    color=color,
    timestamp=datetime.fromtimestamp(payload["timestamp"])
)
embed.add_field(name="P&L", value=f"${payload['pnl']:+.2f}")
embed.add_field(name="P&L %", value=f"{payload['pnl_pct']*100:+.2f}%")
embed.add_field(name="Duration", value=f"{payload['duration_seconds']}s")
embed.add_field(name="Exit Reason", value=payload["reason"])
```

---

## 🧪 Testing

### Mosquitto CLI Tools

Subscribe to all messages:

```bash
mosquitto_sub -h localhost -t 'polyspike/#' -v
```

Subscribe to specific topic:

```bash
mosquitto_sub -h localhost -t 'polyspike/trading/position/opened' -v
```

Publish test message:

```bash
mosquitto_pub -h localhost -t 'polyspike/status/bot/started' \
  -m '{"timestamp": 1735833600, "session_id": "test"}'
```

---

### Python Test Script

Use test script:

```bash
# Terminal 1: Subscribe
python test_mqtt.py subscribe

# Terminal 2: Publish test events
python test_mqtt.py publish --event position_opened
```

---

## 📊 Message Frequency

| Event Type | Frequency | Volume |
|------------|-----------|--------|
| heartbeat | 30s | Low |
| spike_detected | Variable | Medium (approx 5-20/min) |
| position/opened | Variable | Low (approx 0-5/min) |
| position/closed | Variable | Low (approx 0-5/min) |
| balance/update | 12h or change | Very Low |
| stats/periodic | 10s | Low |

**Total message volume:** Approx 50-200 messages/hour (very low load)

---

## ⚠️ Edge Cases

### Missing Fields

Some fields may be missing:

- `spike_magnitude` - may be null if no spike
- `market_name` - fallback to truncated token_id if API failed

**Recommendation:** Always use `.get()` with default value:

```python
market_name = payload.get("market_name", "Unknown Market")
```

---

### Duplicate Messages (QoS 1)

QoS 1 may deliver a message multiple times.

**Solution:** Track `trade_id` or timestamp and ignore duplicates:

```python
seen_trade_ids = set()

if payload["trade_id"] in seen_trade_ids:
    return  # Ignore duplicate
seen_trade_ids.add(payload["trade_id"])
```

---

### Retained Messages

On connection, you receive the last retained messages:

- `status/bot/heartbeat`
- `balance/update`
- `stats/session`

**Solution:** Ignore messages older than 5 minutes on startup:

```python
startup_time = time.time()

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload)

    # Ignore old retained messages
    if payload["timestamp"] < startup_time - 300:
        return
```

---

## 🔧 Troubleshooting

### Broker Not Available

```
ERROR: Connection refused [Errno 111]
```

**Solution:**

1. Check if Mosquitto is running: `sudo systemctl status mosquitto`
2. Start Mosquitto: `sudo systemctl start mosquitto`

---

### No Messages Arriving

1. Check if bot is running: `ps aux | grep python.*main.py`
2. Check `MQTT_ENABLED=true` in `.env`
3. Check mosquitto log: `sudo tail -f /var/log/mosquitto/mosquitto.log`

---

### Messages Arriving but JSON Parse Error

1. Check payload encoding: `msg.payload.decode('utf-8')`
2. Log raw payload before parse: `print(msg.payload)`

---

## 📚 Reference

- [MQTT Protocol](https://mqtt.org/)
- [Paho MQTT Python](https://pypi.org/project/paho-mqtt/)
- [Mosquitto Broker](https://mosquitto.org/)
- [Discord.py Docs](https://discordpy.readthedocs.io/)

---

