"""Fund-level monitored universe for Market Radar.

This is the v0 catalog spine: curated liquid seeds plus live book/opportunity
names. Catalog membership is not a live-book position and does not create
instrument rows. Quotes attach to instruments only after a name prints a
live tape or enters the queue / Ticker Analyst.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.market_constants import RADAR_SECTOR_ETFS
from app.models import RadarUniverseMember
from app.services.market_data.sessions import JURISDICTION_US
from app.services.market_radar.scoring import RadarCandidate
from app.services.market_radar.watchlist import AlwaysWatchedSet


@dataclass(frozen=True)
class SeedMember:
    ticker: str
    name: str
    jurisdiction: str
    sector: str
    industry: str
    asset_class: str = "equity"
    exchange: str | None = None
    currency: str = "USD"
    liquidity_rank: int | None = None
    source: str = "seed_liquid_universe"


@dataclass(frozen=True)
class CatalogSyncResult:
    active_count: int
    upserted_count: int
    seeded_count: int
    always_watched_count: int


SOURCE_RANKS = {
    "book": 10,
    "sector_etf_seed": 20,
    "seed_liquid_universe": 80,
    "manual": 90,
}


US_LIQUID_SEEDS: tuple[SeedMember, ...] = (
    SeedMember("AAPL", "Apple Inc.", "US", "Technology", "Consumer Electronics", liquidity_rank=1),
    SeedMember("MSFT", "Microsoft Corporation", "US", "Technology", "Software", liquidity_rank=2),
    SeedMember("NVDA", "NVIDIA Corporation", "US", "Technology", "Semiconductors", liquidity_rank=3),
    SeedMember("AMZN", "Amazon.com Inc.", "US", "Consumer Cyclical", "Internet Retail", liquidity_rank=4),
    SeedMember("GOOGL", "Alphabet Inc.", "US", "Communication Services", "Internet Content", liquidity_rank=5),
    SeedMember("META", "Meta Platforms Inc.", "US", "Communication Services", "Internet Content", liquidity_rank=6),
    SeedMember("TSLA", "Tesla Inc.", "US", "Consumer Cyclical", "Auto Manufacturers", liquidity_rank=7),
    SeedMember("AVGO", "Broadcom Inc.", "US", "Technology", "Semiconductors", liquidity_rank=8),
    SeedMember("AMD", "Advanced Micro Devices Inc.", "US", "Technology", "Semiconductors", liquidity_rank=9),
    SeedMember("INTC", "Intel Corporation", "US", "Technology", "Semiconductors", liquidity_rank=10),
    SeedMember("JPM", "JPMorgan Chase & Co.", "US", "Financial Services", "Banks", liquidity_rank=11),
    SeedMember("BAC", "Bank of America Corporation", "US", "Financial Services", "Banks", liquidity_rank=12),
    SeedMember("GS", "Goldman Sachs Group Inc.", "US", "Financial Services", "Capital Markets", liquidity_rank=13),
    SeedMember("MS", "Morgan Stanley", "US", "Financial Services", "Capital Markets", liquidity_rank=14),
    SeedMember("V", "Visa Inc.", "US", "Financial Services", "Credit Services", liquidity_rank=15),
    SeedMember("MA", "Mastercard Incorporated", "US", "Financial Services", "Credit Services", liquidity_rank=16),
    SeedMember("XOM", "Exxon Mobil Corporation", "US", "Energy", "Oil & Gas Integrated", liquidity_rank=17),
    SeedMember("CVX", "Chevron Corporation", "US", "Energy", "Oil & Gas Integrated", liquidity_rank=18),
    SeedMember("COP", "ConocoPhillips", "US", "Energy", "Oil & Gas E&P", liquidity_rank=19),
    SeedMember("SLB", "SLB", "US", "Energy", "Oil & Gas Equipment", liquidity_rank=20),
    SeedMember("LLY", "Eli Lilly and Company", "US", "Healthcare", "Drug Manufacturers", liquidity_rank=21),
    SeedMember("UNH", "UnitedHealth Group Incorporated", "US", "Healthcare", "Healthcare Plans", liquidity_rank=22),
    SeedMember("JNJ", "Johnson & Johnson", "US", "Healthcare", "Drug Manufacturers", liquidity_rank=23),
    SeedMember("MRK", "Merck & Co. Inc.", "US", "Healthcare", "Drug Manufacturers", liquidity_rank=24),
    SeedMember("PFE", "Pfizer Inc.", "US", "Healthcare", "Drug Manufacturers", liquidity_rank=25),
    SeedMember("COST", "Costco Wholesale Corporation", "US", "Consumer Defensive", "Discount Stores", liquidity_rank=26),
    SeedMember("WMT", "Walmart Inc.", "US", "Consumer Defensive", "Discount Stores", liquidity_rank=27),
    SeedMember("PG", "Procter & Gamble Company", "US", "Consumer Defensive", "Household Products", liquidity_rank=28),
    SeedMember("KO", "Coca-Cola Company", "US", "Consumer Defensive", "Beverages", liquidity_rank=29),
    SeedMember("PEP", "PepsiCo Inc.", "US", "Consumer Defensive", "Beverages", liquidity_rank=30),
    SeedMember("HD", "Home Depot Inc.", "US", "Consumer Cyclical", "Home Improvement Retail", liquidity_rank=31),
    SeedMember("MCD", "McDonald's Corporation", "US", "Consumer Cyclical", "Restaurants", liquidity_rank=32),
    SeedMember("NKE", "Nike Inc.", "US", "Consumer Cyclical", "Footwear & Accessories", liquidity_rank=33),
    SeedMember("DIS", "Walt Disney Company", "US", "Communication Services", "Entertainment", liquidity_rank=34),
    SeedMember("NFLX", "Netflix Inc.", "US", "Communication Services", "Entertainment", liquidity_rank=35),
    SeedMember("CRM", "Salesforce Inc.", "US", "Technology", "Software", liquidity_rank=36),
    SeedMember("ORCL", "Oracle Corporation", "US", "Technology", "Software", liquidity_rank=37),
    SeedMember("ADBE", "Adobe Inc.", "US", "Technology", "Software", liquidity_rank=38),
    SeedMember("CSCO", "Cisco Systems Inc.", "US", "Technology", "Communication Equipment", liquidity_rank=39),
    SeedMember("TMO", "Thermo Fisher Scientific Inc.", "US", "Healthcare", "Diagnostics & Research", liquidity_rank=40),
    SeedMember("GE", "GE Aerospace", "US", "Industrials", "Aerospace & Defense", liquidity_rank=41),
    SeedMember("BA", "Boeing Company", "US", "Industrials", "Aerospace & Defense", liquidity_rank=42),
    SeedMember("CAT", "Caterpillar Inc.", "US", "Industrials", "Farm & Heavy Construction Machinery", liquidity_rank=43),
    SeedMember("DE", "Deere & Company", "US", "Industrials", "Farm & Heavy Construction Machinery", liquidity_rank=44),
    SeedMember("NEE", "NextEra Energy Inc.", "US", "Utilities", "Utilities Regulated Electric", liquidity_rank=45),
    SeedMember("PLD", "Prologis Inc.", "US", "Real Estate", "REIT Industrial", liquidity_rank=46),
    SeedMember("AMT", "American Tower Corporation", "US", "Real Estate", "REIT Specialty", liquidity_rank=47),
    SeedMember("T", "AT&T Inc.", "US", "Communication Services", "Telecom Services", liquidity_rank=48),
    SeedMember("VZ", "Verizon Communications Inc.", "US", "Communication Services", "Telecom Services", liquidity_rank=49),
    SeedMember("UBER", "Uber Technologies Inc.", "US", "Technology", "Software", liquidity_rank=50),
)

NG_LIQUID_SEEDS: tuple[SeedMember, ...] = (
    SeedMember("DANGCEM.NG", "Dangote Cement", "NG", "Basic Materials", "Building Materials", exchange="NGX", currency="NGN", liquidity_rank=1),
    SeedMember("MTNN.NG", "MTN Nigeria Communications", "NG", "Communication Services", "Telecom Services", exchange="NGX", currency="NGN", liquidity_rank=2),
    SeedMember("AIRTELAFRI.NG", "Airtel Africa", "NG", "Communication Services", "Telecom Services", exchange="NGX", currency="NGN", liquidity_rank=3),
    SeedMember("GTCO.NG", "Guaranty Trust Holding Company", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=4),
    SeedMember("ZENITHBANK.NG", "Zenith Bank", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=5),
    SeedMember("ACCESSCORP.NG", "Access Holdings", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=6),
    SeedMember("UBA.NG", "United Bank for Africa", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=7),
    SeedMember("FBNH.NG", "FBN Holdings", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=8),
    SeedMember("BUAFOODS.NG", "BUA Foods", "NG", "Consumer Defensive", "Packaged Foods", exchange="NGX", currency="NGN", liquidity_rank=9),
    SeedMember("BUACEMENT.NG", "BUA Cement", "NG", "Basic Materials", "Building Materials", exchange="NGX", currency="NGN", liquidity_rank=10),
    SeedMember("SEPLAT.NG", "Seplat Energy", "NG", "Energy", "Oil & Gas E&P", exchange="NGX", currency="NGN", liquidity_rank=11),
    SeedMember("NESTLE.NG", "Nestle Nigeria", "NG", "Consumer Defensive", "Packaged Foods", exchange="NGX", currency="NGN", liquidity_rank=12),
    SeedMember("NB.NG", "Nigerian Breweries", "NG", "Consumer Defensive", "Beverages", exchange="NGX", currency="NGN", liquidity_rank=13),
    SeedMember("GUINNESS.NG", "Guinness Nigeria", "NG", "Consumer Defensive", "Beverages", exchange="NGX", currency="NGN", liquidity_rank=14),
    SeedMember("WAPCO.NG", "Lafarge Africa", "NG", "Basic Materials", "Building Materials", exchange="NGX", currency="NGN", liquidity_rank=15),
    SeedMember("FLOURMILL.NG", "Flour Mills of Nigeria", "NG", "Consumer Defensive", "Packaged Foods", exchange="NGX", currency="NGN", liquidity_rank=16),
    SeedMember("DANGSUGAR.NG", "Dangote Sugar Refinery", "NG", "Consumer Defensive", "Packaged Foods", exchange="NGX", currency="NGN", liquidity_rank=17),
    SeedMember("PRESCO.NG", "Presco", "NG", "Consumer Defensive", "Farm Products", exchange="NGX", currency="NGN", liquidity_rank=18),
    SeedMember("OKOMUOIL.NG", "Okomu Oil Palm", "NG", "Consumer Defensive", "Farm Products", exchange="NGX", currency="NGN", liquidity_rank=19),
    SeedMember("TRANSCORP.NG", "Transnational Corporation", "NG", "Industrials", "Conglomerates", exchange="NGX", currency="NGN", liquidity_rank=20),
    SeedMember("OANDO.NG", "Oando", "NG", "Energy", "Oil & Gas Integrated", exchange="NGX", currency="NGN", liquidity_rank=21),
    SeedMember("FIDELITYBK.NG", "Fidelity Bank", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=22),
    SeedMember("FCMB.NG", "FCMB Group", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=23),
    SeedMember("STERLINGNG.NG", "Sterling Financial Holdings", "NG", "Financial Services", "Banks", exchange="NGX", currency="NGN", liquidity_rank=24),
    SeedMember("NGXGROUP.NG", "Nigerian Exchange Group", "NG", "Financial Services", "Financial Data & Exchanges", exchange="NGX", currency="NGN", liquidity_rank=25),
)


async def sync_monitored_universe(
    session: AsyncSession,
    *,
    watched: AlwaysWatchedSet | None = None,
) -> CatalogSyncResult:
    now = datetime.now(timezone.utc)
    incoming = _seed_members()
    if watched is not None:
        for candidate in watched.candidates.values():
            incoming[candidate.ticker] = SeedMember(
                ticker=candidate.ticker,
                name=candidate.name,
                jurisdiction=candidate.jurisdiction,
                sector=candidate.sector or "Unclassified",
                industry=candidate.industry or candidate.sector or "Unclassified",
                asset_class=_asset_class(candidate.asset_class),
                exchange=candidate.exchange,
                currency=candidate.currency,
                source="book",
            )

    if not incoming:
        return CatalogSyncResult(0, 0, 0, 0)

    existing_members = {
        row.ticker: row
        for row in await session.scalars(
            select(RadarUniverseMember).where(
                RadarUniverseMember.ticker.in_(list(incoming))
            )
        )
    }
    upserted = 0
    for seed in incoming.values():
        source_rank = SOURCE_RANKS.get(seed.source, 100)
        member = existing_members.get(seed.ticker)
        if member is None:
            member = RadarUniverseMember(
                ticker=seed.ticker,
                name=seed.name,
                jurisdiction=seed.jurisdiction,
                sector=seed.sector,
                industry=seed.industry,
                asset_class=_asset_class(seed.asset_class),
                exchange=seed.exchange,
                currency=seed.currency,
                source=seed.source,
                source_rank=source_rank,
                is_active=True,
                always_watched=seed.source == "book",
                liquidity_rank=seed.liquidity_rank,
                last_synced_at=now,
                member_metadata={"seed_source": seed.source},
            )
            session.add(member)
            existing_members[seed.ticker] = member
            upserted += 1
            continue

        if source_rank <= (member.source_rank or 100):
            member.name = seed.name
            member.jurisdiction = seed.jurisdiction
            member.sector = seed.sector
            member.industry = seed.industry
            member.asset_class = _asset_class(seed.asset_class)
            member.exchange = seed.exchange
            member.currency = seed.currency
            member.source = seed.source
            member.source_rank = source_rank
            member.liquidity_rank = seed.liquidity_rank or member.liquidity_rank
        member.is_active = True
        member.always_watched = member.always_watched or seed.source == "book"
        member.last_synced_at = now
        upserted += 1

    await session.flush()

    active_count = await _active_count(session)
    return CatalogSyncResult(
        active_count=active_count,
        upserted_count=upserted,
        seeded_count=len(_seed_members()),
        always_watched_count=len(watched.candidates) if watched is not None else 0,
    )


async def load_catalog_candidates(
    session: AsyncSession,
    *,
    jurisdictions: list[str],
) -> list[RadarCandidate]:
    if not jurisdictions:
        return []
    members = await session.scalars(
        select(RadarUniverseMember)
        .where(RadarUniverseMember.is_active.is_(True))
        .where(RadarUniverseMember.jurisdiction.in_(jurisdictions))
        .order_by(
            RadarUniverseMember.always_watched.desc(),
            RadarUniverseMember.liquidity_rank.asc().nulls_last(),
            RadarUniverseMember.ticker.asc(),
        )
    )
    return [_candidate_from_member(member) for member in members]


def _seed_members() -> dict[str, SeedMember]:
    members: dict[str, SeedMember] = {}
    for ticker, sector, asset_class in RADAR_SECTOR_ETFS:
        members[ticker] = SeedMember(
            ticker=ticker,
            name=ticker,
            jurisdiction=JURISDICTION_US,
            sector=sector,
            industry=asset_class.title(),
            asset_class="etf",
            exchange="US",
            source="sector_etf_seed",
        )
    for seed in US_LIQUID_SEEDS + NG_LIQUID_SEEDS:
        members[seed.ticker] = seed
    return members


async def _active_count(session: AsyncSession) -> int:
    return len(
        list(
            await session.scalars(
                select(RadarUniverseMember.id).where(
                    RadarUniverseMember.is_active.is_(True)
                )
            )
        )
    )


def _candidate_from_member(member: RadarUniverseMember) -> RadarCandidate:
    return RadarCandidate(
        ticker=member.ticker,
        name=member.name,
        jurisdiction=member.jurisdiction,
        sector=member.sector,
        industry=member.industry,
        asset_class=member.asset_class,
        exchange=member.exchange,
        currency=member.currency,
        source=member.source,
        always_watched=member.always_watched,
        is_catalog_member=True,
        evidence={
            "catalog_source": member.source,
            "liquidity_rank": member.liquidity_rank,
            "avg_dollar_volume": _decimal_text(member.avg_dollar_volume),
        },
    )


def _asset_class(value: str | None) -> str:
    normalized = (value or "equity").strip().lower()
    if normalized in {"equity", "etf", "bond", "commodity", "cash_equivalent", "other"}:
        return normalized
    return "equity"


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
