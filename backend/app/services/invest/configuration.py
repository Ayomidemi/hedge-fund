from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InvestSetting

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class InvestRiskPolicy:
    supported_asset_classes: frozenset[str]
    allowed_sides: frozenset[str]
    allowed_order_types: frozenset[str]
    buying_power_concentration_warn_pct: Decimal
    fixed_income_fx_warning_enabled: bool


@dataclass(frozen=True)
class PaperBrokerPolicy:
    allowed_order_types: frozenset[str]
    allowed_sides: frozenset[str]
    concentration_warn_pct: Decimal
    instant_fills: bool
    quantity_precision: Decimal
    price_precision: Decimal
    money_precision: Decimal


def default_invest_setting(key: str) -> Any:
    return deepcopy(DEFAULT_INVEST_SETTINGS.get(key))


async def ensure_invest_settings(
    session: AsyncSession, keys: list[str] | None = None
) -> bool:
    wanted = [
        key
        for key in (keys or list(DEFAULT_INVEST_SETTINGS))
        if key in DEFAULT_INVEST_SETTINGS
    ]
    if not wanted:
        return True
    if not await _invest_settings_table_exists(session):
        return False
    try:
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
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_invest_settings_table(exc):
            raise
        await _rollback_after_settings_fallback(session)
        logger.warning(
            "invest_settings_table_missing",
            extra={"keys": wanted, "error": str(exc)},
        )
        return False
    return True


async def get_invest_setting(session: AsyncSession, key: str) -> Any:
    fallback = default_invest_setting(key)
    if fallback is None:
        return None
    settings_available = await ensure_invest_settings(session, [key])
    if not settings_available:
        return fallback
    try:
        record = await session.scalar(
            select(InvestSetting)
            .where(InvestSetting.key == key)
            .where(InvestSetting.is_active.is_(True))
        )
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_invest_settings_table(exc):
            raise
        await _rollback_after_settings_fallback(session)
        logger.warning(
            "invest_setting_fell_back_to_default",
            extra={"key": key, "error": str(exc)},
        )
        return fallback
    if record is None:
        return fallback
    return _merge_default(fallback, record.payload)


async def get_home_quick_actions(session: AsyncSession) -> list[dict[str, str]]:
    payload = await get_invest_setting(session, "home_quick_actions")
    if not isinstance(payload, list):
        payload = default_invest_setting("home_quick_actions")
    actions: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href") or "")
        if href.rstrip("/") == "/invest/orders":
            item = {**item, "href": "/invest/portfolio"}
        actions.append(item)
    return actions


async def get_search_defaults(session: AsyncSession) -> dict[str, Any]:
    payload = await get_invest_setting(session, "search_defaults")
    return (
        payload
        if isinstance(payload, dict)
        else default_invest_setting("search_defaults")
    )


async def get_risk_policy(session: AsyncSession) -> dict[str, Any]:
    payload = await get_invest_setting(session, "risk_policy")
    return (
        payload if isinstance(payload, dict) else default_invest_setting("risk_policy")
    )


async def get_typed_risk_policy(session: AsyncSession) -> InvestRiskPolicy:
    return parse_risk_policy(await get_risk_policy(session))


async def get_paper_broker_policy(session: AsyncSession) -> dict[str, Any]:
    payload = await get_invest_setting(session, "paper_broker_policy")
    return (
        payload
        if isinstance(payload, dict)
        else default_invest_setting("paper_broker_policy")
    )


async def get_typed_paper_broker_policy(session: AsyncSession) -> PaperBrokerPolicy:
    return parse_paper_broker_policy(await get_paper_broker_policy(session))


async def get_news_policy(session: AsyncSession) -> dict[str, Any]:
    payload = await get_invest_setting(session, "news_policy")
    return (
        payload if isinstance(payload, dict) else default_invest_setting("news_policy")
    )


async def get_discover_policy(session: AsyncSession) -> dict[str, Any]:
    payload = await get_invest_setting(session, "discover_policy")
    policy = (
        payload
        if isinstance(payload, dict)
        else default_invest_setting("discover_policy")
    )
    policy["include_news_section"] = False
    policy["include_watchlist_section"] = False
    return policy


async def get_profile_policy(session: AsyncSession) -> dict[str, Any]:
    payload = await get_invest_setting(session, "profile_policy")
    return (
        payload
        if isinstance(payload, dict)
        else default_invest_setting("profile_policy")
    )


async def get_invest_ui_config(session: AsyncSession) -> dict[str, Any]:
    search = await get_search_defaults(session)
    news = await get_news_policy(session)
    return {
        "search": search,
        "news": {
            "headlines_page_size": _int_setting(
                news, "headlines_page_size", 10, minimum=1, maximum=50
            ),
            "section_page_size": _int_setting(
                news, "section_page_size", 8, minimum=1, maximum=50
            ),
            "ticker_page_size": _int_setting(
                news, "ticker_page_size", 8, minimum=1, maximum=50
            ),
            "refresh_ms": _int_setting(
                news, "refresh_ms", 60000, minimum=5000, maximum=300000
            ),
        },
    }


