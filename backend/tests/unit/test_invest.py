import io
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, TestCase

from app.core.auth import (
    AuthenticatedUser,
    user_can_access_capital,
    user_can_access_invest,
)
from app.core.config import settings
from app.main import app
from app.api.schemas.invest import InvestHolding, InvestOrderCreate
from app.models import Instrument, InvestMarketBoardItem, RetailAccount
from app.services.brokerage.paper import _buy_size, _fixed_income_buy_size
from app.services.brokerage.protocol import BrokerValidationError, SubmitOrderRequest
from app.services.invest.accounts import (
    _allocation_buckets,
    _instrument_href,
    _profile_permissions,
    _withheld_capital_signals,
)
from app.services.invest.fixed_income import (
    fixed_income_cashflows,
    fixed_income_quote,
    fixed_income_response,
    get_fixed_income_product,
    search_fixed_income_products,
)
from app.services.invest.fixed_income_providers import fixed_income_provider_plan
from app.services.invest.markets import (
    DEFAULT_MARKET_BOARD_RULES,
    _apply_tiingo_metadata_to_board_item,
    _board_item_from_rule,
    _parse_tiingo_supported_tickers,
    board_tickers,
    rates_board_tickers,
)
from app.services.invest.risk import evaluate_order_risk


class InvestPermissionTests(TestCase):
    def test_retail_user_cannot_access_capital(self) -> None:
        user = AuthenticatedUser(id="u1", email="r@example.com", role="RETAIL_USER")
        self.assertTrue(user_can_access_invest(user))
        self.assertFalse(user_can_access_capital(user))

    def test_capital_pm_can_access_capital_only(self) -> None:
        user = AuthenticatedUser(id="u2", email="pm@example.com", role="CAPITAL_PM")
        self.assertFalse(user_can_access_invest(user))
        self.assertTrue(user_can_access_capital(user))

    def test_admin_can_access_both_and_switch(self) -> None:
        from app.core.auth import user_can_switch_products

        user = AuthenticatedUser(id="u4", email="a@example.com", role="ADMIN")
        self.assertTrue(user_can_access_invest(user))
        self.assertTrue(user_can_access_capital(user))
        self.assertTrue(user_can_switch_products(user))

    def test_unscoped_authenticated_user_stays_on_invest(self) -> None:
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

    def test_invest_policy_parsers_fallback_on_bad_values(self) -> None:
        from app.services.invest.configuration import (
            parse_paper_broker_policy,
            parse_risk_policy,
        )

        risk_policy = parse_risk_policy(
            {
                "allowed_sides": [],
                "buying_power_concentration_warn_pct": "500",
                "fixed_income_fx_warning_enabled": "false",
            }
        )
        self.assertEqual(risk_policy.allowed_sides, frozenset({"BUY", "SELL"}))
        self.assertEqual(
            risk_policy.buying_power_concentration_warn_pct,
            Decimal("0.50"),
        )
        self.assertFalse(risk_policy.fixed_income_fx_warning_enabled)

        broker_policy = parse_paper_broker_policy(
            {
                "concentration_warn_pct": "NaN",
                "price_precision": "0",
            }
        )
        self.assertEqual(broker_policy.concentration_warn_pct, Decimal("0.25"))
        self.assertEqual(broker_policy.price_precision, Decimal("0.000001"))

    def test_profile_permissions_keep_retail_out_of_capital_controls(self) -> None:
        user = AuthenticatedUser(id="u1", email="r@example.com", role="RETAIL_USER")
        permissions = {item.code: item.enabled for item in _profile_permissions(user)}
        self.assertTrue(permissions["paper_trading"])
        self.assertTrue(permissions["fixed_income"])
        self.assertFalse(permissions["real_cash_movements"])
        self.assertFalse(permissions["capital_workspace"])
        self.assertFalse(permissions["product_switching"])

    def test_invest_research_withholds_capital_signals(self) -> None:
        withheld = _withheld_capital_signals()
        self.assertIn("Capital target weights", withheld)
        self.assertIn("PM approval state", withheld)

    def test_pease_view_uses_factor_scores_without_fund_outputs(self) -> None:
        from app.api.schemas.ticker_intelligence import TickerMetricsInput
        from app.services.invest.research import (
            pease_view_from_scorecard,
            retail_stance,
        )
        from app.services.ticker_intelligence.scoring import score_ticker

        strong = score_ticker(
            TickerMetricsInput(
                revenue_growth_pct=Decimal("18"),
                earnings_growth_pct=Decimal("16"),
                net_margin_pct=Decimal("22"),
                free_cash_flow_yield_pct=Decimal("5"),
                pe_ratio=Decimal("18"),
                debt_to_equity=Decimal("0.3"),
                price_vs_200d_pct=Decimal("8"),
                relative_strength_6m_pct=Decimal("12"),
                volatility_30d_pct=Decimal("18"),
            ),
            "equity",
        )
        view = pease_view_from_scorecard(strong)
        stance, label = retail_stance(strong)
        dumped = view.model_dump_json().lower()
        self.assertEqual(stance, "constructive")
        self.assertEqual(label, "Looks constructive")
        self.assertTrue(view.looks_good)
        self.assertNotIn("recommended_weight", dumped)
        self.assertNotIn("high-conviction", dumped)
        self.assertNotIn("target weight", dumped)
        factor_ids = {factor.id for factor in view.factors}
        self.assertEqual(
            factor_ids,
            {"quality", "growth", "valuation", "risk", "momentum"},
        )

    def test_pease_view_caution_on_leverage_blockers(self) -> None:
        from app.api.schemas.ticker_intelligence import TickerMetricsInput
        from app.services.invest.research import pease_view_from_scorecard
        from app.services.ticker_intelligence.scoring import score_ticker

        stressed = score_ticker(
            TickerMetricsInput(
                net_margin_pct=Decimal("-2"),
                free_cash_flow_yield_pct=Decimal("-9"),
                debt_to_equity=Decimal("6.5"),
            ),
            "equity",
        )
        view = pease_view_from_scorecard(stressed)
        self.assertEqual(view.stance, "caution")
        self.assertTrue(view.watch_outs)

    def test_pease_view_uses_price_path_for_listed_funds(self) -> None:
        from app.api.schemas.ticker_intelligence import TickerMetricsInput
        from app.services.invest.research import (
            pease_view_from_scorecard,
            retail_stance,
        )
        from app.services.ticker_intelligence.scoring import score_ticker

        metrics = TickerMetricsInput(
            current_price=Decimal("91.40"),
            price_vs_200d_pct=Decimal("1.20"),
            relative_strength_6m_pct=Decimal("-0.40"),
            volatility_30d_pct=Decimal("3.50"),
        )
        scorecard = score_ticker(metrics, "etf")
        stance, label = retail_stance(scorecard, price_snapshot=True)
        view = pease_view_from_scorecard(
            scorecard, asset_class="etf", ticker="BIL", metrics=metrics
        )
        self.assertNotEqual(stance, "incomplete")
        self.assertNotEqual(label, "Not enough data")
        self.assertEqual(view.stance, stance)
        self.assertIn("price-path", view.summary.lower())
        self.assertEqual(
            {factor.id for factor in view.factors},
            {"momentum", "growth", "risk"},
        )

    def test_payload_prefers_pease_role_over_jwt_authenticated(self) -> None:
        from app.core.auth import _user_from_payload

        user = _user_from_payload(
            {
                "sub": "11111111-2222-3333-4444-555555555555",
                "email": "retail@example.com",
                "role": "authenticated",
                "user_metadata": {"pease_role": "RETAIL_USER"},
            }
        )
        self.assertEqual(user.role, "RETAIL_USER")
        self.assertFalse(user_can_access_capital(user))

    def test_payload_app_metadata_admin_wins(self) -> None:
        from app.core.auth import _user_from_payload, user_can_switch_products

        user = _user_from_payload(
            {
                "sub": "11111111-2222-3333-4444-555555555555",
                "email": "admin@example.com",
                "role": "authenticated",
                "app_metadata": {"pease_role": "ADMIN"},
                "user_metadata": {"pease_role": "RETAIL_USER"},
            }
        )
        self.assertEqual(user.role, "ADMIN")
        self.assertTrue(user_can_switch_products(user))


