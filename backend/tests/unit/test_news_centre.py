import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from app.main import app
from app.core.config import settings
from app.services.news import providers
from app.services.news.providers import NewsFetchResult, normalize_ticker
from app.services.realtime.events import news_poll_completed_event


class NewsCentreRouteTests(TestCase):
    def test_news_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]

        self.assertIn("/api/news/overview", paths)
        self.assertIn("get", paths["/api/news/overview"])
        self.assertIn("/api/news/poll", paths)
        self.assertIn("post", paths["/api/news/poll"])
        self.assertIn("/api/news/ticker/{ticker}/refresh", paths)
        self.assertIn("post", paths["/api/news/ticker/{ticker}/refresh"])

    def test_news_overview_exposes_pagination_params(self) -> None:
        operation = app.openapi()["paths"]["/api/news/overview"]["get"]
        parameters = {item["name"] for item in operation["parameters"]}

        self.assertIn("page", parameters)
        self.assertIn("page_size", parameters)


class NewsRetentionTests(TestCase):
    def test_news_retention_defaults_to_fifty_days(self) -> None:
        self.assertEqual(settings.news_retention_days, 50)


class NewsProviderTests(TestCase):
    def test_normalize_ticker_respects_market_hint(self) -> None:
        self.assertEqual(normalize_ticker("gtco", "NG"), "GTCO.NG")
        self.assertEqual(normalize_ticker("GTCO.NG", "NG"), "GTCO.NG")
        self.assertEqual(normalize_ticker("aapl", "US"), "AAPL")

    def test_us_current_poll_does_not_call_ngn_providers(self) -> None:
        with (
            patch.object(
                providers,
                "_fetch_tiingo_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as tiingo_news,
            patch.object(
                providers,
                "_fetch_fmp_latest_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as fmp_news,
            patch.object(
                providers,
                "_fetch_ngn_disclosures",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as ngn_disclosures,
            patch.object(
                providers,
                "_fetch_ngn_company_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as ngn_company,
        ):
            result = asyncio.run(
                providers.fetch_current_news(
                    jurisdictions=["US"],
                    us_tickers=["AAPL"],
                    ng_tickers=["GTCO.NG"],
                )
            )

        self.assertEqual(result.calls, 2)
        self.assertEqual(
            result.provider_plan,
            ["US:tiingo:latest", "US:fmp:stock-latest"],
        )
        tiingo_news.assert_awaited_once_with(tickers=[])
        fmp_news.assert_awaited_once_with(
            include_general=False,
            include_press_releases=False,
        )
        ngn_disclosures.assert_not_called()
        ngn_company.assert_not_called()

    def test_ng_current_poll_does_not_call_us_providers(self) -> None:
        with (
            patch.object(
                providers,
                "_fetch_tiingo_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as tiingo_news,
            patch.object(
                providers,
                "_fetch_fmp_latest_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as fmp_news,
            patch.object(
                providers,
                "_fetch_ngn_disclosures",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as ngn_disclosures,
            patch.object(
                providers,
                "_fetch_ngn_company_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as ngn_company,
        ):
            result = asyncio.run(
                providers.fetch_current_news(
                    jurisdictions=["NG"],
                    us_tickers=["AAPL"],
                    ng_tickers=["GTCO.NG"],
                )
            )

        self.assertEqual(result.calls, 1)
        self.assertEqual(result.provider_plan, ["NG:ngnmarket:disclosures"])
        ngn_disclosures.assert_awaited_once_with(symbol=None)
        tiingo_news.assert_not_called()
        fmp_news.assert_not_called()
        ngn_company.assert_not_called()

    def test_current_poll_does_not_include_ticker_batches_by_default(self) -> None:
        with (
            patch.object(
                providers,
                "_fetch_tiingo_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ),
            patch.object(
                providers,
                "_fetch_fmp_latest_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ),
            patch.object(
                providers,
                "_fetch_ngn_disclosures",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ),
            patch.object(
                providers,
                "_fetch_ngn_company_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as ngn_company,
        ):
            result = asyncio.run(
                providers.fetch_current_news(
                    jurisdictions=["US", "NG"],
                    us_tickers=["AAPL"],
                    ng_tickers=["GTCO.NG"],
                )
            )

        self.assertEqual(result.calls, 3)
        self.assertEqual(
            result.provider_plan,
            [
                "US:tiingo:latest",
                "US:fmp:stock-latest",
                "NG:ngnmarket:disclosures",
            ],
        )
        ngn_company.assert_not_called()


class NewsRealtimeEventTests(TestCase):
    def test_news_poll_completed_event_shape(self) -> None:
        event = news_poll_completed_event(
            run_id="run-1",
            status="completed",
            trigger="scheduled",
            target_scope="current",
            target_key="US",
            provider_calls=4,
            items_seen=12,
            items_created=3,
            items_updated=1,
            cache_hit=True,
        )

        self.assertEqual(event["type"], "news.poll_completed")
        self.assertIsNone(event["owner_user_id"])
        self.assertEqual(event["payload"]["target_key"], "US")
        self.assertTrue(event["payload"]["cache_hit"])
        self.assertEqual(event["payload"]["items_created"], 3)
        self.assertEqual(event["payload"]["provider_calls"], 4)
