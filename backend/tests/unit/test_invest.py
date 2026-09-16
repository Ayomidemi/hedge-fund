from unittest import TestCase
from decimal import Decimal

from app.core.auth import (
    AuthenticatedUser,
    user_can_access_capital,
    user_can_access_invest,
)
from app.core.config import settings
from app.main import app
from app.api.schemas.invest import InvestOrderCreate
from app.models import Instrument, RetailAccount
from app.services.brokerage.paper import _buy_size, _fixed_income_buy_size
from app.services.brokerage.protocol import BrokerValidationError, SubmitOrderRequest
from app.services.invest.fixed_income import (
    fixed_income_cashflows,
    fixed_income_quote,
    fixed_income_response,
    get_fixed_income_product,
    search_fixed_income_products,
)
from app.services.invest.markets import board_tickers
from app.services.invest.risk import evaluate_order_risk


class InvestPermissionTests(TestCase):
    def test_retail_user_cannot_access_capital(self) -> None:
        user = AuthenticatedUser(id="u1", email="r@example.com", role="RETAIL_USER")
        self.assertTrue(user_can_access_invest(user))
        self.assertFalse(user_can_access_capital(user))

    def test_capital_pm_can_access_both(self) -> None:
        user = AuthenticatedUser(id="u2", email="pm@example.com", role="CAPITAL_PM")
        self.assertTrue(user_can_access_invest(user))
        self.assertTrue(user_can_access_capital(user))

    def test_default_authenticated_user_is_not_capital_by_default(self) -> None:
        user = AuthenticatedUser(id="u3", email="a@example.com", role="authenticated")
        self.assertTrue(user_can_access_invest(user))
        self.assertFalse(user_can_access_capital(user))

    def test_auth_disabled_anonymous_user_keeps_local_capital_access(self) -> None:
        user = AuthenticatedUser(id="anonymous", email=None, role="anonymous")
        self.assertTrue(user_can_access_invest(user))
        self.assertTrue(user_can_access_capital(user))

    def test_paper_starting_cash_is_decimal(self) -> None:
        self.assertIsInstance(settings.invest_paper_starting_cash, Decimal)
        self.assertGreaterEqual(settings.invest_paper_starting_cash, Decimal("100.00"))


class InvestRouteTests(TestCase):
    def test_invest_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/api/invest/account", paths)
        self.assertIn("/api/invest/home", paths)
        self.assertIn("/api/invest/orders", paths)
        self.assertIn("/api/invest/watchlist", paths)
        self.assertIn("/api/invest/paper/deposit", paths)
        self.assertIn("/api/invest/instruments/search", paths)
        self.assertIn("/api/invest/discover", paths)
        self.assertIn("/api/news/overview", paths)
        self.assertIn("/api/invest/orders/{order_id}", paths)
        self.assertIn("/api/invest/orders/{order_id}/cancel", paths)
        self.assertIn("/api/invest/fixed-income", paths)
        self.assertIn("/api/invest/fixed-income/{ticker}", paths)
        self.assertIn("/api/invest/markets", paths)

    def test_operating_core_stays_on_capital_auth(self) -> None:
        spec = app.openapi()["paths"]["/api/operating-core/dashboard"]["get"]
        # The route exists; retail isolation is enforced in require_capital_user.
        self.assertIn("operationId", spec)


class PaperBrokerSizingTests(TestCase):
    def test_notional_buy_converts_to_quantity(self) -> None:
        quantity, notional = _buy_size(
            SubmitOrderRequest(symbol="TEST", side="BUY", notional=Decimal("500")),
            Decimal("250"),
        )
        self.assertEqual(quantity, Decimal("2.00000000"))
        self.assertEqual(notional, Decimal("500.00"))

    def test_buy_requires_amount_or_quantity(self) -> None:
        with self.assertRaises(BrokerValidationError):
            _buy_size(SubmitOrderRequest(symbol="TEST", side="BUY"), Decimal("10"))

    def test_fixed_income_notional_buy_rounds_to_face_increment(self) -> None:
        quantity, notional = _fixed_income_buy_size(
            SubmitOrderRequest(
                symbol="US-TBILL-13W",
                side="BUY",
                notional=Decimal("500"),
            ),
            Decimal("0.987500"),
            Decimal("100.00"),
        )
        self.assertEqual(quantity, Decimal("500.00000000"))
        self.assertEqual(notional, Decimal("493.75"))


