from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

NewsJurisdiction = Literal["US", "NG", "all"]


class NewsItemResponse(BaseModel):
    id: UUID
    provider: str
    provider_id: str
    source_name: str | None = None
    title: str
    summary: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    crawled_at: datetime | None = None
    jurisdiction: str | None = None
    event_type: str | None = None
    sentiment_label: str | None = None
    sentiment_score: Decimal | None = None
    tickers: list[str] = Field(default_factory=list)


class NewsPollRunResponse(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    trigger: str
    target_scope: str | None = None
    target_key: str | None = None
    provider_calls: int
    items_seen: int
    items_created: int
    items_updated: int
    interval_seconds: int
    cache_hit: bool = False
    provider_plan: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NewsOverviewResponse(BaseModel):
    generated_at: datetime
    latest_run: NewsPollRunResponse | None = None
    current: list[NewsItemResponse]
    ticker: str | None = None
    ticker_items: list[NewsItemResponse] = Field(default_factory=list)
    watchlist_items: list[NewsItemResponse] = Field(default_factory=list)
    provider_notes: list[str] = Field(default_factory=list)


class NewsPollRequest(BaseModel):
    jurisdiction: NewsJurisdiction = "US"
    force: bool = False


class NewsTickerRefreshRequest(BaseModel):
    market: Literal["US", "NG"] | None = None
    force: bool = False