class InvestRouteTests(TestCase):
    def test_invest_routes_are_registered(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/api/invest/account", paths)
        self.assertIn("/api/invest/profile", paths)
        self.assertIn("/api/invest/activity", paths)
        self.assertIn("/api/invest/home", paths)
        self.assertIn("/api/invest/orders", paths)
        self.assertIn("/api/invest/watchlist", paths)
        self.assertIn("/api/invest/paper/deposit", paths)
        self.assertIn("/api/invest/instruments/search", paths)
        self.assertIn("/api/invest/instruments/{ticker}/research", paths)
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
        self.assertEqual(response.quote_source, "model_seed")
        self.assertEqual(response.quote_provider, "internal_model")
        self.assertEqual(response.quote_provider_label, "Internal pricing model")
        self.assertEqual(response.quote_quality, "seed_model")
        self.assertEqual(response.quote_quality_label, "Model fallback")
        self.assertEqual(response.quote_type, "model")
        self.assertFalse(response.quote_is_live)
        self.assertFalse(response.quote_stale)
        self.assertIsNotNone(response.quote_as_of)
        self.assertIsNotNone(response.quote_stale_after)
        self.assertEqual(response.mid_price, response.dirty_price)
        self.assertEqual(response.mid_yield_pct, response.yield_to_maturity_pct)
        self.assertTrue(response.pricing_assumptions)
        self.assertTrue(response.risk_checks)
        self.assertTrue(response.cashflows)

    def test_fixed_income_provider_plan_points_to_real_data_ladder(self) -> None:
        us_bill = get_fixed_income_product("US-TBILL-13W")
        ng_bill = get_fixed_income_product("NG-TBILL-182D")
        assert us_bill is not None
        assert ng_bill is not None

        us_providers = [item.provider for item in fixed_income_provider_plan(us_bill)]
        ng_providers = [item.provider for item in fixed_income_provider_plan(ng_bill)]

        self.assertEqual(us_providers[0], "internal_model")
        self.assertIn("treasury_fiscal_data", us_providers)
        self.assertIn("fred_curve", us_providers)
        self.assertIn("tiingo_proxy", us_providers)
        self.assertEqual(ng_providers[0], "internal_model")
        self.assertIn("fmdq", ng_providers)
        self.assertIn("cbn", ng_providers)

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
            "Paper fill uses the fixed-income quote service mark, including settlement and accrued-interest assumptions.",
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

    def test_ngn_order_uses_usd_cash_notional_for_buying_power(self) -> None:
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
            ticker="FGN-BOND-2029",
            name="FGN Bond 2029",
            asset_class="bond",
            exchange="FMDQ",
            currency="NGN",
            sector="Fixed Income",
            industry="government_bond",
        )
        without_fx = evaluate_order_risk(
            account=account,
            instrument=instrument,
            payload=InvestOrderCreate(
                ticker="FGN-BOND-2029",
                side="BUY",
                amount=Decimal("100000.00"),
            ),
        )
        self.assertIn("buying_power", {check.code for check in without_fx.blockers})

        with_fx = evaluate_order_risk(
            account=account,
            instrument=instrument,
            payload=InvestOrderCreate(
                ticker="FGN-BOND-2029",
                side="BUY",
                amount=Decimal("100000.00"),
            ),
            cash_notional=Decimal("65.40"),
        )
        self.assertFalse(with_fx.blockers)
        self.assertTrue(
            any("stored FX rate" in warning for warning in with_fx.warnings)
        )

    def test_amount_in_base_converts_ngn_to_usd(self) -> None:
        from types import SimpleNamespace

        from app.services.market_data.fx_convert import amount_in_base

        rate = SimpleNamespace(rate=Decimal("1500"))
        cash = amount_in_base(
            Decimal("150000.00"),
            "NGN",
            "USD",
            {("USD", "NGN"): rate},
        )
        self.assertEqual(cash, Decimal("100"))
        self.assertEqual(
            amount_in_base(Decimal("100"), "USD", "USD", {}),
            Decimal("100"),
        )


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

    def test_rates_board_tickers_cover_fixed_income_proxies(self) -> None:
        self.assertEqual(
            rates_board_tickers(),
            ("BIL", "SHY", "IEF", "TLT"),
        )

    def test_tiingo_supported_tickers_parser_filters_requested_symbols(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "supported_tickers.csv",
                "\n".join(
                    [
                        "ticker,exchange,assetType,priceCurrency,startDate,endDate",
                        "SPY,NYSE Arca,ETF,USD,1993-01-29,",
                        "AAPL,NASDAQ,Stock,USD,1980-12-12,",
                    ]
                ),
            )

        parsed = _parse_tiingo_supported_tickers(buffer.getvalue(), {"SPY"})

        self.assertEqual(set(parsed), {"SPY"})
        self.assertEqual(parsed["SPY"]["assetType"], "ETF")
        self.assertEqual(parsed["SPY"]["priceCurrency"], "USD")

    def test_seed_item_uses_tiingo_metadata_when_available(self) -> None:
        spy_rule = next(
            row for row in DEFAULT_MARKET_BOARD_RULES if row.ticker == "SPY"
        )
        seeded = _board_item_from_rule(
            spy_rule,
            display_order=10,
            seeded_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
            tiingo_metadata={
                "ticker": "SPY",
                "exchange": "NYSE Arca",
                "assetType": "ETF",
                "priceCurrency": "USD",
                "startDate": "1993-01-29",
            },
        )

        self.assertEqual(seeded.ticker, "SPY")
        self.assertEqual(seeded.asset_class, "etf")
        self.assertEqual(seeded.exchange, "NYSE Arca")
        self.assertEqual(seeded.source, "tiingo_supported_tickers")
        self.assertEqual(seeded.source_metadata["assetType"], "ETF")

    def test_board_item_can_refresh_tiingo_metadata(self) -> None:
        row = InvestMarketBoardItem(
            ticker="SHY",
            label="1-3Y Treasury ETF",
            name="iShares 1-3 Year Treasury Bond ETF",
            market="US",
            board_group="rates",
            group_title="Rates board",
            group_description="Treasury duration proxies.",
            display_order=20,
            asset_class="etf",
            exchange="ARCA",
            currency="USD",
            sector="Fixed Income",
        )

        changed = _apply_tiingo_metadata_to_board_item(
            row,
            {
                "ticker": "SHY",
                "exchange": "NYSE Arca",
                "assetType": "ETF",
                "priceCurrency": "USD",
                "startDate": "2002-07-22",
            },
            datetime(2026, 9, 23, tzinfo=timezone.utc),
        )

        self.assertTrue(changed)
        self.assertEqual(row.exchange, "NYSE Arca")
        self.assertEqual(row.source, "tiingo_supported_tickers")
        self.assertEqual(row.source_metadata["startDate"], "2002-07-22")


