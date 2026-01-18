"""Create a test paper trading bot"""

import requests
import json

url = "http://localhost:8080/api/bots/create"

data = {
    "name": "Fresh ETH Paper Bot",
    "pair": "ETH/USDT",
    "timeframe": "15m",
    "mode": "demo",
    "trading_mode": "spot",
    "leverage": 1,
}

print(f"🤖 Creating bot: {data['name']}")
print(f"📊 Pair: {data['pair']}, Timeframe: {data['timeframe']}, Mode: {data['mode']}")

response = requests.post(url, json=data)

print(f"\n📡 Status: {response.status_code}")
print(f"📄 Response:")
print(json.dumps(response.json(), indent=2))
