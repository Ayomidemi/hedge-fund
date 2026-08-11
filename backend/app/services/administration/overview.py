import logging
from datetime import datetime, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.administration import (
    AdministrationDataVersionResponse,
    AdministrationModelVersionResponse,
    AdministrationOverviewResponse,
    AdministrationPortfolioRuleResponse,
    AdministrationRiskPolicyResponse,
    FxRateResponse,
    PriceRefreshRunResponse,
    SystemLogEntryResponse,
)
from app.core.auth import AuthenticatedUser
from app.models import (
    FxRate,
    MarketPriceBar,
    ModelVersion,
    PriceRefreshRun,
    RiskLimit,
    RiskPolicyVersion,
    SystemLogEntry,
    TickerFeatureSnapshot,
)
from app.services.administration.system_log import list_system_logs
from app.services.portfolio.operating_core import get_or_create_default_portfolio

logger = logging.getLogger(__name__)


async def build_administration_overview(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    log_limit: int = 100,
    log_category: str | None = None,
) -> AdministrationOverviewResponse:
    portfolio = await get_or_create_default_portfolio(session, user)
    logs = await list_system_logs(
        session,
        user,
        limit=log_limit,
        category=log_category,
    )
    model_versions = list(
        await session.scalars(
            select(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(20)
        )
    )
    risk_policies = list(
        await session.scalars(
            select(RiskPolicyVersion).order_by(RiskPolicyVersion.effective_at.desc()).limit(10)
        )
    )
    risk_limits = list(
        await session.scalars(
            select(RiskLimit)
            .where(RiskLimit.portfolio_id == portfolio.id)
            .order_by(RiskLimit.name.asc())
        )
    )

    price_stats = await session.execute(
        select(
            func.count(MarketPriceBar.id),
            func.count(distinct(MarketPriceBar.instrument_id)),
            func.max(MarketPriceBar.bar_date),
        )
    )
    price_count, price_instruments, latest_price_date = price_stats.one()

    feature_stats = await session.execute(
        select(
            func.count(TickerFeatureSnapshot.id),
            func.count(distinct(TickerFeatureSnapshot.instrument_id)),
            func.max(TickerFeatureSnapshot.as_of_date),
        )
    )
    feature_count, feature_instruments, latest_feature_date = feature_stats.one()

    refresh_runs = list(
        await session.scalars(
            select(PriceRefreshRun)
            .order_by(PriceRefreshRun.started_at.desc())
            .limit(10)
        )
    )
    latest_fx = await session.scalar(
        select(FxRate)
        .where(FxRate.base_currency == "USD", FxRate.quote_currency == "NGN")
        .where(FxRate.is_stale.is_(False))
    )

    logger.info(
        "administration_overview_loaded",
        extra={
            "owner_user_id": user.id,
            "log_count": len(logs),
            "model_count": len(model_versions),
        },
    )

    return AdministrationOverviewResponse(
        generated_at=datetime.now(timezone.utc),
        portfolio_name=portfolio.name,
        system_logs=[_log_response(entry) for entry in logs],
        model_versions=[_model_version_response(item) for item in model_versions],
        data_versions=[
            AdministrationDataVersionResponse(
                key="market_prices",
                label="Market price bars",
                record_count=int(price_count or 0),
                instrument_count=int(price_instruments or 0),
                latest_as_of_date=latest_price_date,
            ),
            AdministrationDataVersionResponse(
                key="feature_snapshots",
                label="Feature snapshots",
                record_count=int(feature_count or 0),
                instrument_count=int(feature_instruments or 0),
                latest_as_of_date=latest_feature_date,
            ),
        ],
        portfolio_rules=[
            AdministrationPortfolioRuleResponse(
                name=limit.name,
                limit_type=limit.limit_type,
                threshold_value=limit.threshold_value,
                unit=limit.unit,
                scope=limit.scope,
            )
            for limit in risk_limits
        ],
        risk_policies=[_risk_policy_response(item) for item in risk_policies],
        price_refresh_runs=[
            PriceRefreshRunResponse.model_validate(run) for run in refresh_runs
        ],
        latest_fx_rate=FxRateResponse.model_validate(latest_fx) if latest_fx else None,
    )


def _log_response(entry: SystemLogEntry) -> SystemLogEntryResponse:
    return SystemLogEntryResponse(
        id=entry.id,
        level=entry.level,
        category=entry.category,
        event=entry.event,
        message=entry.message,
        context=entry.context or {},
        created_at=entry.created_at,
    )


def _model_version_response(model: ModelVersion) -> AdministrationModelVersionResponse:
    metrics = model.metrics or {}
    return AdministrationModelVersionResponse(
        id=model.id,
        name=model.name,
        version=model.version,
        pod=model.pod,
        purpose=model.purpose,
        approved_use=model.approved_use,
        shutdown_criteria=model.shutdown_criteria,
        validation_status=str(metrics.get("validation_status") or metrics.get("status") or "unknown"),
        created_at=model.created_at,
    )


def _risk_policy_response(policy: RiskPolicyVersion) -> AdministrationRiskPolicyResponse:
    return AdministrationRiskPolicyResponse(
        id=policy.id,
        name=policy.name,
        version=policy.version,
        status=policy.status,
        effective_at=policy.effective_at,
        limit_count=len(policy.limits or {}),
        notes=policy.notes,
    )
