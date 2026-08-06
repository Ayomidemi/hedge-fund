import json
import logging
import time
from decimal import Decimal

import httpx

from app.api.schemas.ticker_intelligence import (
    TickerAIDraftCreate,
    TickerAIDraftResponse,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ticker_ai_draft_v1"


class AIDraftUnavailableError(RuntimeError):
    pass


async def generate_ticker_ai_draft(
    payload: TickerAIDraftCreate,
) -> TickerAIDraftResponse:
    if settings.ai_provider != "openai":
        raise AIDraftUnavailableError("AI provider is not configured.")
    if not settings.hf_openai_api_key:
        raise AIDraftUnavailableError("OpenAI API key is missing.")

    started_at = time.perf_counter()
    response_payload = await _create_openai_response(payload)
    draft_json = _extract_output_text(response_payload)

    try:
        draft = TickerAIDraftResponse.model_validate_json(draft_json)
    except ValueError as exc:
        raise AIDraftUnavailableError("AI draft response was not valid JSON.") from exc

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "ticker_ai_draft_generated",
        extra={
            "ticker": payload.instrument.ticker,
            "model": draft.model,
            "prompt_version": draft.prompt_version,
            "elapsed_ms": elapsed_ms,
            "question_count": len(draft.analyst_questions),
            "missing_data_warning_count": len(draft.missing_data_warnings),
        },
    )
    return draft


async def _create_openai_response(payload: TickerAIDraftCreate) -> dict:
    request_payload = {
        "model": settings.hf_openai_model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": _system_prompt(),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(_model_context(payload), default=_json_default),
                    }
                ],
            },
        ],
        "reasoning": {"effort": settings.hf_openai_reasoning_effort},
        "text": {
            "verbosity": "medium",
            "format": {
                "type": "json_schema",
                "name": "ticker_ai_draft",
                "strict": True,
                "schema": _draft_json_schema(),
            },
        },
    }

    async with httpx.AsyncClient(
        base_url=settings.openai_base_url,
        timeout=httpx.Timeout(30.0),
        headers={
            "Authorization": f"Bearer {settings.hf_openai_api_key}",
            "Content-Type": "application/json",
        },
    ) as client:
        response = await client.post("/v1/responses", json=request_payload)

    if response.status_code >= 400:
        detail = _openai_error_detail(response)
        logger.warning(
            "ticker_ai_draft_failed",
            extra={
                "ticker": payload.instrument.ticker,
                "status_code": response.status_code,
                "model": settings.hf_openai_model,
            },
        )
        raise AIDraftUnavailableError(detail)

    try:
        return response.json()
    except ValueError as exc:
        raise AIDraftUnavailableError("OpenAI response was not JSON.") from exc


def _system_prompt() -> str:
    return (
        "You are the Pease Capital ticker analyst assistant. Draft research fields "
        "for an internal hedge-fund analyst workflow. Use only the supplied data. "
        "Do not invent unavailable financial facts, target prices, analyst estimates, "
        "news, or live events. If data is missing, ask precise questions and record "
        "the gap in missing_data_warnings. Keep language investment-committee ready: "
        "specific, balanced, and auditable. The deterministic scorecard and human "
        "review decide action; your job is to draft questions and memo language."
    )


def _model_context(payload: TickerAIDraftCreate) -> dict:
    return {
        "prompt_version": PROMPT_VERSION,
        "required_output_model": settings.hf_openai_model,
        "instrument": payload.instrument.model_dump(mode="json"),
        "metrics": payload.metrics.model_dump(mode="json"),
        "time_horizon": payload.time_horizon,
        "source_reference": payload.source_reference,
        "source_warnings": payload.source_warnings,
        "user_notes": payload.user_notes,
        "analysis_layers": {
            "descriptive": [
                "valuation",
                "growth",
                "margins",
                "leverage",
                "volatility",
                "momentum",
            ],
            "comparative": [
                "history",
                "sector",
                "peers",
                "complete stock universe",
            ],
            "predictive": [
                "expected relative return",
                "downside distribution",
                "model confidence",
                "portfolio improvement",
            ],
        },
    }


def _draft_json_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "prompt_version",
            "model",
            "investment_question",
            "analyst_questions",
            "thesis",
            "bull_case",
            "base_case",
            "bear_case",
            "thesis_breakers",
            "risk_notes",
            "missing_data_warnings",
            "confidence_notes",
        ],
        "properties": {
            "prompt_version": {"type": "string", "enum": [PROMPT_VERSION]},
            "model": {"type": "string"},
            "investment_question": {"type": "string"},
            "analyst_questions": {
                "type": "array",
                "minItems": 4,
                "maxItems": 8,
                "items": {"type": "string"},
            },
            "thesis": {"type": "string"},
            "bull_case": {"type": "string"},
            "base_case": {"type": "string"},
            "bear_case": {"type": "string"},
            "thesis_breakers": {"type": "string"},
            "risk_notes": {"type": "string"},
            "missing_data_warnings": {
                "type": "array",
                "items": {"type": "string"},
            },
            "confidence_notes": {"type": "string"},
        },
    }


def _extract_output_text(response_payload: dict) -> str:
    direct_text = response_payload.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text

    output = response_payload.get("output", [])
    if not isinstance(output, list):
        raise AIDraftUnavailableError("OpenAI response did not contain output.")

    text_parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                text_parts.append(text)

    if not text_parts:
        raise AIDraftUnavailableError("OpenAI response did not contain output text.")
    return "".join(text_parts)


def _openai_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"OpenAI request failed with status {response.status_code}."

    error = body.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    return f"OpenAI request failed with status {response.status_code}."


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
