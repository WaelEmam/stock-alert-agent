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

This project is intended for research and alerting only. It is not financial
advice and should not place trades automatically.

Disclosure: parts of this codebase and documentation were generated or
AI-assisted. Review and test the code before relying on it for alerts,
automation, or deployment.

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
cd /Users/waelemam/Documents/Projects/stock-alert-agent
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

This global `alerts` section is different from per-stock `alert_thresholds`.
Use `alerts` for app-wide Discord behavior. Use `alert_thresholds` inside a
specific watchlist item for stock-specific price, RSI, gain/loss, or score
triggers.

- `send_per_stock_review`: when `true`, allows one full Discord review message
  for each ticker in the watchlist. If a stock has `alert_thresholds`, the
  message is sent only when a threshold is breached.
- `send_daily_summary`: when `true`, sends one summary message after all stocks
  have been reviewed.
- `send_only_if_triggered`: legacy filter for per-stock messages when
  `send_per_stock_review` is `false`.
- `min_alert_score`: minimum absolute score used by the triggered-message
  filter.

With the default settings, each stock is reviewed. Discord messages are sent
only when the stock's alert rules say it should send. If a stock has
`alert_thresholds`, at least one threshold must be breached before a Discord
message is sent for that stock. The daily summary is still controlled by
`send_daily_summary`.

Important difference between run modes:

- `python main.py` uses `send_per_stock_review` and `send_daily_summary` from
  `config.yaml`. Per-stock Discord messages still respect any configured
  `alert_thresholds`.
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
- send a Discord review message per stock when `send_per_stock_review` is
  enabled and that stock's alert logic says to send
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

With this setup, `python main.py` reviews every stock. For stocks with
`alert_thresholds`, it sends a Discord review only when at least one threshold
is breached. For stocks without `alert_thresholds`, it uses the normal
score/signal alert behavior. It then sends a daily summary if
`send_daily_summary` is `true`.

To stop routine per-stock Discord messages and keep only triggered alerts for
stocks without `alert_thresholds`, use:

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

## `config.yaml` Reference

This file controls the agent, data source, alert behavior, watchlist, and rule
thresholds.

### `agent`

| Field | Example | Description |
| --- | --- | --- |
| `name` | `"Home Stock Alert Agent"` | Display name used in summaries and error messages. |
| `model` | `"gpt-4.1-mini"` | OpenAI model used when summaries are enabled and `OPENAI_API_KEY` is set. |
| `timezone` | `"America/Toronto"` | Intended timezone for the agent. Current timestamps use the container or host runtime clock. |

Example:

```yaml
agent:
  name: "Home Stock Alert Agent"
  model: "gpt-4.1-mini"
  timezone: "America/Toronto"
```

### `alerts`

Global alert settings. These are different from per-stock `alert_thresholds`.

| Field | Example | Description |
| --- | --- | --- |
| `send_per_stock_review` | `true` | Allows one Discord review per stock. If a stock has `alert_thresholds`, a message is sent only when a threshold is breached. |
| `send_daily_summary` | `false` | Sends a summary message after a full `/run`. For scheduled jobs, `false` avoids repeated summary spam. |
| `send_only_if_triggered` | `true` | Legacy score/signal filter used for stocks that do not have `alert_thresholds`. |
| `min_alert_score` | `5` | Minimum absolute score for the legacy triggered-alert filter. |

Example:

```yaml
alerts:
  send_per_stock_review: true
  send_daily_summary: false
  send_only_if_triggered: true
  min_alert_score: 5
```

### `data`

Yahoo Finance and yfinance settings.

| Field | Example | Description |
| --- | --- | --- |
| `price_provider` | `"yahoo"` | Current supported provider. The app uses Yahoo Finance through `yfinance`. |
| `yfinance.retries` | `2` | yfinance network retry count for transient failures. |
| `yfinance.debug` | `false` | Enables verbose yfinance logging when troubleshooting. |
| `yfinance.proxy` | `null` | Optional proxy URL. Leave blank unless your network requires it. |

Example:

```yaml
data:
  price_provider: "yahoo"
  yfinance:
    retries: 2
    debug: false
    proxy:
```

### `portfolio`

| Field | Example | Description |
| --- | --- | --- |
| `max_single_position_pct` | `15` | Portfolio-level reference value. The current rule engine uses `rules.risk.max_position_pct` for scoring. |

Example:

```yaml
portfolio:
  max_single_position_pct: 15
```

### `watchlist`

Each item in `watchlist` describes one stock to monitor.

