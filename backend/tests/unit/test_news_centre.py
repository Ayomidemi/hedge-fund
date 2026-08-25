import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from uuid import uuid4

from app.main import app
from app.core.config import Settings, settings
from app.services.news import centre, providers
from app.services.news.providers import NewsFetchResult, ProviderNewsItem, normalize_ticker
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
        self.assertIn("/api/news/items/{news_item_id}/star", paths)
        self.assertIn("put", paths["/api/news/items/{news_item_id}/star"])

    def test_news_overview_exposes_pagination_params(self) -> None:
        operation = app.openapi()["paths"]["/api/news/overview"]["get"]
        parameters = {item["name"] for item in operation["parameters"]}

        self.assertIn("page", parameters)
        self.assertIn("page_size", parameters)
        self.assertIn("ticker_page", parameters)
        self.assertIn("ticker_page_size", parameters)


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

        self.assertEqual(result.calls, 1)
        self.assertEqual(result.provider_plan, ["US:tiingo:latest"])
        tiingo_news.assert_awaited_once_with(tickers=[])
        fmp_news.assert_not_called()
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
            ) as fmp_news,
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

        self.assertEqual(result.calls, 2)
        self.assertEqual(
            result.provider_plan,
            [
                "US:tiingo:latest",
                "NG:ngnmarket:disclosures",
            ],
        )
        ngn_company.assert_not_called()
        fmp_news.assert_not_called()

    def test_us_ticker_refresh_does_not_call_fmp(self) -> None:
        with (
            patch.object(
                providers,
                "_fetch_tiingo_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as tiingo_news,
            patch.object(
                providers,
                "_fetch_fmp_ticker_news",
                new=AsyncMock(return_value=NewsFetchResult(calls=1)),
            ) as fmp_news,
        ):
            result = asyncio.run(providers.fetch_news_for_ticker("SCGLY", market="US"))

        self.assertIn("US:tiingo:ticker:SCGLY", result.provider_plan)
        tiingo_news.assert_awaited_once_with(tickers=["SCGLY"])
        fmp_news.assert_not_called()
        self.assertFalse(any("fmp" in label for label in result.provider_plan))


class NewsUpsertBatchTests(TestCase):
    def test_prepare_provider_items_dedupes_and_drops_empty_titles(self) -> None:
        items = [
            ProviderNewsItem(
                provider="tiingo",
                provider_id="1",
                title="  First ",
                tickers=("AAPL",),
            ),
            ProviderNewsItem(
                provider="tiingo",
                provider_id="1",
                title="Second",
                tickers=("MSFT",),
            ),
            ProviderNewsItem(
                provider="tiingo",
                provider_id="2",
                title="   ",
                tickers=("TSLA",),
            ),
        ]

        prepared = centre._prepare_provider_items(items)

        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0].title, "Second")
        self.assertEqual(prepared[0].tickers, ("MSFT",))

    def test_news_item_values_clip_ids_and_urls(self) -> None:
        item = ProviderNewsItem(
            provider="tiingo",
            provider_id="x" * 600,
            title=" Clip me ",
            url="https://example.com/" + ("a" * 3000),
            source_name="S" * 300,
            raw_payload={"id": 1},
        )

        values = centre._news_item_values(item, news_item_id=uuid4())

        self.assertEqual(values["title"], "Clip me")
        self.assertEqual(len(values["provider_id"]), 512)
        self.assertEqual(len(values["url"]), 2048)
        self.assertEqual(len(values["source_name"]), 255)
        self.assertEqual(values["raw_payload"], {"id": 1})

    def test_upsert_chunks_large_batches(self) -> None:
        items = [
            ProviderNewsItem(
                provider="tiingo",
                provider_id=str(index),
                title=f"Story {index}",
            )
            for index in range(centre.NEWS_UPSERT_BATCH_SIZE + 5)
        ]
        chunk = AsyncMock(return_value=(2, 1))

        with patch.object(centre, "_upsert_provider_item_chunk", new=chunk):
            created, updated = asyncio.run(
                centre._upsert_provider_items(AsyncMock(), items)
            )

        self.assertEqual(chunk.await_count, 2)
        self.assertEqual(created, 4)
        self.assertEqual(updated, 2)


class NewsPollIntervalTests(TestCase):
    def test_news_poll_interval_defaults_to_sixty_seconds(self) -> None:
        self.assertEqual(
            Settings.model_fields["hf_news_poll_interval_seconds"].default,
            60,
        )
        self.assertGreaterEqual(settings.news_poll_interval_seconds, 30)


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
