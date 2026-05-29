import os
import json
import time
import math
import yaml
import requests
import yfinance as yf
import pandas as pd
import numpy as np

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv
from openai import OpenAI


# ----------------------------
# Environment and config
# ----------------------------

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def load_config(path=None):
    config_path = path or os.getenv("CONFIG_PATH", "config.yaml")

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# ----------------------------
# Technical indicators
# ----------------------------

def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.rolling(period).mean()
    avg_loss = losses.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    latest = rsi.iloc[-1]
    if pd.isna(latest):
        return 50.0

    return float(latest)


def pct_change(current, reference):
    if reference is None or reference == 0 or pd.isna(reference):
        return None
    return ((current - reference) / reference) * 100


def get_agent_now(config):
    timezone_name = config.get("agent", {}).get("timezone")

    if timezone_name:
        try:
            return datetime.now(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            pass

    return datetime.now()


# ----------------------------
# Data fetcher
# ----------------------------

def configure_yfinance(config):
    data_config = config.get("data", {}) if config else {}
    yfinance_config = data_config.get("yfinance", {})

    if not hasattr(yf, "config"):
        return

    yf.config.network.retries = yfinance_config.get("retries", 2)

    proxy = yfinance_config.get("proxy") or os.getenv("YFINANCE_PROXY")
    if proxy:
        yf.config.network.proxy = proxy

    debug = yfinance_config.get("debug", False)
    yf.config.debug.logging = debug
    yf.config.debug.hide_exceptions = not debug


def normalize_yfinance_download(hist, ticker: str):
    if hist is None or hist.empty:
        return pd.DataFrame()

    if isinstance(hist.columns, pd.MultiIndex):
        if ticker in hist.columns.get_level_values(0):
            hist = hist[ticker]
        elif ticker in hist.columns.get_level_values(-1):
            hist = hist.xs(ticker, axis=1, level=-1)

    return hist.dropna(how="all")


def fetch_yahoo_history_once(ticker: str):
    stock = yf.Ticker(ticker)
    errors = []

    try:
        hist = stock.history(
            period="1y",
            interval="1d",
            auto_adjust=True,
            timeout=20,
            raise_errors=True,
        )

        if hist is not None and not hist.empty:
            return hist, stock

    except TypeError:
        try:
            hist = stock.history(
                period="1y",
                interval="1d",
                auto_adjust=True,
                timeout=20,
            )

            if hist is not None and not hist.empty:
                return hist, stock

        except Exception as e:
            errors.append(f"Ticker.history: {e}")

    except Exception as e:
        errors.append(f"Ticker.history: {e}")

    try:
        hist = yf.download(
            tickers=ticker,
            period="1y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=20,
            multi_level_index=False,
        )
        hist = normalize_yfinance_download(hist, ticker)

        if hist is not None and not hist.empty:
            return hist, stock

    except Exception as e:
        errors.append(f"yf.download: {e}")

    raise ValueError(
        f"No Yahoo Finance price history returned for {ticker}. "
        f"{' | '.join(errors)}"
    )


def fetch_yahoo_history_with_retries(ticker: str, attempts: int = 3, delay_seconds: int = 5):
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            return fetch_yahoo_history_once(ticker)

        except Exception as e:
            last_error = e

        if attempt < attempts:
            print(
                f"Yahoo Finance fetch failed for {ticker} "
                f"(attempt {attempt}/{attempts}). Retrying in {delay_seconds}s..."
            )
            time.sleep(delay_seconds)

    raise RuntimeError(
        f"Could not fetch Yahoo Finance price data for {ticker} after "
        f"{attempts} attempts. This is usually a network, firewall, VPN, DNS, "
        f"or temporary Yahoo Finance availability issue. Original error: {last_error}"
    )


def fetch_stock_data(ticker: str, config=None):
    hist, stock = fetch_yahoo_history_with_retries(ticker)
    price_provider = "yahoo"

    if hist.empty:
        raise ValueError(f"No price history found for {ticker}")

    close = hist["Close"]

    current_price = float(close.iloc[-1])
    previous_close = float(close.iloc[-2]) if len(close) > 1 else current_price

    sma_50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    rsi = calculate_rsi(close)

    info = {}
    news_items = []

    if price_provider == "yahoo":
        try:
            info = stock.info or {}
        except Exception:
            info = {}

        try:
            raw_news = stock.news or []
            for item in raw_news[:5]:
                news_items.append({
                    "title": item.get("title"),
                    "publisher": item.get("publisher"),
                    "link": item.get("link"),
                    "provider_publish_time": item.get("providerPublishTime"),
                })
        except Exception:
            pass

    return {
        "ticker": ticker,
        "price_provider": price_provider,
        "current_price": current_price,
        "previous_close": previous_close,
        "daily_change_pct": pct_change(current_price, previous_close),
        "sma_50": sma_50,
        "sma_200": sma_200,
        "rsi": rsi,
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "price_to_sales": info.get("priceToSalesTrailing12Months"),
        "profit_margins": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "analyst_recommendation": info.get("recommendationKey"),
        "target_mean_price": info.get("targetMeanPrice"),
        "news": news_items,
    }


# ----------------------------
# Rule engine
# ----------------------------

def evaluate_rules(stock_data, watch_item, config):
    rules = config["rules"]
    technical = rules["technical"]
    risk = rules["risk"]

    score = 0
    triggered = []
    warnings = []

    ticker = stock_data["ticker"]
    price = stock_data["current_price"]
    sma_50 = stock_data["sma_50"]
    sma_200 = stock_data["sma_200"]
    rsi = stock_data["rsi"]

    cost_basis = watch_item.get("cost_basis")
    position_pct = watch_item.get("position_pct", 0)

    gain_loss_pct = pct_change(price, cost_basis) if cost_basis else None

    # Trend rules
    if sma_50 and price > sma_50:
        score += 2
        triggered.append(f"Price is above 50-day moving average: ${price:.2f} > ${sma_50:.2f}")

    if sma_50 and price < sma_50:
        score -= 2
        triggered.append(f"Price is below 50-day moving average: ${price:.2f} < ${sma_50:.2f}")

    if sma_200 and price > sma_200:
        score += 2
        triggered.append(f"Price is above 200-day moving average: ${price:.2f} > ${sma_200:.2f}")

    if sma_200 and price < sma_200:
        score -= 5
        triggered.append(f"Sell review: price is below 200-day moving average: ${price:.2f} < ${sma_200:.2f}")

    # RSI rules
    if rsi >= technical["rsi_overbought"]:
        score -= 2
        triggered.append(f"RSI is overbought at {rsi:.1f}")

    if rsi <= technical["rsi_oversold"]:
        score += 2
        triggered.append(f"RSI is oversold at {rsi:.1f}")

    # Position risk
    max_position_pct = risk.get("max_position_pct", 15)
    if position_pct > max_position_pct:
        score -= 3
        triggered.append(
            f"Position size is above max allocation: {position_pct}% > {max_position_pct}%"
        )

    # Stop-loss / take-profit
    if gain_loss_pct is not None:
        if gain_loss_pct <= risk["stop_loss_pct"]:
            score -= 6
            triggered.append(
                f"Urgent review: position is below stop-loss threshold: {gain_loss_pct:.1f}%"
            )

        if gain_loss_pct >= risk["take_profit_pct"]:
            score -= 1
            triggered.append(
                f"Take-profit review: position gain is {gain_loss_pct:.1f}%"
            )

    # Fundamental hints
    revenue_growth = stock_data.get("revenue_growth")
    earnings_growth = stock_data.get("earnings_growth")
    forward_pe = stock_data.get("forward_pe")

    if revenue_growth is not None:
        if revenue_growth > 0.15:
            score += 2
            triggered.append(f"Revenue growth is strong: {revenue_growth * 100:.1f}%")
        elif revenue_growth < 0:
            score -= 2
            triggered.append(f"Revenue growth is negative: {revenue_growth * 100:.1f}%")

    if earnings_growth is not None:
        if earnings_growth > 0.10:
            score += 1
            triggered.append(f"Earnings growth is positive: {earnings_growth * 100:.1f}%")
        elif earnings_growth < 0:
            score -= 2
            triggered.append(f"Earnings growth is negative: {earnings_growth * 100:.1f}%")

    if forward_pe is not None and forward_pe > 60:
        score -= 1
        warnings.append(f"Forward P/E is high: {forward_pe:.1f}")

    # Recommendation label
    scoring = rules["scoring"]

    if score <= scoring["urgent_review_threshold"]:
        signal = "URGENT REVIEW"
    elif score <= scoring["sell_review_threshold"]:
        signal = "SELL REVIEW"
    elif score >= scoring["buy_review_threshold"]:
        signal = "BUY REVIEW"
    else:
        signal = "HOLD / WATCH"

    alert_score = abs(score)

    return {
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "alert_score": alert_score,
        "triggered_rules": triggered,
        "warnings": warnings,
        "gain_loss_pct": gain_loss_pct,
    }


# ----------------------------
# OpenAI research summary
# ----------------------------

def generate_research_summary(stock_data, rule_result, watch_item, config):
    if not client:
        return "OpenAI summary skipped because OPENAI_API_KEY is not set."

    model = config["agent"].get("model", "gpt-4.1-mini")

    prompt = {
        "role": "user",
        "content": f"""
You are a stock research alert assistant.

Important:
- Do not provide personalized financial advice.
- Do not claim certainty.
- Do not tell the user they must buy or sell.
- Use "buy review", "sell review", "hold/watch", or "urgent review".
- Base your analysis only on the supplied data.
- Be concise and practical.

Watch item:
{json.dumps(watch_item, indent=2)}

Stock data:
{json.dumps(stock_data, indent=2, default=str)}

Rule result:
{json.dumps(rule_result, indent=2, default=str)}

Return:
1. One-sentence summary
2. Signal explanation
3. Bull case
4. Bear case
5. What changed / what to check next
6. A final "review action" phrased as a question, not an instruction
"""
    }

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a cautious investment research assistant for alerting only, not a financial advisor."
                },
                prompt
            ],
            temperature=0.2,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"OpenAI summary failed: {e}"


