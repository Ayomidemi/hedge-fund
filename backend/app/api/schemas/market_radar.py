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


class MarketRadarIndustryResponse(BaseModel):
    name: str
    jurisdiction: str
    name_count: int
    flagged_count: int
    heat: str
    names: list[MarketRadarNameResponse]


class MarketRadarOverviewResponse(BaseModel):
    generated_at: datetime
    sessions: list[MarketRadarSessionResponse]
    latest_run: MarketRadarRunResponse | None = None
    working_set_count: int
    flagged_count: int
    industries: list[MarketRadarIndustryResponse]
    working_set: list[MarketRadarNameResponse]
    flagged: list[MarketRadarNameResponse]
