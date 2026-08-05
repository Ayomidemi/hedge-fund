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