def generate_portfolio_summary(results, config):
    if not client:
        return "OpenAI portfolio summary skipped because OPENAI_API_KEY is not set."

    model = config["agent"].get("model", "gpt-4.1-mini")

    summary_items = []
    for result in results:
        if result["status"] != "ok":
            summary_items.append({
                "ticker": result["ticker"],
                "status": "error",
                "error": result.get("error"),
            })
            continue

        stock_data = result["stock_data"]
        rule_result = result["rule_result"]
        threshold_result = result.get("threshold_result", {})

        summary_items.append({
            "ticker": result["ticker"],
            "name": result.get("watch_item", {}).get("name"),
            "strategy": result.get("watch_item", {}).get("strategy"),
            "position_pct": result.get("watch_item", {}).get("position_pct"),
            "cost_basis": result.get("watch_item", {}).get("cost_basis"),
            "current_price": stock_data.get("current_price"),
            "daily_change_pct": stock_data.get("daily_change_pct"),
            "rsi": stock_data.get("rsi"),
            "sma_50": stock_data.get("sma_50"),
            "sma_200": stock_data.get("sma_200"),
            "forward_pe": stock_data.get("forward_pe"),
            "revenue_growth": stock_data.get("revenue_growth"),
            "earnings_growth": stock_data.get("earnings_growth"),
            "analyst_recommendation": stock_data.get("analyst_recommendation"),
            "target_mean_price": stock_data.get("target_mean_price"),
            "signal": rule_result.get("signal"),
            "score": rule_result.get("score"),
            "gain_loss_pct": rule_result.get("gain_loss_pct"),
            "triggered_rules": rule_result.get("triggered_rules", [])[:5],
            "warnings": rule_result.get("warnings", [])[:3],
            "threshold_breached": threshold_result.get("breached"),
            "threshold_breaches": threshold_result.get("breaches", [])[:3],
            "news": [
                item.get("title")
                for item in stock_data.get("news", [])[:3]
                if item.get("title")
            ],
        })

    prompt = {
        "role": "user",
        "content": f"""
You are a cautious stock research assistant summarizing a watchlist alert run.

Important:
- Do not provide personalized financial advice.
- Do not claim certainty.
- Do not tell the user they must buy or sell.
- Base your analysis only on the supplied data.
- Be concise enough for a Discord message.
- Focus on what deserves review, what changed, risks, and what to check next.

Watchlist run data:
{json.dumps(summary_items, indent=2, default=str)}

Return:
1. Overall readout in 2-3 bullets
2. Highest-priority reviews, if any
3. One concise note per ticker
4. What to check next
"""
    }

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a cautious investment research assistant for alerting only, not a financial advisor.",
                },
                prompt,
            ],
            temperature=0.2,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"OpenAI portfolio summary failed: {e}"