| Field | Example | Description |
| --- | --- | --- |
| `ticker` | `"SNOW"` | Ticker symbol passed to Yahoo Finance. Canadian tickers can use Yahoo format such as `"RY.TO"`. |
| `name` | `"Snowflake"` | Human-readable company name. Used for context in summaries. |
| `position_pct` | `25` | Approximate percent of your portfolio in this stock. Used by position-size risk rules. |
| `cost_basis` | `125` | Your average purchase price per share. Used for gain/loss, stop-loss, take-profit, and gain/loss thresholds. |
| `strategy` | `"exit_review"` | Your reason for watching or holding the stock. Used as context in OpenAI summaries. |
| `alert_thresholds` | See below | Optional stock-specific alert triggers. If present, Discord sends only when at least one threshold is breached. |

Example:

```yaml
watchlist:
  - ticker: "SNOW"
    name: "Snowflake"
    position_pct: 25
    cost_basis: 125
    strategy: "exit_review"
    alert_thresholds:
      price_below: 160
      price_above: 190
      rsi_above: 80
```

### `watchlist[].alert_thresholds`

Optional per-stock Discord alert thresholds.

| Field | Example | Description |
| --- | --- | --- |
| `price_below` | `160` | Alert if current price is below this value. |
| `price_above` | `190` | Alert if current price is above this value. |
| `daily_change_below_pct` | `-5` | Alert if daily percentage change is below this value. |
| `daily_change_above_pct` | `5` | Alert if daily percentage change is above this value. |
| `rsi_below` | `30` | Alert if RSI is below this value. |
| `rsi_above` | `80` | Alert if RSI is above this value. |
| `gain_loss_below_pct` | `-15` | Alert if gain/loss from `cost_basis` is below this percentage. |
| `gain_loss_above_pct` | `40` | Alert if gain/loss from `cost_basis` is above this percentage. |
| `score_below` | `-5` | Alert if the rule score is below this value. |
| `score_above` | `7` | Alert if the rule score is above this value. |

Example:

```yaml
alert_thresholds:
  price_below: 160
  price_above: 190
  daily_change_below_pct: -5
  daily_change_above_pct: 5
  rsi_below: 30
  rsi_above: 80
  gain_loss_below_pct: -15
  gain_loss_above_pct: 40
  score_below: -5
  score_above: 7
```

When `alert_thresholds` exist for a stock, Discord messages for that stock are
sent only when at least one threshold is breached. JSON responses are still
returned either way.

### `rules.technical`

| Field | Example | Description |
| --- | --- | --- |
| `rsi_overbought` | `70` | RSI level that subtracts points and marks the stock as overbought. |
| `rsi_oversold` | `30` | RSI level that adds points and marks the stock as oversold. |
| `below_200dma_sell_review` | `true` | Present in config for readability. The current code always applies the below-200DMA rule when data exists. |
| `above_50dma_buy_review` | `true` | Present in config for readability. The current code always applies the above-50DMA rule when data exists. |
| `above_200dma_buy_review` | `true` | Present in config for readability. The current code always applies the above-200DMA rule when data exists. |

Example:

```yaml
rules:
  technical:
    rsi_overbought: 70
    rsi_oversold: 30
    below_200dma_sell_review: true
    above_50dma_buy_review: true
    above_200dma_buy_review: true
```

### `rules.risk`

| Field | Example | Description |
| --- | --- | --- |
| `stop_loss_pct` | `-15` | Subtracts points when the position is down this much or more from `cost_basis`. |
| `take_profit_pct` | `40` | Adds a take-profit review when the position is up this much or more from `cost_basis`. |
| `max_position_pct` | `15` | Subtracts points when `position_pct` is above this value. |

Example:

```yaml
rules:
  risk:
    stop_loss_pct: -15
    take_profit_pct: 40
    max_position_pct: 15
```

### `rules.scoring`

| Field | Example | Description |
| --- | --- | --- |
| `buy_review_threshold` | `7` | Score at or above this value becomes `BUY REVIEW`. |
| `sell_review_threshold` | `-5` | Score at or below this value becomes `SELL REVIEW`. |
| `urgent_review_threshold` | `-8` | Score at or below this value becomes `URGENT REVIEW`. |

Example:

```yaml
rules:
  scoring:
    buy_review_threshold: 7
    sell_review_threshold: -5
    urgent_review_threshold: -8
```

## Common Setup Issues

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

### `alert_thresholds`

`alert_thresholds` are optional per-stock Discord alert triggers. They let you
say, "only alert me for this stock if it goes below this price, above this
price, above this RSI, below this gain/loss percentage," and so on.

Example:

```yaml
watchlist:
  - ticker: "SNOW"
    name: "Snowflake"
    position_pct: 25
    cost_basis: 125
    strategy: "exit_review"
    alert_thresholds:
      price_below: 160
      price_above: 190
      daily_change_below_pct: -5
      daily_change_above_pct: 5
      rsi_below: 30
      rsi_above: 80
      gain_loss_below_pct: -15
      gain_loss_above_pct: 40
      score_below: -5
      score_above: 7
```

Supported threshold keys:

- `price_below`: alert if current price is below this value.
- `price_above`: alert if current price is above this value.
- `daily_change_below_pct`: alert if daily percentage change is below this
  value.
- `daily_change_above_pct`: alert if daily percentage change is above this
  value.
- `rsi_below`: alert if RSI is below this value.
- `rsi_above`: alert if RSI is above this value.
- `gain_loss_below_pct`: alert if gain/loss from `cost_basis` is below this
  percentage.
- `gain_loss_above_pct`: alert if gain/loss from `cost_basis` is above this
  percentage.
- `score_below`: alert if the rule score is below this value.
- `score_above`: alert if the rule score is above this value.

When `alert_thresholds` are configured for a stock, Discord alerts for that
stock are sent only when at least one threshold is breached. The API still
returns JSON either way.

Examples:

- If `price_below: 160` and the current price is `155`, the threshold is
  breached and Discord can send.
- If `price_below: 160` and the current price is `170`, the threshold is not
  breached and no Discord message is sent for that stock.
- If `rsi_above: 80` and RSI is `85`, the threshold is breached.
- If `gain_loss_below_pct: -15` and the position is down `20%` from
  `cost_basis`, the threshold is breached.

If a stock does not have `alert_thresholds`, the agent falls back to the normal
score/signal alert behavior controlled by:

```yaml
alerts:
  send_only_if_triggered: false
  min_alert_score: 5
```

The API response includes `threshold_result`:

```json
{
  "threshold_result": {
    "configured": true,
    "breached": true,
    "breaches": [
      {
        "key": "rsi_above",
        "label": "RSI",
        "direction": "above",
        "current": 85.4,
        "threshold": 80,
        "message": "RSI is above threshold: 85.40 > 80.00"
      }
    ]
  }
}
```

The Discord message also includes an **Alert Thresholds** section showing which
thresholds were breached, or that thresholds were configured but none were
breached.

## Running From A Fresh Terminal

Each time you open a new terminal, activate the virtual environment before
running the project:

```bash
cd /Users/waelemam/Documents/Projects/stock-alert-agent
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

By default the app reads `config.yaml` from the current working directory. In
Docker, set `CONFIG_PATH` to point at the mounted config file.

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

The included `docker-compose.yml` uses the published Docker Hub image and starts
two containers:

- `stock-alert-agent`: the FastAPI service
- `stock-alert-scheduler`: an Alpine cron sidecar that can call the API on a
  schedule

Start the service:

```bash
docker compose up -d
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
- mounts `/containers/stock-alert-agent` at `/config` as read-only
- sets `CONFIG_PATH=/config/config.yaml`
- mounts `/containers/stock-alert-agent/crontab` into the scheduler container

Stop the service:

```bash
docker compose down
```

### Deploy From Docker Hub With Docker Compose

Use this style when the image is already published to Docker Hub and the server
should pull it instead of building locally.

Example `docker-compose.yml`:

```yaml
services:
  stock-alert-agent:
    image: waelemam/stock-alert-agent:1.1.1
    container_name: stock-alert-agent
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL}
      - STOCK_AGENT_API_KEY=${STOCK_AGENT_API_KEY}
      - CONFIG_PATH=/config/config.yaml
    ports:
      - "8898:8000"
    volumes:
      - /containers/stock-alert-agent:/config:ro
    restart: unless-stopped

  stock-alert-scheduler:
    image: alpine:latest
    container_name: stock-alert-scheduler
    depends_on:
      - stock-alert-agent
    environment:
      - STOCK_AGENT_API_KEY=${STOCK_AGENT_API_KEY}
    volumes:
      - /containers/stock-alert-agent/crontab:/etc/crontabs/root:ro
    command: >
      sh -c "apk add --no-cache curl && crond -f -l 8"
    restart: unless-stopped
```

Create the host folder:

```bash
mkdir -p /containers/stock-alert-agent
```

Create the host config file:

```bash
nano /containers/stock-alert-agent/config.yaml
```

Paste your `config.yaml` content into that file. The volume mount points the
host config folder into the container:

```text
/containers/stock-alert-agent
```

The app reads the file from:

