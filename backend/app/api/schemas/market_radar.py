from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

RadarJurisdiction = Literal["US", "NG", "all"]


class MarketRadarScanRequest(BaseModel):
    jurisdictions: list[Literal["US", "NG"]] | None = None
    force: bool = False


class MarketRadarSessionResponse(BaseModel):
    jurisdiction: str
    is_open: bool
    in_post_close_window: bool
    allows_discovery: bool
    label: str
    vendors: list[str]


class MarketRadarRunResponse(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    triggered_by_user_id: str | None = None
    jurisdictions_requested: list[str]
    jurisdictions_scanned: list[str]
    jurisdictions_skipped: list[dict[str, Any]]
    vendor_calls: int
    cache_hits: int
    catalog_count: int
    working_set_count: int
    flagged_count: int
    promoted_count: int
    promotion_owner_ids: list[str]
    notes: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class MarketRadarNameResponse(BaseModel):
    ticker: str
    name: str
    jurisdiction: str
    sector: str | None = None
    industry: str | None = None
    asset_class: str
    currency: str
    source: str
    always_watched: bool
    price: Decimal | None = None
    change_pct: Decimal | None = None
    volume: int | None = None
    volume_ratio: Decimal | None = None
    anomaly_score: Decimal
    flags: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    sparkline: list[dict[str, Any]] = Field(default_factory=list)
    as_of: datetime
    source_as_of: datetime | None = None
    carried_forward: bool = False
    stale_reason: str | None = None
    on_watchlist: bool = False
    pinned_prior: bool = False


class MarketRadarIndustryResponse(BaseModel):
    name: str
    jurisdiction: str
    name_count: int
    flagged_count: int
    heat: str
    names: list[MarketRadarNameResponse]


class RadarWatchlistCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    notes: str | None = None
    market: Literal["US", "NG"] | None = None


class RadarWatchlistItemResponse(BaseModel):
    ticker: str
    name: str
    jurisdiction: str
    notes: str | None = None
    added_at: datetime
    on_watchlist: bool = True
    price: Decimal | None = None
    change_pct: Decimal | None = None
    volume: int | None = None
    volume_ratio: Decimal | None = None
    anomaly_score: Decimal | None = None
    flags: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    sparkline: list[dict[str, Any]] = Field(default_factory=list)
    as_of: datetime | None = None
    source_as_of: datetime | None = None
    carried_forward: bool = False
    scan_state: str | None = None
    scan_delta_change_pct: Decimal | None = None
    scan_delta_price_pct: Decimal | None = None


class RadarWatchlistClockResponse(BaseModel):
    label: str
    change_pct: Decimal | None = None
    price_return_zscore: Any = None
    volume_zscore: Any = None
    volatility_ratio: Any = None
    scan_state: Any = None
    scan_delta_change_pct: Any = None
    scan_delta_price_pct: Any = None
    scan_minutes_since_prior: Any = None


class RadarWatchlistDetailResponse(RadarWatchlistItemResponse):
    clocks: dict[str, RadarWatchlistClockResponse]


class RadarWatchlistListResponse(BaseModel):
    items: list[RadarWatchlistItemResponse]


class RadarWatchlistChartPoint(BaseModel):
    at: datetime | None = None
    date: str | None = None
    price: Decimal | None = None
    volume: int | None = None
    change_pct: Decimal | None = None
    source: str | None = None


class RadarWatchlistChartResponse(BaseModel):
    ticker: str
    range: str
    source: str
    filled_from_vendor: bool = False
    note: str | None = None
    points: list[RadarWatchlistChartPoint] = Field(default_factory=list)


class MarketRadarOverviewResponse(BaseModel):
    generated_at: datetime
    sessions: list[MarketRadarSessionResponse]
    latest_run: MarketRadarRunResponse | None = None
    working_set_count: int
    flagged_count: int
    industries: list[MarketRadarIndustryResponse]
    working_set: list[MarketRadarNameResponse]
    flagged: list[MarketRadarNameResponse]
    watchlist: list[RadarWatchlistItemResponse] = Field(default_factory=list)
    scan_changes: list[MarketRadarNameResponse] = Field(default_factory=list)
