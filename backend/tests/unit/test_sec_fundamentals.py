from decimal import Decimal
from unittest import TestCase

from app.services.ticker_intelligence.sec_fundamentals import calculate_sec_fundamentals


class SecFundamentalsTests(TestCase):
    def test_calculates_fundamentals_from_companyfacts(self) -> None:
        companyfacts = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {
                            "USD": [
                                _annual_fact("2024-12-31", "2025-02-01", 1000),
                                _annual_fact("2025-12-31", "2026-02-01", 1200),
                            ]
                        }
                    },
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                _annual_fact("2024-12-31", "2025-02-01", 100),
                                _annual_fact("2025-12-31", "2026-02-01", 180),
                            ]
                        }
                    },
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "units": {
                            "USD": [_annual_fact("2025-12-31", "2026-02-01", 250)]
                        }
                    },
                    "PaymentsToAcquirePropertyPlantAndEquipment": {
                        "units": {
                            "USD": [_annual_fact("2025-12-31", "2026-02-01", 50)]
                        }
                    },
                    "LongTermDebtAndFinanceLeaseObligationsCurrent": {
                        "units": {
                            "USD": [_instant_fact("2025-12-31", "2026-02-01", 40)]
                        }
                    },
                    "LongTermDebtAndFinanceLeaseObligationsNoncurrent": {
                        "units": {
                            "USD": [_instant_fact("2025-12-31", "2026-02-01", 260)]
                        }
                    },
                    "StockholdersEquity": {
                        "units": {
                            "USD": [_instant_fact("2025-12-31", "2026-02-01", 600)]
                        }
                    },
                }
            }
        }

        fundamentals = calculate_sec_fundamentals(
            companyfacts,
            market_cap=Decimal("3600"),
        )

        self.assertEqual(fundamentals.revenue_growth_pct, Decimal("20.00"))
        self.assertEqual(fundamentals.earnings_growth_pct, Decimal("80.00"))
        self.assertEqual(fundamentals.free_cash_flow_yield_pct, Decimal("5.56"))
        self.assertEqual(fundamentals.net_margin_pct, Decimal("15.00"))
        self.assertEqual(fundamentals.debt_to_equity, Decimal("0.50"))
        self.assertEqual(fundamentals.pe_ratio, Decimal("20.00"))
        self.assertEqual(fundamentals.source_period, "2025-12-31")


def _annual_fact(end: str, filed: str, value: int) -> dict:
    return {
        "end": end,
        "filed": filed,
        "val": value,
        "form": "10-K",
        "fp": "FY",
    }


def _instant_fact(end: str, filed: str, value: int) -> dict:
    return {
        "end": end,
        "filed": filed,
        "val": value,
        "form": "10-K",
        "fp": "FY",
    }