```text
/config/config.yaml
```

This directory-mount approach is recommended over mounting a single file. Some
editors save files by replacing the file inode, and single-file Docker bind
mounts can keep pointing at the old file until the container is recreated.
Mounting the directory avoids that problem, so changes to `config.yaml` are
picked up on the next `/run` or `/analyze/{ticker}` request.

Create the scheduler crontab file:

```bash
nano /containers/stock-alert-agent/crontab
```

This file must exist on the host before starting the stack because it is mounted
into the scheduler container.

Example: run the full watchlist every 10 minutes, send Discord only when stock
alert logic says to send, skip OpenAI summaries, and skip daily summaries:

```cron
*/10 * * * * curl -s -X POST http://stock-alert-agent:8000/run -H "X-API-Key: ${STOCK_AGENT_API_KEY}" -H "Content-Type: application/json" -d '{"include_summary":false,"send_discord":true,"send_daily_summary":false}'
```

Inside Docker Compose, the scheduler calls the API service by container/service
name:

```text
http://stock-alert-agent:8000
```

Do not use `localhost:8000` inside the scheduler container. In that container,
`localhost` means the scheduler container itself.

The `*/10 * * * *` cron expression runs at minute `0`, `10`, `20`, `30`, `40`,
and `50` of every hour. It is based on the container clock, not on when the
container started.

The scheduler uses `alpine:latest` and installs `curl` when it starts:

```yaml
command: >
  sh -c "apk add --no-cache curl && crond -f -l 8"
```

Start the stack:

```bash
docker compose up -d
```

Check logs:

```bash
docker compose logs -f stock-alert-agent
docker compose logs -f stock-alert-scheduler
```

Open the API:

```text
http://SERVER_IP:8898
```

This redirects to:

```text
http://SERVER_IP:8898/docs
```

#### Environment Variables For Compose

If your compose file uses:

```yaml
environment:
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL}
  - STOCK_AGENT_API_KEY=${STOCK_AGENT_API_KEY}
  - CONFIG_PATH=/config/config.yaml
```

then define those variables in the same environment where Compose runs, or put
them in a `.env` file next to `docker-compose.yml`:

```bash
OPENAI_API_KEY=sk-...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
STOCK_AGENT_API_KEY=replace-with-a-long-random-secret
```

Use `${VAR_NAME}` syntax, not `{VAR_NAME}`.

#### Config Changes Not Appearing In The Container

If edits to `config.yaml` only appear after restarting the container, you are
probably using a single-file bind mount like this:

```yaml
volumes:
  - /containers/stock-alert-agent/config.yaml:/app/config.yaml:ro
```

Use a directory bind mount instead:

```yaml
environment:
  - CONFIG_PATH=/config/config.yaml
volumes:
  - /containers/stock-alert-agent:/config:ro
```

Then verify the container sees the current config:

```bash
docker exec stock-alert-agent cat /config/config.yaml
```

The app reloads the config file on each API request, so no restart is needed
after threshold edits when the directory mount is used.

#### Fixing Config Mount Errors

If you see an error like:

```text
not a directory: Are you trying to mount a directory onto a file (or vice-versa)?
```

Docker is telling you that the host path and container path do not have the same
type. With the recommended directory mount, the host path should be a directory:

```bash
file /containers/stock-alert-agent
ls -la /containers/stock-alert-agent/config.yaml
```

You want `/containers/stock-alert-agent` to be a directory and
`/containers/stock-alert-agent/config.yaml` to be a file.

If Docker accidentally created `config.yaml` as a directory, remove it and
recreate it as a file:

```bash
rm -r /containers/stock-alert-agent/config.yaml
nano /containers/stock-alert-agent/config.yaml
```

Then redeploy:

```bash
docker compose up -d
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
exist in `config.yaml`. The response includes `threshold_result` when
per-stock `alert_thresholds` are configured.

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

If `"send_discord": true`, Discord sends only when the stock's alert logic says
to send. For stocks with `alert_thresholds`, that means at least one threshold
must be breached.

#### `POST /run`

Runs the full watchlist from `config.yaml`. Each result includes
`threshold_result` when that stock has per-stock `alert_thresholds`.

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

For stocks with `alert_thresholds`, Discord sends only when at least one
threshold is breached. Stocks without `alert_thresholds` use the normal
score/signal alert behavior.

### Docker Files

- `Dockerfile`: builds the FastAPI container.
- `docker-compose.yml`: local service runner with `.env`, port mapping, and
  mounted `config.yaml`.
- `.dockerignore`: keeps local secrets, virtual environments, and cache files
  out of the image.
