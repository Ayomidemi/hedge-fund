from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from pydantic import ValidationError

from app.api.schemas.operating_core import CashDepositCreate, InstrumentCreate, ManualTradeCreate, ManualTradeUpdate
from app.api.schemas.risk_centre import PreTradeRiskCheckCreate
from app.core.auth import AuthenticatedUser
from app.models import Instrument, InstrumentQuote, Trade
from app.services.market_data.fx_convert import mark_price_for_position
from app.services.portfolio.operating_core import (
    CapitalValidationError, _trade_cash_ledger_values, _trade_price_in_base, _validate_trade_edit,
    cash_balance_in_base, get_or_create_default_portfolio,
)
from app.services.risk.risk_centre import PortfolioRiskState, RiskPosition, _apply_trade_to_state, _pre_trade_decision

D = Decimal


class CapitalInvariantTests(TestCase):
    def test_frozen_foreign_price_and_fees_are_not_revalued_at_current_fx(self):
        instrument = Instrument(ticker="GTCO.NG", name="GTCO", currency="NGN", asset_class="equity")
        portfolio = SimpleNamespace(base_currency="USD")
        trade = Trade(id=uuid4(), quantity=D("10"), executed_price=D("1500"), fees=D("150"),
                      executed_price_base=D("1"), fees_base=D("0.10"), side="buy", trade_date=datetime.now(timezone.utc))
        # Native NGN/USD has since moved from 1500 to 2000.
        values = _trade_cash_ledger_values(trade, instrument, portfolio,
                                           {("USD", "NGN"): SimpleNamespace(rate=D("2000"))})
        self.assertEqual(values["amount"], D("-10.10"))
        self.assertEqual(values["currency"], "USD")
        trade.executed_price_base = None
        with self.assertRaises(CapitalValidationError):
            _trade_price_in_base(trade, instrument, portfolio, {("USD", "NGN"): SimpleNamespace(rate=D("2000"))})

    def test_fill_economics_are_immutable_but_notes_can_change(self):
        instrument = InstrumentCreate(ticker="AAPL", name="Apple", asset_class="equity")
        at = datetime.now(timezone.utc)
        payload = ManualTradeUpdate(instrument=instrument, side="buy", quantity=1, price=100, trade_date=at, rationale="new note")
        trade = SimpleNamespace(instrument=instrument, status="filled", side="buy", quantity=D("1"),
                                executed_price=D("100"), fees=D("0"), trade_date=at)
        _validate_trade_edit(trade, payload)
        with self.assertRaises(CapitalValidationError):
            _validate_trade_edit(trade, payload.model_copy(update={"quantity": D("2")}))

    def test_excess_precision_cannot_round_cash_differently_from_database(self):
        with self.assertRaises(ValidationError):
            CashDepositCreate(amount="0.001", platform="test")
        with self.assertRaises(ValidationError):
            ManualTradeCreate(instrument=InstrumentCreate(ticker="ACME", name="Acme", asset_class="equity"),
                              side="buy", quantity="1.000000001", price="100")

    def test_marks_never_treat_unsupported_currency_as_usd(self):
        instrument = Instrument(ticker="EURSTOCK", name="Stock", currency="EUR", asset_class="equity")
        quote = InstrumentQuote(price=D("100"), currency="EUR")
        self.assertIsNone(mark_price_for_position(quote=quote, instrument=instrument, portfolio_base_currency="USD", fx_rates={}))
        quote.price = D("NaN")
        self.assertIsNone(mark_price_for_position(quote=quote, instrument=instrument, portfolio_base_currency="USD", fx_rates={}))

    def test_native_ngn_portfolio_does_not_convert_ngn_marks_to_usd(self):
        instrument = Instrument(ticker="GTCO.NG", name="GTCO", currency="NGN", asset_class="equity")
        quote = InstrumentQuote(price=D("1500"), currency="NGN")
        self.assertEqual(mark_price_for_position(quote=quote, instrument=instrument, portfolio_base_currency="NGN", fx_rates={}), D("1500"))

    def test_risk_does_not_reprice_old_holdings_at_order_price(self):
        state = PortfolioRiskState(portfolio_id=uuid4(), portfolio_name="Fund", calculated_at=datetime.now(timezone.utc),
            as_of_date=date.today(), nav=D("2000"), cash_balance=D("1000"), invested_value=D("1000"),
            positions=[RiskPosition(instrument_id=uuid4(), ticker="ACME", name="Acme", asset_class="equity",
                sector="Tech", quantity=D("10"), average_cost=D("80"), market_value=D("1000"), unrealized_pnl=D("200"))])
        payload = PreTradeRiskCheckCreate(instrument=InstrumentCreate(ticker="ACME", name="Acme", asset_class="equity"),
                                          side="buy", quantity=1, price=90)
        result, _, _ = _apply_trade_to_state(state, payload, fx_rates={})
        self.assertEqual(result.positions[0].market_value, D("1100"))
        self.assertEqual(result.nav, D("2010"))
        payload = payload.model_copy(update={"quantity": D("100")})
        _, _, messages = _apply_trade_to_state(state, payload, fx_rates={})
        self.assertEqual(_pre_trade_decision("normal", [], messages, []), "reject")


class CapitalAsyncInvariantTests(IsolatedAsyncioTestCase):
    async def test_cash_is_converted_and_future_deposits_do_not_fund_trades(self):
        entries = [SimpleNamespace(amount=D("100"), currency="USD", entry_date=date.today()),
                   SimpleNamespace(amount=D("1500"), currency="NGN", entry_date=date.today()),
                   SimpleNamespace(amount=D("99999"), currency="USD", entry_date=date(2099, 1, 1))]
        with patch("app.services.portfolio.operating_core.load_fx_rates", AsyncMock(return_value={
            ("USD", "NGN"): SimpleNamespace(rate=D("1500"))
        })):
            balance = await cash_balance_in_base(AsyncMock(), SimpleNamespace(base_currency="USD"), entries)
        self.assertEqual(balance, D("101"))

    async def test_portfolio_lookup_never_commits_an_existing_transaction(self):
        session = AsyncMock()
        portfolio = SimpleNamespace(id=uuid4())
        with patch("app.services.portfolio.operating_core._load_owned_portfolio", AsyncMock(return_value=portfolio)), \
             patch("app.services.portfolio.operating_core._ensure_default_risk_limits", AsyncMock()):
            self.assertIs(await get_or_create_default_portfolio(session, AuthenticatedUser(id="user", email=None)), portfolio)
        session.commit.assert_not_awaited()