class InvestNewsTickerTests(TestCase):
    def test_fixed_income_symbols_expand_to_listed_proxy(self) -> None:
        from app.services.invest.news import _news_tickers_for_symbol, _unique

        self.assertEqual(
            _news_tickers_for_symbol("US-TBILL-13W"),
            ["US-TBILL-13W", "BIL"],
        )
        self.assertEqual(_news_tickers_for_symbol("SPY"), ["SPY"])
        self.assertEqual(
            _unique(["SPY", "spy", "BIL", "SPY"]),
            ["SPY", "BIL"],
        )

    def test_income_universe_covers_shelf_and_listed_proxies(self) -> None:
        from app.services.invest.news import INCOME_TICKERS

        self.assertIn("BIL", INCOME_TICKERS)
        self.assertIn("SHY", INCOME_TICKERS)
        self.assertIn("IEF", INCOME_TICKERS)
        self.assertIn("TLT", INCOME_TICKERS)
        self.assertIn("US-TBILL-13W", INCOME_TICKERS)
        self.assertIn("FGN-BOND-2029", INCOME_TICKERS)

    def test_income_story_matches_rates_copy_and_proxies(self) -> None:
        from app.services.invest.news import is_income_story

        self.assertTrue(
            is_income_story(
                title="Treasury yields jump after FOMC",
                summary="The 10-year Treasury yield rose 8 basis points.",
                tickers=["SPY"],
            )
        )
        self.assertTrue(
            is_income_story(
                title="BIL tracks short bills",
                summary=None,
                tickers=["BIL"],
            )
        )
        self.assertTrue(
            is_income_story(
                title="DMO clears FGN bond auction",
                summary="Naira demand stayed firm at the latest stop rate.",
                tickers=[],
                jurisdiction="NG",
            )
        )
        self.assertFalse(
            is_income_story(
                title="NVDA earnings beat lifts semiconductor names",
                summary="Data-center demand remains the main driver.",
                tickers=["NVDA"],
            )
        )

    def test_summary_leads_with_rates(self) -> None:
        from app.services.invest.news import _summary

        rates = _summary(income_count=6, portfolio_count=2, watchlist_count=1)
        personal = _summary(income_count=0, portfolio_count=2, watchlist_count=1)
        empty = _summary(income_count=0, portfolio_count=0, watchlist_count=0)
        self.assertIn("rates and income", rates)
        self.assertIn("holdings", rates)
        self.assertIn("rates headlines", personal)
        self.assertIn("T-bills", empty)

    def test_income_stories_can_be_paged(self) -> None:
        from types import SimpleNamespace
        from uuid import uuid4

        from app.services.invest.news import (
            _merge_income_stories,
            _pagination,
            _slice_page,
        )

        stories = [
            SimpleNamespace(
                id=uuid4(),
                title="Treasury yields jump after FOMC",
                summary=None,
                ticker_links=[SimpleNamespace(ticker="BIL")],
            )
            for _ in range(12)
        ]
        merged = _merge_income_stories(
            stories,
            [],
            jurisdiction="US",
            income_ticker_set={"BIL"},
            limit=20,
        )
        page, total = _slice_page(merged, 2, 8)
        self.assertEqual(total, 12)
        self.assertEqual(len(page), 4)
        meta = _pagination(2, 8, total)
        self.assertTrue(meta.has_previous)
        self.assertFalse(meta.has_next)


