# Stock Alert Agent

A lightweight stock monitoring and research alert agent that can run as a
script or as a Dockerized FastAPI service.

The agent:
- Monitors a stock watchlist from `config.yaml`
- Pulls market, basic fundamental, and news data using Yahoo Finance through
  `yfinance`
- Calculates simple technical indicators
- Evaluates rule-based buy-review, hold/watch, sell-review, and urgent-review signals
- Uses OpenAI to generate a concise research summary
- Optionally sends alerts to Discord using a Discord webhook

This project is intended for research and alerting only. It is not financial advice and should not place trades automatically.

---

## How the Agent Works

The agent follows this workflow:

1. Read your watchlist and rules from `config.yaml`
2. Fetch stock data for each ticker
3. Calculate indicators such as:
   - Current price
   - Daily price change
   - 50-day moving average
   - 200-day moving average
   - RSI
4. Compare the stock against your rules
5. Assign a signal:
   - `BUY REVIEW`
   - `HOLD / WATCH`
   - `SELL REVIEW`
   - `URGENT REVIEW`
6. Ask OpenAI to explain the signal in plain English
7. Return JSON from the API or optionally send the result to Discord

The OpenAI model does not decide trades by itself. The code generates the signal from your rules, and the model explains the result.

---

## Requirements

- Python 3.10 or newer
- Optional: a Discord server where you can create a webhook
- Optional but recommended: an OpenAI API key

If you do not provide an OpenAI API key, the rule-based alerts can still run, but the research summary will be skipped.

---

## Setup

These steps assume you are working from this project folder:

```bash
cd Documents/Projects/stock-alert-agent
```

### 1. Confirm Python is installed

Check that Python 3 is available:

```bash
python3 --version
```

You should see a Python 3 version, such as `Python 3.10.x`, `Python 3.11.x`, or
`Python 3.12.x`.

### 2. Create a virtual environment

A virtual environment keeps this project's Python packages separate from your
global Python installation.

```bash
python3 -m venv venv
```

This creates a local folder named `venv`.

### 3. Activate the virtual environment

On macOS or Linux:

```bash
source venv/bin/activate
```

When the environment is active, your terminal prompt usually shows `(venv)`.

If you ever want to leave the virtual environment, run:

```bash
deactivate
```

### 4. Upgrade pip

This step is optional, but it helps avoid package installer issues:

```bash
python -m pip install --upgrade pip
```

### 5. Install dependencies

Install the packages used by the project:

```bash
pip install -r requirments.txt
```

Important: the dependency file in this project is currently named
`requirments.txt`, not `requirements.txt`.

The main packages are:

- `yfinance`: fetches stock prices, fundamentals, and news
- `fastapi`: exposes the HTTP API
- `uvicorn`: runs the FastAPI service
- `requests`: sends messages to Discord
- `pandas` and `numpy`: calculate indicators and handle market data
- `openai`: creates the optional research summary
- `python-dotenv`: loads local secrets from `.env`
- `PyYAML`: reads `config.yaml`

### 6. Create the `.env` file

Create a file named `.env` in the project folder.

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
OPENAI_API_KEY="sk-..."
STOCK_AGENT_API_KEY="replace-with-a-long-random-secret"
```

`DISCORD_WEBHOOK_URL` is required only when you want the agent to send Discord
messages. JSON-only API calls can run without it.

`OPENAI_API_KEY` is optional. If it is missing, the agent still runs, but the
OpenAI research summary is skipped.

`STOCK_AGENT_API_KEY` is required for protected API endpoints:

- `GET /watchlist`
- `POST /run`
- `POST /analyze/{ticker}`

It is not required for `GET /` or `GET /health`.

### 7. Review `config.yaml`

Before running the project, review the watchlist and rules in `config.yaml`.

Example watchlist item:

```yaml
watchlist:
  - ticker: "AAPL"
    name: "Apple"
    position_pct: 5
    cost_basis: 150
    strategy: "long_term_growth"
```

Important fields:

- `ticker`: stock symbol to monitor
- `position_pct`: approximate percentage of your portfolio in this stock
- `cost_basis`: your average purchase price per share
- `strategy`: your own label for why you are watching or holding the stock.
  See the strategy options section below.

Yahoo Finance settings:

```yaml
data:
  price_provider: "yahoo"
  yfinance:
    retries: 2
    debug: false
    proxy:
