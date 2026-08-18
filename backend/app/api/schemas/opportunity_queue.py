from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.api.schemas.operating_core import InstrumentCreate, InstrumentResponse

OpportunityStatus = Literal[
    "discovered",
    "screening",
    "research",
    "watchlist",
    "candidate",
    "approved",
    "active_position",
    "exited",
    "post_mortem",
    "rejected",
]
OpportunityPriority = Literal["low", "medium", "high", "urgent"]


class OpportunityCreate(BaseModel):
    source_memo_id: UUID | None = None
    instrument: InstrumentCreate | None = None
    status: OpportunityStatus = "discovered"
    priority: OpportunityPriority = "medium"
    thesis: str | None = None
    research_question: str | None = None
    next_action: str | None = None
    time_horizon: str | None = Field(default=None, max_length=64)
    conviction_score: Decimal | None = Field(default=None, ge=0, le=100)
    expected_edge_pct: Decimal | None = None
    target_weight: Decimal | None = Field(default=None, ge=0, le=100)
    review_by: date | None = None
    notes: str | None = None

    @field_validator("thesis", "research_question", "next_action", "notes")
    @classmethod
    def empty_text_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OpportunityUpdate(BaseModel):
    status: OpportunityStatus | None = None
    priority: OpportunityPriority | None = None
    thesis: str | None = None
    research_question: str | None = None
    next_action: str | None = None
    time_horizon: str | None = Field(default=None, max_length=64)
    conviction_score: Decimal | None = Field(default=None, ge=0, le=100)
    expected_edge_pct: Decimal | None = None
    target_weight: Decimal | None = Field(default=None, ge=0, le=100)
    review_by: date | None = None
    notes: str | None = None
    override_reason: str | None = None

    @field_validator(
        "thesis", "research_question", "next_action", "notes", "override_reason"
    )
    @classmethod
    def empty_text_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OpportunityMemoLink(BaseModel):
    id: UUID
    memo_date: date
    classification: str
    executive_view: str


class OpportunityRadarLink(BaseModel):
    ticker: str
    price: Decimal | None = None
    change_pct: Decimal | None = None
    flags: list[str] = Field(default_factory=list)
    scan_state: str | None = None
    scan_delta_change_pct: str | None = None
    as_of: datetime
    carried_forward: bool = False


class OpportunityRiskLink(BaseModel):
    id: UUID
    decision: str
    risk_level: str
    checked_at: datetime


class OpportunityPositionLink(BaseModel):
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


class OpportunityTradeLink(BaseModel):
    id: UUID
    side: str
    quantity: Decimal
    executed_price: Decimal | None = None
    trade_date: datetime
    status: str


class OpportunityLinks(BaseModel):
    memo: OpportunityMemoLink | None = None
    radar: OpportunityRadarLink | None = None
    pre_trade: OpportunityRiskLink | None = None
    position: OpportunityPositionLink | None = None
    last_trade: OpportunityTradeLink | None = None
    tape: list[dict] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class OpportunityResponse(BaseModel):
    id: UUID
    instrument: InstrumentResponse
    source_memo_id: UUID | None
    source_recommendation_id: UUID | None
    discovered_at: datetime
    status: str
    priority: str
    thesis: str
    research_question: str | None
    next_action: str | None
    time_horizon: str | None
    conviction_score: Decimal | None
    expected_edge_pct: Decimal | None
    target_weight: Decimal | None
    review_by: date | None
    closed_at: datetime | None
    notes: str | None
    status_history: list[dict]
    latest_action: str | None = None
    latest_composite_score: Decimal | None = None
    latest_confidence_score: Decimal | None = None
    links: OpportunityLinks = Field(default_factory=OpportunityLinks)
    created_at: datetime
    updated_at: datetime


class OpportunityCandidateResponse(BaseModel):
    memo_id: UUID
    recommendation_id: UUID | None
    ticker: str
    name: str
    asset_class: str
    memo_date: date
    classification: str
    executive_view: str
    action: str | None
    composite_score: Decimal | None
    confidence_score: Decimal | None


class OpportunityQueueSummaryResponse(BaseModel):
    total: int
    active: int
    high_priority: int
    approved: int
    candidates: int
    next_review_by: date | None
    status_counts: dict[str, int]


class OpportunityQueueResponse(BaseModel):
    generated_at: datetime
    summary: OpportunityQueueSummaryResponse
    opportunities: list[OpportunityResponse]
    candidates: list[OpportunityCandidateResponse]
    status_order: list[str]
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 1