# ----------------------------
# Discord alerting
# ----------------------------

def chunk_text(text, max_len=1800):
    chunks = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


def send_discord_message(content):
    if not DISCORD_WEBHOOK_URL:
        raise ValueError("Missing DISCORD_WEBHOOK_URL in .env")

    chunks = chunk_text(content)

    for chunk in chunks:
        payload = {"content": chunk}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=20)

        if response.status_code not in (200, 204):
            raise RuntimeError(
                f"Discord webhook failed: {response.status_code} {response.text}"
            )

        time.sleep(0.4)


def format_stock_alert(stock_data, rule_result, research_summary, threshold_result=None):
    ticker = stock_data["ticker"]
    price = stock_data["current_price"]
    daily = stock_data["daily_change_pct"]

    daily_text = f"{daily:.2f}%" if daily is not None else "N/A"

    triggered = rule_result["triggered_rules"]
    warnings = rule_result["warnings"]

    triggered_text = "\n".join([f"- {x}" for x in triggered]) if triggered else "- No major rules triggered"
    warnings_text = "\n".join([f"- {x}" for x in warnings]) if warnings else "- None"

    threshold_text = "- No per-stock thresholds configured"
    if threshold_result and threshold_result["configured"]:
        if threshold_result["breaches"]:
            threshold_text = "\n".join(
                [f"- {breach['message']}" for breach in threshold_result["breaches"]]
            )
        else:
            threshold_text = "- Thresholds configured, but none breached"

    news_text = ""
    for item in stock_data.get("news", [])[:3]:
        title = item.get("title", "No title")
        link = item.get("link", "")
        news_text += f"- {title}\n  {link}\n"

    if not news_text:
        news_text = "- No recent news found from data source"

    return f"""
**{ticker} Alert — {rule_result['signal']}**

Price: `${price:.2f}`
Price Data: `{stock_data.get('price_provider', 'unknown')}`
Daily Change: `{daily_text}`
Score: `{rule_result['score']}`

**Triggered Rules**
{triggered_text}

**Alert Thresholds**
{threshold_text}

**Warnings**
{warnings_text}

**Recent News**
{news_text}

**Research Summary**
{research_summary}

_Not financial advice. Review before making any decision._
""".strip()