def parse_risk_policy(payload: dict[str, Any] | None = None) -> InvestRiskPolicy:
    source = _merged_payload("risk_policy", payload)
    fallback = DEFAULT_INVEST_SETTINGS["risk_policy"]
    return InvestRiskPolicy(
        supported_asset_classes=_string_set(
            source.get("supported_asset_classes"),
            fallback["supported_asset_classes"],
            case="lower",
        ),
        allowed_sides=_string_set(
            source.get("allowed_sides"),
            fallback["allowed_sides"],
            case="upper",
        ),
        allowed_order_types=_string_set(
            source.get("allowed_order_types"),
            fallback["allowed_order_types"],
            case="lower",
        ),
        buying_power_concentration_warn_pct=_decimal_setting(
            source,
            "buying_power_concentration_warn_pct",
            Decimal("0.50"),
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        ),
        fixed_income_fx_warning_enabled=_bool_setting(
            source.get("fixed_income_fx_warning_enabled"), True
        ),
    )


def parse_paper_broker_policy(
    payload: dict[str, Any] | None = None,
) -> PaperBrokerPolicy:
    source = _merged_payload("paper_broker_policy", payload)
    fallback = DEFAULT_INVEST_SETTINGS["paper_broker_policy"]
    return PaperBrokerPolicy(
        allowed_order_types=_string_set(
            source.get("allowed_order_types"),
            fallback["allowed_order_types"],
            case="lower",
        ),
        allowed_sides=_string_set(
            source.get("allowed_sides"),
            fallback["allowed_sides"],
            case="upper",
        ),
        concentration_warn_pct=_decimal_setting(
            source,
            "concentration_warn_pct",
            Decimal("0.25"),
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        ),
        instant_fills=_bool_setting(source.get("instant_fills"), True),
        quantity_precision=_decimal_setting(
            source,
            "quantity_precision",
            Decimal("0.00000001"),
            minimum=Decimal("0.00000001"),
        ),
        price_precision=_decimal_setting(
            source,
            "price_precision",
            Decimal("0.000001"),
            minimum=Decimal("0.000001"),
        ),
        money_precision=_decimal_setting(
            source,
            "money_precision",
            Decimal("0.01"),
            minimum=Decimal("0.01"),
        ),
    )


def _merge_default(fallback: Any, override: Any) -> Any:
    if isinstance(fallback, dict) and isinstance(override, dict):
        merged = deepcopy(fallback)
        for key, value in override.items():
            merged[key] = _merge_default(merged.get(key), value)
        return merged
    if override is None:
        return deepcopy(fallback)
    return deepcopy(override)


def _merged_payload(key: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    fallback = default_invest_setting(key)
    if not isinstance(fallback, dict):
        return {}
    if not isinstance(payload, dict):
        return fallback
    merged = _merge_default(fallback, payload)
    return merged if isinstance(merged, dict) else fallback


def _string_set(value: Any, fallback: list[str], *, case: str) -> frozenset[str]:
    source = value if isinstance(value, (list, tuple, set)) else fallback
    normalized: list[str] = []
    for item in source:
        text = str(item).strip()
        if not text:
            continue
        normalized.append(text.upper() if case == "upper" else text.lower())
    if not normalized:
        return _string_set(fallback, fallback, case=case)
    return frozenset(normalized)


def _decimal_setting(
    payload: dict[str, Any],
    key: str,
    fallback: Decimal,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> Decimal:
    value = _decimal(payload.get(key), fallback)
    if minimum is not None and value < minimum:
        return fallback
    if maximum is not None and value > maximum:
        return fallback
    return value


def _decimal(value: Any, fallback: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return fallback
    if not parsed.is_finite():
        return fallback
    return parsed


def _int_setting(
    payload: dict[str, Any],
    key: str,
    fallback: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        value = int(payload.get(key, fallback))
    except (TypeError, ValueError):
        return fallback
    if minimum is not None and value < minimum:
        return fallback
    if maximum is not None and value > maximum:
        return fallback
    return value


def _bool_setting(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return fallback


def _is_missing_invest_settings_table(exc: Exception) -> bool:
    message = str(exc).lower()
    return "invest_settings" in message and (
        "does not exist" in message
        or "undefinedtable" in message
        or "no such table" in message
    )


async def _rollback_after_settings_fallback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        logger.exception("invest_settings_fallback_rollback_failed")


async def _invest_settings_table_exists(session: AsyncSession) -> bool:
    connection = await session.connection()
    return await connection.run_sync(
        lambda sync_connection: sqlalchemy_inspect(sync_connection).has_table(
            "invest_settings"
        )
    )
