from unittest import TestCase

from app.main import app


class OperatingCoreRouteTests(TestCase):
    def test_cash_ledger_history_has_dedicated_get_route(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/operating-core/cash-ledger/history", paths)
        self.assertIn("get", paths["/api/operating-core/cash-ledger/history"])

    def test_cash_ledger_collection_accepts_get_and_post(self) -> None:
        methods = app.openapi()["paths"]["/api/operating-core/cash-ledger"]

        self.assertIn("get", methods)
        self.assertIn("post", methods)

    def test_cash_ledger_movement_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/operating-core/cash-ledger/deposits", paths)
        self.assertIn("post", paths["/api/operating-core/cash-ledger/deposits"])
        self.assertIn("/api/operating-core/cash-ledger/withdrawals", paths)
        self.assertIn("post", paths["/api/operating-core/cash-ledger/withdrawals"])
        self.assertIn("/api/operating-core/cash-ledger/adjustments", paths)
        self.assertIn("post", paths["/api/operating-core/cash-ledger/adjustments"])

    def test_ticker_intelligence_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/ticker-intelligence/analyze", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/analyze"])
        self.assertIn("/api/ticker-intelligence/memos", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/memos"])
        self.assertIn("/api/ticker-intelligence/{ticker}/prefill", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/{ticker}/prefill"])
        self.assertIn("/api/ticker-intelligence/{ticker}/memos", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/{ticker}/memos"])
