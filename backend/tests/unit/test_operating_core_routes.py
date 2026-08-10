from unittest import TestCase

from app.main import app


class OperatingCoreRouteTests(TestCase):
    def test_auth_route_is_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/auth/me", paths)
        self.assertIn("get", paths["/api/auth/me"])

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
        self.assertIn("/api/ticker-intelligence/ai/draft", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ai/draft"])
        self.assertIn("/api/ticker-intelligence/memos", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/memos"])
        self.assertIn("/api/ticker-intelligence/memos/{memo_id}", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/memos/{memo_id}"])
        self.assertIn("/api/ticker-intelligence/ml/prices/yahoo/backfill", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/prices/yahoo/backfill"])
        self.assertIn("/api/ticker-intelligence/ml/pipeline/run", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/pipeline/run"])
        self.assertIn("/api/ticker-intelligence/ml/labels", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/labels"])
        self.assertIn("/api/ticker-intelligence/ml/features/price", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/features/price"])
        self.assertIn("/api/ticker-intelligence/ml/regime/hmm", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/regime/hmm"])
        self.assertIn("/api/ticker-intelligence/ml/regime/latest", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/ml/regime/latest"])
        self.assertIn("/api/ticker-intelligence/ml/backtests/factor", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/backtests/factor"])
        self.assertIn("/api/ticker-intelligence/ml/train", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/train"])
        self.assertIn("/api/ticker-intelligence/ml/predict", paths)
        self.assertIn("post", paths["/api/ticker-intelligence/ml/predict"])
        self.assertIn("/api/ticker-intelligence/ml/models", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/ml/models"])
        self.assertIn("/api/ticker-intelligence/ml/report/{ticker}", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/ml/report/{ticker}"])
        self.assertIn("/api/ticker-intelligence/ml/dataset/{ticker}", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/ml/dataset/{ticker}"])
        self.assertIn("/api/ticker-intelligence/{ticker}/prefill", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/{ticker}/prefill"])
        self.assertIn("/api/ticker-intelligence/{ticker}/memos", paths)
        self.assertIn("get", paths["/api/ticker-intelligence/{ticker}/memos"])

    def test_monthly_report_route_is_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/reports/monthly", paths)
        self.assertIn("get", paths["/api/reports/monthly"])

    def test_risk_centre_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/risk-centre/overview", paths)
        self.assertIn("get", paths["/api/risk-centre/overview"])
        self.assertIn("/api/risk-centre/snapshots", paths)
        self.assertIn("post", paths["/api/risk-centre/snapshots"])
        self.assertIn("/api/risk-centre/stress-tests", paths)
        self.assertIn("post", paths["/api/risk-centre/stress-tests"])
        self.assertIn("/api/risk-centre/pre-trade-check", paths)
        self.assertIn("post", paths["/api/risk-centre/pre-trade-check"])

    def test_strategy_pod_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/strategy-pods", paths)
        self.assertIn("get", paths["/api/strategy-pods"])
        self.assertIn("/api/strategy-pods/{code}", paths)
        self.assertIn("get", paths["/api/strategy-pods/{code}"])
        self.assertIn("patch", paths["/api/strategy-pods/{code}"])
        self.assertIn("/api/strategy-pods/{code}/snapshots", paths)
        self.assertIn("post", paths["/api/strategy-pods/{code}/snapshots"])
