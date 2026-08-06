from unittest import TestCase

from app.services.ticker_intelligence.ai_draft import (
    PROMPT_VERSION,
    _extract_output_text,
    _model_context,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.ticker_intelligence import (
    TickerAIDraftCreate,
    TickerMetricsInput,
)


class TickerAIDraftTests(TestCase):
    def test_extracts_output_text_from_responses_payload(self) -> None:
        payload = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"prompt_version":"ticker_ai_draft_v1"}',
                        }
                    ]
                }
            ]
        }

        self.assertEqual(
            _extract_output_text(payload),
            '{"prompt_version":"ticker_ai_draft_v1"}',
        )

    def test_model_context_includes_three_analysis_layers(self) -> None:
        context = _model_context(
            TickerAIDraftCreate(
                instrument=InstrumentCreate(
                    ticker="AAPL",
                    name="Apple Inc.",
                    asset_class="equity",
                    currency="USD",
                ),
                metrics=TickerMetricsInput(current_price="200", pe_ratio="30"),
                source_warnings=["Forward estimates unavailable."],
            )
        )

        self.assertEqual(context["prompt_version"], PROMPT_VERSION)
        self.assertIn("descriptive", context["analysis_layers"])
        self.assertIn("comparative", context["analysis_layers"])
        self.assertIn("predictive", context["analysis_layers"])
        self.assertEqual(context["instrument"]["ticker"], "AAPL")
