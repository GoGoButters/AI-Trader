# AI-Trader Orchestrator v2.0

A powerful automated trading platform with AI-driven news analysis, real-time sentiment scoring, and persistent memory.

## 🚀 Features

- **Multi-Bot Management**: Create and control multiple paper/live trading bots from a single UI.
- **AI News Analysis**: Real-time news fetching via SearXNG/Perplexica, analyzed by LLMs for market impact.
- **MACD + RSI Strategy**: Professional-grade technical indicators with MACD confirmation toggle.
- **Persistent AI Memory**: Integrated with **Graphiti** to remember historical market patterns and news impacts.
- **Exchange Integration**: Secure management of KuCoin API keys.
- **Real-Time Monitoring**: Live charts (Lightweight Charts) and system logs.
- **CI/CD Ready**: Integrated GitHub Actions for linting and Docker verification.

## 🛠 Prerequisites

- **Docker & Docker Compose**
- **SearXNG**: For news searching (included in docker-compose).
- **Graphiti Memory Service**: Required for persistent AI memory.
- **LLM API Key**: OpenAI-compatible endpoint (e.g., OpenRouter, Local LLM).

## 📦 Quick Start (Linux/Docker)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/GoGoButters/AI-Trader.git
   cd AI-Trader
   ```

2. **Configure `config.yml`**:
   Update the `services` and `models` sections with your API keys and service URLs.
   ```yaml
   services:
     graphiti: "url: http://YOUR_GRAPHITI_IP:8001; token: YOUR_SECRET"
     searxng: "url: http://searxng:8080"
   
   models:
     primary_analysis: "model: YOUR_MODEL; api_base: YOUR_URL; api_key: YOUR_KEY"
   ```

3. **Launch with Docker Compose**:
   ```bash
   docker-compose up -d
   ```

4. **Access the UI**:
   Open `http://localhost:3000` in your browser.

## 🏗 Architecture

- **Frontend**: Vanilla JS + CSS, Lightweight Charts.
- **Backend**: FastAPI (Python 3.11), SQLAlchemy, SQLite.
- **Trading Engine**: `ccxt` for exchange interaction, `ta` for indicators.
- **AI Logic**: Custom `NewsProcessor` using LLMs and Graphiti for context.

## 📊 Strategy: RSI + MACD

The default strategy uses a combination of Relative Strength Index (RSI) and Moving Average Convergence Divergence (MACD):

- **BUY Signal**: RSI < 40 (Oversold) + MACD Bullish Crossover.
- **SELL Signal**: RSI > 60 (Overbought) + MACD Bearish Crossover.
- *MACD can be disabled in bot settings to use RSI-only signals.*

## 🔒 Security

API Keys are stored encrypted in the local SQLite database. Never share your `config.yml` or database files containing secrets.

## 📄 License

Apache License 2.0
