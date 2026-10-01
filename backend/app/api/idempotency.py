"""Client idempotency keys for money-moving writes.

A key is optional. When a caller sends one, a replay of that request returns
the original row instead of booking the movement again.
"""

from fastapi import Header, HTTPException, status


class IdempotencyKeyError(ValueError):
    pass


def normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 128:
        raise IdempotencyKeyError("Idempotency-Key must be 128 characters or fewer.")
    return cleaned


def merge_idempotency_key(header: str | None, body: str | None) -> str | None:
    """Header wins when both are present. Body is the fallback."""
    if header:
        return header
    return normalize_idempotency_key(body)


def optional_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str | None:
    try:
        return normalize_idempotency_key(idempotency_key)
    except IdempotencyKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