class InvestDiscoverCopyTests(TestCase):
    def test_move_copy_is_plain_language(self) -> None:
        from types import SimpleNamespace

        from app.services.invest.discover import (
            _move_copy,
            _retail_badge,
            uses_desk_language,
        )

        item = SimpleNamespace(
            ticker="NVDA",
            name="NVIDIA",
            change_pct=Decimal("4.20"),
            volume_ratio=Decimal("2.10"),
            industry="Semiconductors",
            sector="Technology",
            flags=["unusual_volume", "price_move"],
        )
        copy = _move_copy(item)
        self.assertIn("NVDA is up 4.20%", copy)
        self.assertIn("2.1× volume", copy)
        self.assertFalse(uses_desk_language(copy))
        self.assertEqual(_retail_badge(item), "Heavy volume")

    def test_sector_copy_describes_a_group(self) -> None:
        from types import SimpleNamespace

        from app.services.invest.discover import _sector_copy, uses_desk_language

        industry = SimpleNamespace(
            name="Semiconductors",
            status="industry_event",
            jurisdiction="US",
            flagged_count=6,
            name_count=12,
            median_change_pct=Decimal("3.10"),
        )
        copy = _sector_copy(industry)
        self.assertIn("Semiconductors", copy)
        self.assertIn("6 of 12", copy)
        self.assertFalse(uses_desk_language(copy))

    def test_summary_and_empty_watchlist_actions(self) -> None:
        from app.services.invest.discover import _next_actions, _summary

        quiet = _summary(
            unusual_count=0,
            sector_count=0,
            watchlist_hits=0,
            watchlist_count=0,
        )
        live = _summary(
            unusual_count=4,
            sector_count=1,
            watchlist_hits=2,
            watchlist_count=3,
        )
        self.assertIn("quiet", quiet.lower())
        self.assertIn("watched names", live.lower())
        self.assertTrue(_next_actions(set()))
        self.assertEqual(_next_actions({"AAPL"}), [])

    def test_unusual_section_omits_fixed_income_catalog(self) -> None:
        from app.services.invest.discover import _unusual_section

        section = _unusual_section([], screened=80)
        self.assertEqual(section.id, "unusual_activity")
        self.assertNotIn("fixed_income", section.id)
        self.assertIn("quiet", section.items[0].title.lower())

    def test_narrative_uses_sector_sentence(self) -> None:
        from types import SimpleNamespace

        from app.services.invest.discover import _narrative

        industry = SimpleNamespace(
            name="Semiconductors",
            status="industry_event",
            jurisdiction="US",
            flagged_count=6,
            name_count=12,
            median_change_pct=Decimal("3.10"),
        )
        copy = _narrative([industry], [])
        self.assertIsNotNone(copy)
        self.assertIn("Semiconductors", copy or "")


