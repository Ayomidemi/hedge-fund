"""Account-scoped risk settings; changes never start trading or reset funds."""
from fastapi import HTTPException
from sqlalchemy import select
from app.core.auth import AuthenticatedUser
from app.db.locks import lock_portfolio
from app.models import RiskLimit
from app.services.risk.policy import PROFILES, apply_account_limits, profile_policy
from app.services.portfolio.operating_core import get_or_create_default_portfolio


async def risk_settings(session, owner, *, update=None, expected=None):
    portfolio = await get_or_create_default_portfolio(session, AuthenticatedUser(id=owner, email=None))
    if update is not None:
        portfolio = await lock_portfolio(session, portfolio)
        if expected != portfolio.risk_profile:
            raise HTTPException(status_code=409, detail="Risk settings changed elsewhere. Reload before saving.")
    limits = list(await session.scalars(select(RiskLimit).where(RiskLimit.portfolio_id == portfolio.id, RiskLimit.is_active.is_(True))))
    options = {name: apply_account_limits(profile_policy(name), limits) for name in PROFILES}
    if update is not None and update != portfolio.risk_profile:
        from app.services.paper_fund.engine import _latest, _orders, _cancel_pending
        from app.services.administration.system_log import record_system_log
        old = portfolio.risk_profile
        portfolio.risk_profile = update
        run = await _latest(session, owner, lock=True)
        if run is not None and run.status != "completed":
            run.policy = options[update]
            _cancel_pending(await _orders(session, run), "Risk profile changed; entry requires a new assessment.")
        await record_system_log(session, owner_user_id=owner, event="capital.risk_profile_changed", level="info", category="risk", message=f"Capital risk profile changed from {old} to {update}.",
                                context={"portfolio_id": str(portfolio.id), "policy": options[update]})
    if update is not None:
        await session.commit()
    return {"profile": portfolio.risk_profile, "options": options,
            "notice": "Account limits apply to every profile. Changes cancel pending entries; existing stops and risk halts remain in force. Higher risk does not imply higher returns."}