```

- `price_provider`: currently set to `yahoo`. The project uses `yfinance` and
  does not require another finance API key.
- `retries`: yfinance's built-in retry count for transient network errors.
- `debug`: when `true`, enables verbose yfinance logging and stops yfinance from
  hiding exceptions.
- `proxy`: optional proxy server. Leave this blank unless your network requires
  one.

Discord alert settings:

```yaml
alerts:
  send_per_stock_review: true
  send_daily_summary: true
  send_only_if_triggered: false
  min_alert_score: 5
```

- `send_per_stock_review`: when `true`, sends one full Discord review message
  for each ticker in the watchlist.
- `send_daily_summary`: when `true`, sends one summary message after all stocks
  have been reviewed.
- `send_only_if_triggered`: legacy filter for per-stock messages when
  `send_per_stock_review` is `false`.
- `min_alert_score`: minimum absolute score used by the triggered-message
  filter.

With the default settings, two watchlist stocks produce three Discord messages:
one review for each stock, then one daily summary.

Important difference between run modes:

- `python main.py` uses `send_per_stock_review` and `send_daily_summary` from
  `config.yaml`, so it sends Discord messages by default when
  `DISCORD_WEBHOOK_URL` is set.
- FastAPI endpoints do not send Discord messages by default. For API calls, set
  `send_discord` to `true` in the request body.

### 8. Run the agent

Run:

```bash
python main.py
```

The agent will:

- load `.env`
- load `config.yaml`
- check each ticker in the watchlist
- fetch stock data using `yfinance`
- evaluate the technical, risk, and fundamental rules
- generate an OpenAI summary if `OPENAI_API_KEY` is configured
- send one Discord review message per stock when `send_per_stock_review` is
  enabled
- send a daily summary if enabled in `config.yaml`

## Enabling Discord Messages

Discord sending has two parts:

1. Add a Discord webhook URL to `.env`.
2. Enable sending for the run mode you are using.

### 1. Add The Webhook

Create or update `.env`:

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

Keep `.env` private. It is listed in `.gitignore` and `.dockerignore`.

### 2. Enable Discord For `python main.py`

For the script runner, Discord behavior comes from `config.yaml`:

```yaml
alerts:
  send_per_stock_review: true
  send_daily_summary: true
  send_only_if_triggered: false
  min_alert_score: 5
```

With this setup, `python main.py` sends one full Discord review per stock and
then sends a daily summary.

To stop per-stock Discord messages but keep only triggered alerts, use:

```yaml
alerts:
  send_per_stock_review: false
  send_only_if_triggered: true
  min_alert_score: 5
```

To disable the daily summary:

```yaml
alerts:
  send_daily_summary: false
```

### 3. Enable Discord For FastAPI Or Docker

API calls are JSON-only unless the request body includes:

```json
{
  "send_discord": true
}
```

For Docker or Docker Compose, `.env` is passed into the container. The compose
file already includes:

```yaml
env_file:
  - .env
```

So the container can send Discord messages as long as `.env` contains
`DISCORD_WEBHOOK_URL` and the API request sets `send_discord` to `true`.

## API Key Authentication

The FastAPI service protects the operational endpoints with an API key. Add this
to `.env`:

```bash
STOCK_AGENT_API_KEY="replace-with-a-long-random-secret"
```

Use the key in the `X-API-Key` header:

```bash
curl http://localhost:8000/watchlist \
  -H "X-API-Key: replace-with-a-long-random-secret"
```

Protected endpoints:

- `GET /watchlist`
- `POST /run`
- `POST /analyze/{ticker}`

Public endpoints:

- `GET /`
- `GET /health`

If `STOCK_AGENT_API_KEY` is not set, protected endpoints return `503`. If the
header is missing or wrong, they return `401`.

### 9. Run it again later

The script runs once and exits. To check the stocks again, run:

```bash
python main.py
```

To run it automatically every day, use a scheduler such as cron, launchd, GitHub
Actions, or another automation tool.

## Common Setup Issues

### `pip install -r requirements.txt` fails

Use the current filename:

```bash
pip install -r requirments.txt
```

The project file is misspelled as `requirments.txt`.

### `Missing DISCORD_WEBHOOK_URL in .env` When Sending Discord Messages

This only matters when `python main.py` is configured to send Discord messages
or an API request uses `"send_discord": true`.

Make sure `.env` exists in the project folder and includes:

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

### OpenAI summaries are skipped

Add this to `.env`:

```bash
OPENAI_API_KEY="sk-..."
```

Or leave it unset if you only want rule-based Discord alerts.

### Yahoo Finance connection error

If you see an error like this:

```text
Failed to connect to fc.yahoo.com port 443
```

The code is failing while `yfinance` tries to connect to Yahoo Finance. This is
usually not a ticker problem. It is usually one of these:

- temporary Yahoo Finance availability issue
- internet connection issue
- VPN or firewall blocking Yahoo Finance
- DNS issue
- corporate or school network blocking `fc.yahoo.com`

Things to try:

```bash
python main.py
```

Run it again after a minute. The code now uses yfinance's network retry config
and also retries the required price-history request before failing.

To get more detail from yfinance, temporarily enable debug mode:

```yaml
data:
  price_provider: "yahoo"
  yfinance:
    retries: 2
    debug: true
    proxy:
```

Then rerun:

```bash
python main.py
```

If it still fails, test direct access to Yahoo's endpoint:

```bash
curl -I https://fc.yahoo.com
```

If that command cannot connect, the issue is network access to Yahoo Finance,
not the Python code.

If your error includes `curl:` and `curl_cffi` is installed, try the yfinance
documented requests fallback. First check whether `curl_cffi` is installed:

```bash
python -c "import importlib.util; print(importlib.util.find_spec('curl_cffi') is not None)"
```

If it prints `True`, reinstall yfinance without `curl_cffi`:

```bash
pip uninstall -y yfinance curl_cffi
curl -fsSL https://raw.githubusercontent.com/ranaroussi/yfinance/main/requirements.txt | grep -vi '^curl_cffi' | pip install -r /dev/stdin
pip install --no-deps yfinance
```

Then verify:

```bash
python -c "import importlib.util, yfinance as yf; print(yf.__version__); print(importlib.util.find_spec('curl_cffi') is None)"
```

After that, rerun:

```bash
python main.py
```

If your network requires a proxy, set it in `config.yaml`:

```yaml
data:
  price_provider: "yahoo"
  yfinance:
    retries: 2
    debug: false
    proxy: "http://your-proxy-server:port"
```

You can also try disconnecting from VPN, changing Wi-Fi networks, or running the
agent from a home network instead of a restricted network.

## Watchlist Fields

### `position_pct`

`position_pct` means the size of the position as a percentage of your total
portfolio.

Example:

```yaml
position_pct: 10
```

This means the stock is about 10% of your portfolio. The rule engine compares
this value to `rules.risk.max_position_pct`. If the position is larger than the
allowed maximum, the score is reduced.

### `cost_basis`

`cost_basis` means your average purchase price per share.

Example:

```yaml
cost_basis: 150
```

If the current price is `$120`, the position is down 20%:

```text
((120 - 150) / 150) * 100 = -20%
```

If the current price is `$210`, the position is up 40%:

```text
((210 - 150) / 150) * 100 = 40%
```

The agent uses this value for stop-loss and take-profit checks.

### `strategy`

`strategy` is a label that explains why the stock is in your watchlist or
portfolio.

Example:

```yaml
strategy: "long_term_growth"
```

The current code does not use `strategy` to change the numeric score. It is
included in the watch item that gets sent to OpenAI, so it helps the research
summary understand the context of the position.

You can technically use any text value, but keeping a consistent set of options
makes the alerts easier to read.

Recommended strategy options:

- `long_term_growth`: For companies you want to hold for multiple years because
  you expect revenue, earnings, or market share to grow over time.
- `short_term_growth`: For positions you are watching over a shorter timeframe,
  usually because of recent momentum, news, earnings, or a near-term catalyst.
- `growth_momentum`: For stocks that are rising strongly and where price trend
  is an important part of the thesis.
- `value`: For stocks you believe may be undervalued compared with earnings,
  assets, cash flow, or long-term business quality.
- `dividend_income`: For stocks held mainly for dividends, income, or yield
  stability.
- `core_holding`: For a major long-term portfolio position that you expect to
  keep unless the thesis changes significantly.
- `defensive`: For lower-volatility or more stable companies intended to reduce
  portfolio risk during weaker markets.
- `turnaround`: For companies where the thesis depends on recovery, improving
  operations, new management, or a business reset.
- `speculative`: For higher-risk positions where the outcome is less certain
  and position sizing should usually be smaller.
- `watch_only`: For stocks you do not own yet but want the agent to monitor.
- `exit_review`: For positions you are actively considering trimming or selling
  if risk signals continue.

Example watchlist using different strategies:

```yaml
watchlist:
  - ticker: "SNOW"
    name: "Snowflake"
    position_pct: 25
    cost_basis: 125
    strategy: "short_term_growth"

  - ticker: "RY.TO"
    name: "Royal Bank of Canada"
    position_pct: 75
    cost_basis: 140
    strategy: "long_term_growth"

  - ticker: "KO"
    name: "Coca-Cola"
    position_pct: 0
    cost_basis: 0
    strategy: "watch_only"
