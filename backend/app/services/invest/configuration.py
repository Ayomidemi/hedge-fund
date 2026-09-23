from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InvestSetting

DEFAULT_INVEST_SETTINGS: dict[str, Any] = {
    "home_quick_actions": [
        {
            "title": "Compare bills and bonds",
            "detail": "T-bills, Treasury notes, FGN bonds, and cash-yield products.",
            "href": "/invest/markets",
        },
        {
            "title": "Fund paper cash",
            "detail": "Top up or reset the simulated Invest brokerage account.",
            "href": "/invest/cash",
        },
        {
            "title": "Check unusual tape",
            "detail": "Retail-safe market context without Capital workflow language.",
            "href": "/invest/discover",
        },
        {
            "title": "Review portfolio",
            "detail": "Positions, paper fills, and cash.",
            "href": "/invest/portfolio",
        },
    ],
    "search_defaults": {
        "default_query": "T-BILL",
        "default_market": "US",
        "markets": [
            {"code": "US", "label": "US"},
            {"code": "NG", "label": "NGX"},
        ],
    },
    "risk_policy": {
        "supported_asset_classes": ["equity", "etf", "bond", "cash_equivalent"],
        "allowed_sides": ["BUY", "SELL"],
        "allowed_order_types": ["market"],
        "buying_power_concentration_warn_pct": "0.50",
        "fixed_income_fx_warning_enabled": True,
    },
    "paper_broker_policy": {
        "allowed_order_types": ["market"],
        "allowed_sides": ["BUY", "SELL"],
        "concentration_warn_pct": "0.25",
        "instant_fills": True,
        "quantity_precision": "0.00000001",
        "price_precision": "0.000001",
        "money_precision": "0.01",
    },
    "news_policy": {
        "headlines_page_size": 10,
        "section_page_size": 8,
        "ticker_page_size": 8,
        "saved_page_size": 8,
        "income_pool": 80,
        "income_refresh_min_items": 5,
        "income_refresh_timeout_seconds": 6.0,
        "refresh_ms": 60000,
        "income_keywords": {
            "US": [
                "treasury",
                "treasuries",
                "t-bill",
                "t bill",
                "tbill",
                "t-note",
                "t-bond",
                "yield curve",
                "bond yield",
                "treasury yield",
                "fed funds",
                "rate cut",
                "rate hike",
                "duration risk",
                "money market",
                "fomc",
            ],
            "NG": [
                "fgn",
                "cbn",
                "naira",
                "dmo",
                "fmdq",
                "nigerian treasury",
                "nigeria treasury",
                "ntb",
                "treasury bill",
                "bond auction",
                "open market operation",
            ],
        },
    },
    "discover_policy": {
        "unusual_limit": 10,
        "sector_limit": 6,
        "board_limit": 6,
        "include_news_section": False,
        "include_watchlist_section": False,
        "next_actions_when_empty_watchlist": [
            {
                "title": "Compare the fixed-income shelf",
                "subtitle": "Bills and bonds stay first on Markets.",
                "badge": "Markets",
                "href": "/invest/markets",
                "tone": "income",
                "metadata": [],
            },
            {
                "title": "Scan listed board movers",
                "subtitle": "ETF proxies and NGX pulses sit beside fixed income.",
                "badge": "Board",
                "href": "/invest/markets",
                "tone": "neutral",
                "metadata": [],
            },
        ],
    },
    "profile_policy": {
        "permissions": [
            {
                "code": "paper_trading",
                "label": "Paper trading",
                "enabled": True,
                "description": "Simulated Invest orders.",
            },
            {
                "code": "fixed_income",
                "label": "Fixed income",
                "enabled": True,
                "description": "Bills, notes, bonds, and cash-yield products.",
            },
            {
                "code": "real_cash_movements",
                "label": "Real cash movement",
                "enabled": False,
                "description": "Live funding is off.",
            },
            {
                "code": "capital_workspace",
                "label": "Pease Capital workspace",
                "enabled": False,
                "description": "Fund books and PM workflow.",
            },
            {
                "code": "product_switching",
                "label": "Product switching",
                "enabled": False,
                "description": "Invest and Capital switcher.",
            },
        ],
        "product_boundary": [
            "Invest cash stays separate.",
            "Paper orders stay in Invest.",
            "Capital signals stay in Capital.",
            "Broker routing is isolated.",
        ],
        "notification_settings": [
            "Order fills",
            "Cash events",
            "Account events",
            "Market alerts planned",
        ],
        "withheld_capital_signals": [
            "Capital target weights",
            "Expected alpha and model rank",
            "Strategy pod assignment",
            "PM approval state",
            "Portfolio hedge recommendation",
            "Fund-level risk budget",
        ],
    },
}


def default_invest_setting(key: str) -> Any:
    return deepcopy(DEFAULT_INVEST_SETTINGS.get(key))


async def ensure_invest_settings(
    session: AsyncSession, keys: list[str] | None = None
) -> None:
    wanted = keys or list(DEFAULT_INVEST_SETTINGS)
    existing = set(
        await session.scalars(
            select(InvestSetting.key).where(InvestSetting.key.in_(wanted))
        )
    )
    for key in wanted:
        if key in existing:
            continue
        session.add(
            InvestSetting(
                key=key,
                payload=default_invest_setting(key),
                is_active=True,
            )
        )
    await session.flush()


async def get_invest_setting(session: AsyncSession, key: str) -> Any:
    fallback = default_invest_setting(key)
    await ensure_invest_settings(session, [key])
    record = await session.scalar(
        select(InvestSetting)
        .where(InvestSetting.key == key)
        .where(InvestSetting.is_active.is_(True))
    )
    if record is None:
        return fallback
    return _merge_default(fallback, record.payload)


async def get_home_quick_actions(session: AsyncSession) -> list[dict[str, str]]:
    payload = await get_invest_setting(session, "home_quick_actions")
    return [item for item in payload if isinstance(item, dict)]


async def get_search_defaults(session: AsyncSession) -> dict[str, Any]:
    return await get_invest_setting(session, "search_defaults")


async def get_risk_policy(session: AsyncSession) -> dict[str, Any]:
    return await get_invest_setting(session, "risk_policy")


async def get_paper_broker_policy(session: AsyncSession) -> dict[str, Any]:
    return await get_invest_setting(session, "paper_broker_policy")


async def get_news_policy(session: AsyncSession) -> dict[str, Any]:
    return await get_invest_setting(session, "news_policy")


async def get_discover_policy(session: AsyncSession) -> dict[str, Any]:
    return await get_invest_setting(session, "discover_policy")


async def get_profile_policy(session: AsyncSession) -> dict[str, Any]:
    return await get_invest_setting(session, "profile_policy")


async def get_invest_ui_config(session: AsyncSession) -> dict[str, Any]:
    search = await get_search_defaults(session)
    news = await get_news_policy(session)
    return {
        "search": search,
        "news": {
            "headlines_page_size": int(news.get("headlines_page_size", 10)),
            "section_page_size": int(news.get("section_page_size", 8)),
            "ticker_page_size": int(news.get("ticker_page_size", 8)),
            "refresh_ms": int(news.get("refresh_ms", 60000)),
        },
    }


def _merge_default(fallback: Any, override: Any) -> Any:
    if isinstance(fallback, dict) and isinstance(override, dict):
        merged = deepcopy(fallback)
        for key, value in override.items():
            merged[key] = _merge_default(merged.get(key), value)
        return merged
    if override is None:
        return deepcopy(fallback)
    return deepcopy(override)