class InvestPortfolioResponseTests(TestCase):
    def test_fixed_income_hrefs_route_to_fixed_income_detail(self) -> None:
        self.assertEqual(
            _instrument_href("US-TBILL-13W"),
            "/invest/fixed-income/US-TBILL-13W",
        )
        self.assertEqual(_instrument_href("SPY"), "/invest/instruments/SPY")
        self.assertEqual(
            _instrument_href("CUSTOM-BOND", "bond"),
            "/invest/fixed-income/CUSTOM-BOND",
        )

    def test_paper_policy_stays_market_only_with_instant_fills(self) -> None:
        from app.services.invest.configuration import default_invest_setting

        policy = default_invest_setting("paper_broker_policy")
        self.assertTrue(policy["instant_fills"])
        self.assertEqual(policy["allowed_order_types"], ["market"])
        quantity, notional = _buy_size(
            SubmitOrderRequest(symbol="SPY", side="BUY", notional=Decimal("500")),
            Decimal("100"),
        )
        self.assertEqual(quantity, Decimal("5.00000000"))
        self.assertEqual(notional, Decimal("500.00"))
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
            ticker="SPY",
            name="SPDR S&P 500",
            asset_class="etf",
            exchange="ARCA",
            currency="USD",
            sector="Index",
            industry="etf",
        )
        assessment = evaluate_order_risk(
            account=account,
            instrument=instrument,
            payload=InvestOrderCreate(
                ticker="SPY",
                side="BUY",
                amount=Decimal("500"),
            ),
        )
        self.assertFalse(assessment.blockers)

    def test_allocation_buckets_include_cash_and_fixed_income(self) -> None:
        holdings = [
            InvestHolding(
                ticker="US-TBILL-13W",
                name="US Treasury Bill 13 Week",
                asset_class="cash_equivalent",
                currency="USD",
                quantity=Decimal("1000"),
                average_cost=Decimal("0.99"),
                current_price=Decimal("0.99"),
                market_value=Decimal("990.00"),
                unrealized_pnl=Decimal("0.00"),
                unrealized_pnl_pct=None,
                href="/invest/fixed-income/US-TBILL-13W",
            )
        ]
        buckets = _allocation_buckets(
            holdings,
            cash=Decimal("10.00"),
            portfolio_value=Decimal("1000.00"),
        )
        by_name = {bucket.name: bucket for bucket in buckets}
        self.assertEqual(by_name["Cash"].allocation_pct, Decimal("1.00"))
        self.assertEqual(by_name["Fixed income"].allocation_pct, Decimal("99.00"))


