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

    @field_validator("thesis", "research_question", "next_action", "notes")
    @classmethod
    def empty_text_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


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
