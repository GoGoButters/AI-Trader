# AI-Trader 🤖📈

AI-powered cryptocurrency trading bot with news sentiment analysis and memory-based decision making.

## Features

- **Paper Trading** - Risk-free demo mode with realistic simulation
- **RSI + MACD Strategy** - Technical analysis with configurable indicators
- **Perplexica AI Search** - AI-enhanced news search with LLM-powered analysis
- **Multi-Timeframe News Impact** - News impact coefficients for all KuCoin timeframes (1m to 1w)
- **Memory System** - Graphiti-powered memory for pattern recognition
- **Multi-pair Support** - Trade BTC, ETH, SOL and more on KuCoin
- **Leverage Trading** - Spot, Margin (10x), and Futures (125x)

## Prerequisites

### Required Services

1. **Graphiti Memory Server** - External memory service

   ```bash
   git clone https://github.com/GoGoButters/Graphiti_Awesome_Memory
   cd Graphiti_Awesome_Memory
   docker-compose up -d
   ```

2. **LLM API** - OpenAI-compatible endpoint (LiteLLM, vLLM, OpenRouter, etc.)

3. **Docker & Docker Compose** - For containerized deployment

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/GoGoButters/AI-Trader.git
cd AI-Trader
```

### 2. Configure Services

Edit `config.yml` with your API endpoints:

```yaml
services:
  # Graphiti Memory Service
  graphiti: "url: http://YOUR_GRAPHITI_IP:8001; token: your-api-key"
  
  # Perplexica AI Search - uses your LLM for enhanced search
  perplexica:
    url: http://perplexica-search:3000
    llm:
      base_url: http://YOUR_LLM_IP:4000/v1
      api_key: your-llm-api-key
      model: openai/gpt-4  # Or your custom model
    embeddings:
      base_url: http://YOUR_LLM_IP:4000/v1
      api_key: your-embedding-api-key
      model: text-embedding-3-small
  
  # SearXNG (backend for Perplexica)
  searxng: "url: http://searxng:8080"

models:
  # LLM for news analysis
  primary_analysis: "model: gpt-4; api_base: http://YOUR_LLM_IP:4000/v1; api_key: your-key"
```

### 3. Generate Environment Files

```bash
cd orchestrator
python generate_env.py
```

This generates:

- `perplexica.env` - Environment variables for Docker
- `perplexica-config/config.json` - Perplexica settings with your models

### 4. Deploy with Docker

```bash
docker-compose up -d
```

### 5. Access Dashboard

- **UI**: <http://localhost:3001>
- **API Docs**: <http://localhost:8080/docs>
- **Perplexica**: <http://localhost:3000>

## Configuration

### config.yml Structure

| Section | Description |
|---------|-------------|
| `services.graphiti` | Memory server URL and token |
| `services.perplexica` | AI search with LLM and embeddings config |
| `services.searxng` | News search backend URL |
| `models.primary_analysis` | LLM for news classification |
| `models.embeddings` | Embeddings model for similarity |
| `database` | SQLite or PostgreSQL settings |
| `orchestrator` | Bot limits, CORS, trading defaults |

### Trading Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rsi_oversold` | 40 | Buy when RSI below |
| `rsi_overbought` | 60 | Sell when RSI above |
| `macd_enabled` | true | Require MACD confirmation |
| `stop_loss` | -5% | Stop loss percentage |
| `take_profit` | 10% | Take profit percentage |

### Supported Timeframes

All 13 KuCoin timeframes are supported:

- `1m`, `3m`, `5m`, `15m`, `30m`
- `1h`, `2h`, `4h`, `6h`, `8h`, `12h`
- `1d`, `1w`

Each timeframe has its own news impact coefficient for accurate analysis.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI-Trader System                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Frontend  │  │ Orchestrator│  │    Perplexica       │  │
│  │   (UI)      │──│   (FastAPI) │──│ (AI News Search)    │  │
│  │  Port 3001  │  │  Port 8080  │  │    Port 3000        │  │
│  └─────────────┘  └──────┬──────┘  └──────────┬──────────┘  │
│                          │                     │             │
│         ┌────────────────┼─────────────────────┤             │
│         ▼                ▼                     ▼             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   SQLite    │  │    LLM      │  │    SearXNG          │  │
│  │  Database   │  │  (External) │  │  (Meta-Search)      │  │
│  └─────────────┘  └──────┬──────┘  └─────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│                   ┌─────────────┐                            │
│                   │   Graphiti  │                            │
│                   │Memory Server│                            │
│                   └─────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

## API Endpoints

### Bots

- `POST /api/bots/create` - Create new trading bot
- `GET /api/bots/list` - List all bots
- `POST /api/bots/{id}/start` - Start bot
- `POST /api/bots/{id}/stop` - Stop bot
- `GET /api/bots/{id}/trades` - Get bot trade history

### News

- `GET /api/news/list` - Get analyzed news articles
- `GET /api/news/coefficients` - Get impact coefficients

### Logs

- `GET /api/logs/recent` - Get system logs

## Workflow

### Updating Models

```bash
# 1. Edit config.yml with new model settings
# 2. Regenerate environment files
cd orchestrator
python generate_env.py

# 3. Restart containers
docker-compose up -d --build
```

## Development

### Local Setup

```bash
# Install dependencies
pip install -r orchestrator/backend/requirements.txt

# Run locally
cd orchestrator
python run_orchestrator.py
```

### Testing

```bash
pytest orchestrator/backend/tests -v
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request