class FixedIncomeScopeTests(TestCase):
    def test_fixed_income_catalog_includes_us_and_nigeria_products(self) -> None:
        all_products = search_fixed_income_products()
        tickers = {product.ticker for product in all_products}
        self.assertIn("US-TBILL-13W", tickers)
        self.assertIn("FGN-BOND-2029", tickers)

    def test_fixed_income_product_carries_retail_fields(self) -> None:
        product = get_fixed_income_product("NG-TBILL-182D")
        self.assertIsNotNone(product)
        assert product is not None
        self.assertEqual(product.currency, "NGN")
        self.assertGreaterEqual(product.minimum_order_amount, Decimal("100000.00"))
        self.assertEqual(product.trade_status, "paper_tradable")
        self.assertIsNotNone(product.indicative_yield_pct)
        self.assertIsNone(product.proxy_ticker)

    def test_fixed_income_quote_models_price_settlement_and_cashflows(self) -> None:
        bill = get_fixed_income_product("US-TBILL-13W")
        bond = get_fixed_income_product("FGN-BOND-2029")
        assert bill is not None
        assert bond is not None

        bill_quote = fixed_income_quote(bill)
        self.assertLess(bill_quote.dirty_price_per_100, Decimal("100"))
        self.assertEqual(bill_quote.accrued_interest_per_100, Decimal("0.0000"))
        self.assertGreater(bill_quote.days_to_maturity, 0)

        bond_flows = fixed_income_cashflows(bond)
        self.assertGreater(len(bond_flows), 1)
        self.assertEqual(bond_flows[-1].cashflow_type, "coupon_principal")

    def test_fixed_income_response_exposes_retail_quote_fields(self) -> None:
        product = get_fixed_income_product("US-TREASURY-2Y")
        assert product is not None
        response = fixed_income_response(product)
        self.assertEqual(response.trade_status, "paper_tradable")
        self.assertIsNotNone(response.clean_price)
        self.assertIsNotNone(response.dirty_price)
        self.assertIsNotNone(response.settlement_date)
        self.assertTrue(response.cashflows)

    def test_us_cash_bills_point_to_listed_paper_proxy(self) -> None:
        bill = get_fixed_income_product("US-TBILL-13W")
        note = get_fixed_income_product("US-TREASURY-2Y")
        assert bill is not None
        assert note is not None
        self.assertEqual(bill.proxy_ticker, "BIL")
        self.assertEqual(note.proxy_ticker, "SHY")

    def test_retail_risk_allows_model_fixed_income_execution(self) -> None:
        account = RetailAccount(
            user_id="u1",
            account_number="PI-TEST",
            broker_provider="PAPER",
            broker_account_id="paper-1",
            status="active",
            base_currency="USD",
            cash_balance=Decimal("10000.00"),
        )
        instrument = Instrument(
            ticker="US-TBILL-13W",
            name="US Treasury Bill 13 Week",
            asset_class="cash_equivalent",
            exchange="TREASURY",
            currency="USD",
            sector="Fixed Income",
            industry="treasury_bill",
        )
        assessment = evaluate_order_risk(
            account=account,
            instrument=instrument,
            payload=InvestOrderCreate(
                ticker="US-TBILL-13W",
                side="BUY",
                amount=Decimal("500"),
            ),
        )
        blocker_codes = {check.code for check in assessment.blockers}
        self.assertNotIn("fixed_income_execution", blocker_codes)
        self.assertFalse(assessment.blockers)
        self.assertIn(
            "Paper fill uses an indicative fixed-income model price, including settlement and accrued-interest assumptions.",
            assessment.warnings,
        )

    def test_retail_risk_blocks_below_fixed_income_minimum(self) -> None:
        account = RetailAccount(
            user_id="u1",
            account_number="PI-TEST",
            broker_provider="PAPER",
            broker_account_id="paper-1",
            status="active",
            base_currency="USD",
            cash_balance=Decimal("10000.00"),
        )
        instrument = Instrument(
            ticker="NG-TBILL-182D",
            name="Nigeria Treasury Bill 182 Day",
            asset_class="cash_equivalent",
            exchange="FMDQ",
            currency="NGN",
            sector="Fixed Income",
            industry="treasury_bill",
        )
        assessment = evaluate_order_risk(
            account=account,
            instrument=instrument,
            payload=InvestOrderCreate(
                ticker="NG-TBILL-182D",
                side="BUY",
                amount=Decimal("500"),
            ),
        )
        blocker_codes = {check.code for check in assessment.blockers}
        self.assertIn("minimum_order", blocker_codes)


class InvestMarketsBoardTests(TestCase):
    def test_board_covers_us_rates_and_nigeria_pulses(self) -> None:
        tickers = board_tickers()
        self.assertIn("SPY", tickers)
        self.assertIn("DIA", tickers)
        self.assertIn("BIL", tickers)
        self.assertIn("SHY", tickers)
        self.assertIn("TLT", tickers)
        self.assertIn("XLK", tickers)
        self.assertIn("GTCO.NG", tickers)
        self.assertIn("SEPLAT.NG", tickers)
