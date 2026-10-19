"""Verified identity gates for new automatic entries; exits never use this gate."""
from datetime import datetime, timedelta, timezone
import re
import httpx
from sqlalchemy import case, select

from app.core.config import settings
from app.models import Instrument, Position, RadarRun, RadarSnapshot

RESTRICTED_SYMBOLS = frozenset({'SOXS', 'BMNZ'})
RESTRICTED_NAME = re.compile(r'\b(?:leveraged|inverse|[23]\s*[x×]|ultrashort)\b|\bdaily\b.*\b(?:bear|short|bull)\b', re.I)


def instrument_rejection(instrument, now):
    if instrument is None:
        return 'Verified instrument identity is unavailable.'
    if instrument.ticker.upper() in RESTRICTED_SYMBOLS or RESTRICTED_NAME.search(instrument.name or ''):
        return 'Leveraged or inverse products are excluded from automatic entries.'
    metadata = getattr(instrument, 'execution_metadata', None) or {}
    if metadata.get('source') != 'fmp_profile' or metadata.get('symbol') != instrument.ticker:
        return 'Instrument classification awaits provider verification.'
    try:
        checked = datetime.fromisoformat(metadata['checked_at'])
        if checked.tzinfo is None or not timedelta(0) <= now - checked <= timedelta(days=30):
            return 'Instrument classification needs a current provider verification.'
    except (KeyError, TypeError, ValueError):
        return 'Instrument classification awaits provider verification.'
    if (metadata.get('product_type') not in {'equity', 'etf'}
            or metadata.get('product_type') != instrument.asset_class
            or instrument.currency != 'USD' or metadata.get('currency') != 'USD'):
        return 'Verified product type or currency is outside the automatic mandate.'
    if instrument.asset_class == 'equity' and (not instrument.sector or not instrument.industry):
        return 'Verified sector and industry are required for automatic stock entries.'
    return None


def parse_profile(ticker, payload, now):
    """Exact symbol, explicit booleans, no defaulting an unknown fund to equity."""
    row = next((r for r in payload if isinstance(r, dict) and r.get('symbol') == ticker), None) if isinstance(payload, list) else None
    if (row is None or row.get('currency') != 'USD' or row.get('isActivelyTrading') is not True
            or type(row.get('isEtf')) is not bool or type(row.get('isFund')) is not bool):
        return None
    name = str(row.get('companyName') or '').strip()
    if not name:
        return None
    kind = 'etf' if row['isEtf'] else 'unsupported' if row['isFund'] else 'equity'
    if ticker in RESTRICTED_SYMBOLS or RESTRICTED_NAME.search(name):
        kind = 'restricted'
    sector = str(row.get('sector') or '').strip() or None
    industry = str(row.get('industry') or '').strip() or None
    if kind == 'equity' and (not sector or not industry):
        return None
    return {'name': name[:255], 'sector': sector[:128] if sector else None,
            'industry': industry[:128] if industry else None,
            'asset_class': 'etf' if row['isEtf'] else 'equity',
            'metadata': {'symbol': ticker, 'product_type': kind, 'source': 'fmp_profile',
                         'currency': 'USD', 'checked_at': now.isoformat()}}


async def refresh_metadata(session, *, now=None):
    now = now or datetime.now(timezone.utc)
    if not settings.hf_fmp_api_key:
        raise RuntimeError('MetadataProviderNotConfigured')
    held = select(Position.instrument_id).where(Position.quantity > 0)
    discoveries = select(RadarSnapshot.ticker).join(RadarRun).where(
        RadarRun.started_at >= now-timedelta(days=7), RadarRun.status == 'completed',
        RadarSnapshot.radar_priority.in_(['P0','P1']))
    rows = list(await session.scalars(select(Instrument).where(
        Instrument.currency == 'USD', Instrument.asset_class.in_(['equity','etf']),
        (Instrument.id.in_(held)) | (Instrument.ticker.in_(discoveries)),
        (Instrument.metadata_next_attempt_at.is_(None)) | (Instrument.metadata_next_attempt_at <= now),
    ).order_by(case((Instrument.id.in_(held), 0), else_=1),
               Instrument.metadata_next_attempt_at.asc().nullsfirst(), Instrument.ticker).limit(4)))
    for row in rows:
        row.metadata_next_attempt_at = now + timedelta(minutes=30)
    await session.commit()
    failures = 0
    async with httpx.AsyncClient(base_url=settings.fmp_base_url.removesuffix('/api'), timeout=8) as client:
        for row in rows:
            try:
                response = await client.get('/stable/profile', params={'symbol': row.ticker, 'apikey': settings.hf_fmp_api_key})
                response.raise_for_status()
                profile = parse_profile(row.ticker, response.json(), now)
            except (httpx.HTTPError, ValueError, TypeError):
                profile = None
            if profile is None:
                failures += 1
                continue
            row.name, row.sector, row.industry = profile['name'], profile['sector'], profile['industry']
            row.asset_class, row.execution_metadata = profile['asset_class'], profile['metadata']
            row.metadata_next_attempt_at = now + timedelta(days=7)
            await session.commit()
    if failures:
        raise RuntimeError('MetadataVerificationIncomplete')
    return len(rows)
