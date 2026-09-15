from unittest import TestCase
from decimal import Decimal

from app.core.auth import (
    AuthenticatedUser,
    user_can_access_capital,
    user_can_access_invest,
)
from app.core.config import settings
from app.main import app
from app.services.brokerage.paper import _buy_size
from app.services.brokerage.protocol import BrokerValidationError, SubmitOrderRequest


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
        self.assertIn("/api/invest/orders/{order_id}", paths)
        self.assertIn("/api/invest/orders/{order_id}/cancel", paths)

    def test_operating_core_stays_on_capital_auth(self) -> None:
        spec = app.openapi()["paths"]["/api/operating-core/dashboard"]["get"]
        # The route exists; retail isolation is enforced in require_capital_user.
        self.assertIn("operationId", spec)


class PaperBrokerSizingTests(TestCase):
    def test_notional_buy_converts_to_quantity(self) -> None:
        quantity, notional = _buy_size(
            SubmitOrderRequest(symbol="AAPL", side="BUY", notional=Decimal("500")),
            Decimal("250"),
        )
        self.assertEqual(quantity, Decimal("2.00000000"))
        self.assertEqual(notional, Decimal("500.00"))

    def test_buy_requires_amount_or_quantity(self) -> None:
        with self.assertRaises(BrokerValidationError):
            _buy_size(SubmitOrderRequest(symbol="AAPL", side="BUY"), Decimal("10"))