```

## Running From A Fresh Terminal

Each time you open a new terminal, activate the virtual environment before
running the project:

```bash
cd Documents/Projects/stock-alert-agent
source venv/bin/activate
python main.py
```

## FastAPI Service

The project can also run as a Dockerized FastAPI service.

Structure:

```text
Docker container
  FastAPI app
    GET  /health
    POST /run
    GET  /watchlist
    POST /analyze/{ticker}
```

### API Behavior

- Loads `config.yaml`
- Fetches stock data with `yfinance`
- Evaluates the configured rules
- Optionally generates OpenAI summaries
- Returns JSON responses
- Optionally sends Discord alerts from inside the container

Discord sending is off by default for API calls. Set `send_discord` to `true`
in the request body when you want the container to send Discord messages.

For Discord messages from Docker, make sure `.env` contains
`DISCORD_WEBHOOK_URL`, start the container, then call `/run` or
`/analyze/{ticker}` with `"send_discord": true`.

### Run Locally With FastAPI

Install dependencies:

```bash
source venv/bin/activate
pip install -r requirments.txt
```

Start the API:

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

This redirects to the interactive Swagger UI:

```text
http://localhost:8000/docs
```

### Run With Docker Compose

Build and start the service:

```bash
docker compose up --build
```

The API will be available at:

```text
http://localhost:8000
```

That redirects to the interactive docs:

```text
http://localhost:8000/docs
```

The compose file:

- reads secrets from `.env`
- exposes port `8000`
- mounts local `config.yaml` into the container as read-only

Stop the service:

```bash
docker compose down
```

### Run With Docker Directly

Build the image:

```bash
docker build -t stock-alert-agent .
```

Run the container:

```bash
docker run --rm \
  --env-file .env \
  -p 8000:8000 \
  -v "$(pwd)/config.yaml:/app/config.yaml:ro" \
  stock-alert-agent
```

### API Endpoints

#### `GET /health`

Checks whether the service is alive and whether config/secrets are available.

```bash
curl http://localhost:8000/health
```

Example response:

```json
{
  "status": "ok",
  "config_loaded": true,
  "watchlist_count": 2,
  "openai_configured": true,
  "discord_configured": true,
  "api_auth_configured": true
}
```

#### `GET /watchlist`

Returns the current agent settings, alert settings, data settings, watchlist,
and rules from `config.yaml`.

```bash
curl http://localhost:8000/watchlist \
  -H "X-API-Key: replace-with-a-long-random-secret"
```

#### `POST /analyze/{ticker}`

Analyzes one ticker and returns JSON. This does not need the ticker to already
exist in `config.yaml`.

```bash
curl -X POST http://localhost:8000/analyze/SNOW \
  -H "X-API-Key: replace-with-a-long-random-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "include_summary": true,
    "send_discord": false
  }'
```

You can override watchlist context for one request:

```bash
curl -X POST http://localhost:8000/analyze/SNOW \
  -H "X-API-Key: replace-with-a-long-random-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "include_summary": true,
    "send_discord": true,
    "position_pct": 10,
    "cost_basis": 125,
    "strategy": "short_term_growth"
  }'
```

#### `POST /run`

Runs the full watchlist from `config.yaml`.

```bash
curl -X POST http://localhost:8000/run \
  -H "X-API-Key: replace-with-a-long-random-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "include_summary": true,
    "send_discord": false
  }'
```

To send Discord messages from inside the container:

```bash
curl -X POST http://localhost:8000/run \
  -H "X-API-Key: replace-with-a-long-random-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "include_summary": true,
    "send_discord": true,
    "send_daily_summary": true
  }'
```

### Docker Files

- `Dockerfile`: builds the FastAPI container.
- `docker-compose.yml`: local service runner with `.env`, port mapping, and
  mounted `config.yaml`.
- `.dockerignore`: keeps local secrets, virtual environments, and cache files
  out of the image.