def to_json_safe(value):
    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [to_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [to_json_safe(item) for item in value]

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        value = float(value)

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()

    return value


def find_watch_item(config, ticker: str):
    ticker_upper = ticker.upper()

    for watch_item in config.get("watchlist", []):
        if watch_item.get("ticker", "").upper() == ticker_upper:
            return watch_item

    return {
        "ticker": ticker_upper,
        "name": ticker_upper,
        "position_pct": 0,
        "cost_basis": None,
        "strategy": "watch_only",
    }


def add_threshold_breach(breaches, key, label, current, threshold, direction):
    if current is None or threshold is None:
        return

    if direction == "below" and current < threshold:
        breaches.append({
            "key": key,
            "label": label,
            "direction": direction,
            "current": current,
            "threshold": threshold,
            "message": f"{label} is below threshold: {current:.2f} < {threshold:.2f}",
        })

    if direction == "above" and current > threshold:
        breaches.append({
            "key": key,
            "label": label,
            "direction": direction,
            "current": current,
            "threshold": threshold,
            "message": f"{label} is above threshold: {current:.2f} > {threshold:.2f}",
        })


def evaluate_alert_thresholds(stock_data, rule_result, watch_item):
    thresholds = watch_item.get("alert_thresholds") or {}
    breaches = []

    if not thresholds:
        return {
            "configured": False,
            "breached": False,
            "breaches": breaches,
        }

    add_threshold_breach(
        breaches,
        "price_below",
        "Current price",
        stock_data.get("current_price"),
        thresholds.get("price_below"),
        "below",
    )
    add_threshold_breach(
        breaches,
        "price_above",
        "Current price",
        stock_data.get("current_price"),
        thresholds.get("price_above"),
        "above",
    )
    add_threshold_breach(
        breaches,
        "daily_change_below_pct",
        "Daily change %",
        stock_data.get("daily_change_pct"),
        thresholds.get("daily_change_below_pct"),
        "below",
    )
    add_threshold_breach(
        breaches,
        "daily_change_above_pct",
        "Daily change %",
        stock_data.get("daily_change_pct"),
        thresholds.get("daily_change_above_pct"),
        "above",
    )
    add_threshold_breach(
        breaches,
        "rsi_below",
        "RSI",
        stock_data.get("rsi"),
        thresholds.get("rsi_below"),
        "below",
    )
    add_threshold_breach(
        breaches,
        "rsi_above",
        "RSI",
        stock_data.get("rsi"),
        thresholds.get("rsi_above"),
        "above",
    )
    add_threshold_breach(
        breaches,
        "gain_loss_below_pct",
        "Gain/loss %",
        rule_result.get("gain_loss_pct"),
        thresholds.get("gain_loss_below_pct"),
        "below",
    )
    add_threshold_breach(
        breaches,
        "gain_loss_above_pct",
        "Gain/loss %",
        rule_result.get("gain_loss_pct"),
        thresholds.get("gain_loss_above_pct"),
        "above",
    )
    add_threshold_breach(
        breaches,
        "score_below",
        "Rule score",
        rule_result.get("score"),
        thresholds.get("score_below"),
        "below",
    )
    add_threshold_breach(
        breaches,
        "score_above",
        "Rule score",
        rule_result.get("score"),
        thresholds.get("score_above"),
        "above",
    )

    return {
        "configured": True,
        "breached": bool(breaches),
        "breaches": breaches,
    }


def should_send_stock_alert(config, rule_result, threshold_result=None):
    if threshold_result and threshold_result["configured"]:
        return threshold_result["breached"]

    alerts = config.get("alerts", {})
    send_only_if_triggered = alerts.get("send_only_if_triggered", False)
    min_alert_score = alerts.get("min_alert_score", 5)

    return (
        not send_only_if_triggered
        or rule_result["alert_score"] >= min_alert_score
        or rule_result["signal"] in ["BUY REVIEW", "SELL REVIEW", "URGENT REVIEW"]
    )


def analyze_stock(
    ticker: str,
    config=None,
    watch_item=None,
    include_summary: bool = True,
    send_discord: bool = False,
):
    config = config or load_config()
    configure_yfinance(config)
    watch_item = watch_item or find_watch_item(config, ticker)
    ticker = watch_item.get("ticker", ticker).upper()

    stock_data = fetch_stock_data(ticker, config)
    rule_result = evaluate_rules(stock_data, watch_item, config)
    threshold_result = evaluate_alert_thresholds(stock_data, rule_result, watch_item)

    if include_summary:
        research_summary = generate_research_summary(
            stock_data=stock_data,
            rule_result=rule_result,
            watch_item=watch_item,
            config=config,
        )
    else:
        research_summary = "OpenAI summary skipped by request."

    message = format_stock_alert(
        stock_data,
        rule_result,
        research_summary,
        threshold_result,
    )

    should_alert = should_send_stock_alert(config, rule_result, threshold_result)
    discord_sent = False

    if send_discord and should_alert:
        send_discord_message(message)
        discord_sent = True

    return to_json_safe({
        "ticker": ticker,
        "status": "ok",
        "watch_item": watch_item,
        "stock_data": stock_data,
        "rule_result": rule_result,
        "threshold_result": threshold_result,
        "research_summary": research_summary,
        "discord_message": message,
        "should_alert": should_alert,
        "discord_sent": discord_sent,
    })


def run_agent(
    config=None,
    include_summary: bool = True,
    send_discord: bool | None = None,
    send_summary: bool | None = None,
    send_daily_summary: bool | None = None,
):
    config = config or load_config()
    configure_yfinance(config)

    now = get_agent_now(config).strftime("%Y-%m-%d %H:%M:%S %Z")
    agent_name = config["agent"].get("name", "Stock Alert Agent")
    alerts = config.get("alerts", {})

    send_per_stock_review = alerts.get("send_per_stock_review", True)
    if send_discord is None:
        send_discord = send_per_stock_review

    if send_summary is None:
        send_summary = send_daily_summary

    if send_summary is None:
        send_summary = alerts.get(
            "send_summary",
            alerts.get("send_daily_summary", True),
        )

    results = []

    for watch_item in config.get("watchlist", []):
        ticker = watch_item["ticker"]

        try:
            result = analyze_stock(
                ticker=ticker,
                config=config,
                watch_item=watch_item,
                include_summary=include_summary,
                send_discord=send_discord,
            )
            results.append(result)

        except Exception as e:
            error_result = {
                "ticker": ticker,
                "status": "error",
                "error": str(e),
                "discord_sent": False,
            }

            if send_discord:
                error_msg = f"**{agent_name} error for {ticker}**\n`{str(e)}`"
                send_discord_message(error_msg)
                error_result["discord_sent"] = True

            results.append(error_result)

        time.sleep(1)

    summary = {
        "agent_name": agent_name,
        "run_time": now,
        "count": len(results),
        "ok_count": len([result for result in results if result["status"] == "ok"]),
        "error_count": len([result for result in results if result["status"] == "error"]),
    }

    summary_sent = False
    portfolio_summary = None
    if send_discord and send_summary:
        if include_summary:
            portfolio_summary = generate_portfolio_summary(results, config)

        summary_lines = [
            f"**{agent_name} Summary**",
            f"Run time: `{now}`",
            "",
        ]

        for result in results:
            if result["status"] == "ok":
                rule_result = result["rule_result"]
                summary_lines.append(
                    f"- `{result['ticker']}`: **{rule_result['signal']}**, "
                    f"score `{rule_result['score']}`"
                )
            else:
                summary_lines.append(f"- `{result['ticker']}`: **ERROR**")

        summary_lines.append("")
        if portfolio_summary:
            summary_lines.extend([
                "**OpenAI Research Summary**",
                portfolio_summary,
                "",
            ])

        summary_lines.append("_Not financial advice. Alerts are for research review only._")

        send_discord_message("\n".join(summary_lines))
        summary_sent = True

    return to_json_safe({
        "status": "ok" if summary["error_count"] == 0 else "partial",
        "summary": summary,
        "portfolio_summary": portfolio_summary,
        "summary_sent": summary_sent,
        "daily_summary_sent": summary_sent,
        "results": results,
    })


# ----------------------------
# Main runner
# ----------------------------

if __name__ == "__main__":
    run_agent()
