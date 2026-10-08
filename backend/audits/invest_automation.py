"""Readiness probes. No live-account writes or provider requests.

Run from backend:
  HF_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55439/hedge_audit_test \
    .venv/bin/python audits/invest_automation.py

The optional SQL probe permits only a localhost disposable *_test database and
creates/drops its own isolated schema. Results describe current shortcomings;
'gap_present' is not a passing readiness assertion.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema
from app.api.schemas.invest import InvestOrderCreate
from app.db.locks import lock_retail_account
from app.models import RetailAccount
from app.services.invest.risk import evaluate_order_risk
from app.services.brokerage.paper import PaperBrokerProvider, _balances
from app.services.market_data.quote_cache import get_cached_quote_price

D = Decimal

def report(name, present, **evidence):
    print(json.dumps({'probe': name, 'gap_present': present, **evidence}, default=str), flush=True)


async def cash_lock_probe(url):
    parsed = make_url(url)
    if parsed.host not in {'localhost', '127.0.0.1', '::1'} or not (parsed.database or '').endswith('_test'):
        raise RuntimeError('Use a localhost disposable database whose name ends in _test.')
    schema = 'invest_audit_' + uuid4().hex
    engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(CreateSchema(schema))
            await conn.run_sync(RetailAccount.__table__.create)
        account_id = uuid4()
        async with factory() as s:
            s.add(RetailAccount(id=account_id, user_id='disposable', account_number=uuid4().hex[:20],
                broker_provider='PAPER', broker_account_id=str(account_id), status='active',
                base_currency='USD', cash_balance=D('100')))
            await s.commit()
        async with factory() as first, factory() as waiting:
            # Both requests read before the first commits. The second must see
            # the new balance when it subsequently obtains the account lock.
            first_account = await first.get(RetailAccount, account_id)
            waiting_account = await waiting.get(RetailAccount, account_id)
            locked = await lock_retail_account(first, first_account)
            locked.cash_balance = D('40')
            await first.commit()
            locked_waiting = await lock_retail_account(waiting, waiting_account)
            actual = await waiting.scalar(select(RetailAccount.cash_balance).where(RetailAccount.id == account_id))
            report('retail_lock_retains_prelock_balance', locked_waiting.cash_balance != actual,
                   locked_object_cash=locked_waiting.cash_balance, committed_database_cash=actual)
            await waiting.rollback()
        async with factory() as cached, factory() as writer:
            old = await cached.get(RetailAccount, account_id)
            current = await writer.get(RetailAccount, account_id)
            current.cash_balance = D('20')
            await writer.commit()
            locked = await PaperBrokerProvider(cached)._load_account(str(account_id), for_update=True)
            actual = await cached.scalar(select(RetailAccount.cash_balance).where(RetailAccount.id == account_id))
            report('broker_lock_retains_prelock_balance', locked.cash_balance != actual,
                   locked_object_cash=locked.cash_balance, committed_database_cash=actual)
            assert old is locked
            await cached.rollback()
    finally:
        async with engine.begin() as conn:
            await conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()


async def main():
    order = InvestOrderCreate.model_validate({'ticker':'TEST', 'side':'BUY', 'quantity':1,
                                             'order_type':'limit', 'limit_price':'90'})
    report('order_api_drops_limit_price', 'limit_price' not in order.model_dump(), payload=order.model_dump())
    quote = SimpleNamespace(price=D('100'), is_stale=False,
                            as_of=datetime.now(timezone.utc)-timedelta(days=3))
    price = await get_cached_quote_price(SimpleNamespace(scalar=AsyncMock(return_value=quote)), 'TEST')
    report('quote_reader_accepts_old_timestamp_when_flag_is_clear', price == quote.price, price=price)
    with patch('app.services.invest.risk.session_for', return_value=SimpleNamespace(is_open=False, label='US market')):
        risk = evaluate_order_risk(account=SimpleNamespace(cash_balance=D('10000'), base_currency='USD'),
            instrument=SimpleNamespace(ticker='TEST', currency='USD', asset_class='equity'),
            payload=InvestOrderCreate(ticker='TEST', side='BUY', amount=D('9000')))
    report('closed_session_and_90pct_cash_order_not_blocked', not risk.blockers,
           blocker_count=len(risk.blockers), warnings=risk.warnings)
    balances = _balances(SimpleNamespace(cash_balance=D('10000'), base_currency='USD'))
    report('balances_have_no_order_reservations', balances.buying_power == balances.cash and balances.pending == 0,
           cash=balances.cash, buying_power=balances.buying_power, pending=balances.pending)
    url = os.environ.get('HF_TEST_DATABASE_URL')
    if url:
        await cash_lock_probe(url)
    else:
        print(json.dumps({'sql_probes':'skipped; supply disposable HF_TEST_DATABASE_URL'}))

if __name__ == '__main__':
    asyncio.run(main())
