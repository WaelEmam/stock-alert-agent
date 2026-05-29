import os
import secrets
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from main import (
    analyze_stock,
    configure_yfinance,
    find_watch_item,
    load_config,
    run_agent,
)


app = FastAPI(
    title="Stock Alert Agent API",
    description="FastAPI service for running stock reviews and optional Discord alerts.",
    version="1.2.0",
)


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(x_api_key: str | None = Depends(api_key_header)):
    expected_api_key = os.getenv("STOCK_AGENT_API_KEY")

    if not expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STOCK_AGENT_API_KEY is not configured on the server.",
        )

    if not x_api_key or not secrets.compare_digest(x_api_key, expected_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )

    return True


@app.get("/", include_in_schema=False)
def landing_page():
    return RedirectResponse(url="/docs", status_code=307)


class RunRequest(BaseModel):
    include_summary: bool = Field(
        default=True,
        description="Generate OpenAI research summaries when OPENAI_API_KEY is configured.",
    )
    send_discord: bool = Field(
        default=False,
        description="Send per-stock review messages to Discord from inside the container.",
    )
    send_summary: bool | None = Field(
        default=None,
        description="Send the full-watchlist Discord summary for this run.",
    )
    send_daily_summary: bool | None = Field(
        default=None,
        description="Deprecated alias for send_summary.",
    )


class AnalyzeRequest(BaseModel):
    include_summary: bool = Field(
        default=True,
        description="Generate an OpenAI research summary when OPENAI_API_KEY is configured.",
    )
    send_discord: bool = Field(
        default=False,
        description="Send this ticker review to Discord from inside the container.",
    )
    name: str | None = Field(default=None, description="Optional display name override.")
    position_pct: float | None = Field(
        default=None,
        description="Optional portfolio allocation override.",
    )
    cost_basis: float | None = Field(
        default=None,
        description="Optional average purchase price override.",
    )
    strategy: str | None = Field(default=None, description="Optional strategy label override.")
    watch_item: dict[str, Any] | None = Field(
        default=None,
        description="Optional full watch item override.",
    )


@app.get("/health")
def health():
    try:
        config = load_config()
        config_loaded = True
        watchlist_count = len(config.get("watchlist", []))
    except Exception:
        config_loaded = False
        watchlist_count = 0

    return {
        "status": "ok" if config_loaded else "error",
        "config_loaded": config_loaded,
        "watchlist_count": watchlist_count,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "discord_configured": bool(os.getenv("DISCORD_WEBHOOK_URL")),
        "api_auth_configured": bool(os.getenv("STOCK_AGENT_API_KEY")),
    }


@app.post("/run", dependencies=[Depends(require_api_key)])
def run_reviews(request: RunRequest | None = Body(default=None)):
    request = request or RunRequest()

    try:
        config = load_config()
        return run_agent(
            config=config,
            include_summary=request.include_summary,
            send_discord=request.send_discord,
            send_summary=request.send_summary,
            send_daily_summary=request.send_daily_summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/watchlist", dependencies=[Depends(require_api_key)])
def get_watchlist():
    try:
        config = load_config()
        return {
            "agent": config.get("agent", {}),
            "alerts": config.get("alerts", {}),
            "data": config.get("data", {}),
            "watchlist": config.get("watchlist", []),
            "rules": config.get("rules", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/analyze/{ticker}", dependencies=[Depends(require_api_key)])
def analyze_ticker(ticker: str, request: AnalyzeRequest | None = Body(default=None)):
    request = request or AnalyzeRequest()

    try:
        config = load_config()
        configure_yfinance(config)

        watch_item = request.watch_item or find_watch_item(config, ticker)
        watch_item = dict(watch_item)
        watch_item["ticker"] = ticker.upper()

        if request.name is not None:
            watch_item["name"] = request.name
        if request.position_pct is not None:
            watch_item["position_pct"] = request.position_pct
        if request.cost_basis is not None:
            watch_item["cost_basis"] = request.cost_basis
        if request.strategy is not None:
            watch_item["strategy"] = request.strategy

        return analyze_stock(
            ticker=ticker,
            config=config,
            watch_item=watch_item,
            include_summary=request.include_summary,
            send_discord=request.send_discord,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