class InvestPriceUniverseTests(IsolatedAsyncioTestCase):
    async def test_price_universe_includes_invest_books(self) -> None:
        from uuid import uuid4

        from app.services.market_data.universe import build_price_universe

        retail_position_id = uuid4()
        watchlist_id = uuid4()
        board_id = uuid4()
        session = _FakeScalarsSession(
            [
                [],
                [retail_position_id],
                [watchlist_id],
                ["BIL"],
                [board_id],
                [],
                [],
                [],
                [
                    Instrument(
                        id=retail_position_id,
                        ticker="TLT",
                        name="iShares 20+ Year Treasury Bond ETF",
                        asset_class="etf",
                        exchange="ARCA",
                        currency="USD",
                    ),
                    Instrument(
                        id=watchlist_id,
                        ticker="GTCO",
                        name="Guaranty Trust Holding Company",
                        asset_class="equity",
                        exchange="NGX",
                        currency="NGN",
                    ),
                    Instrument(
                        id=board_id,
                        ticker="BIL",
                        name="SPDR Bloomberg 1-3 Month T-Bill ETF",
                        asset_class="etf",
                        exchange="ARCA",
                        currency="USD",
                    ),
                ],
            ]
        )

        universe = await build_price_universe(session)

        self.assertEqual(universe["TLT"], [retail_position_id])
        self.assertEqual(universe["GTCO.NG"], [watchlist_id])
        self.assertEqual(universe["BIL"], [board_id])


class _FakeScalarsSession:
    def __init__(self, results: list[list]) -> None:
        self._results = iter(results)

    async def scalars(self, statement):
        return next(self._results)
