from unittest import TestCase

from app.api.idempotency import (
    IdempotencyKeyError,
    merge_idempotency_key,
    normalize_idempotency_key,
)
from app.services.portfolio.operating_core import _reusable_source_reference


class IdempotencyKeyTests(TestCase):
    def test_blank_key_is_ignored(self) -> None:
        self.assertIsNone(normalize_idempotency_key("   "))
        self.assertIsNone(normalize_idempotency_key(None))

    def test_header_wins_over_body(self) -> None:
        self.assertEqual(merge_idempotency_key("header-key", "body-key"), "header-key")

    def test_body_is_used_when_header_is_absent(self) -> None:
        self.assertEqual(merge_idempotency_key(None, " body-key "), "body-key")

    def test_long_key_is_rejected(self) -> None:
        with self.assertRaises(IdempotencyKeyError):
            normalize_idempotency_key("k" * 129)

    def test_trade_ledger_references_are_not_reused_as_client_keys(self) -> None:
        self.assertIsNone(_reusable_source_reference("manual_trade"))
        self.assertIsNone(_reusable_source_reference("trade:abc"))
        self.assertEqual(_reusable_source_reference(" wire-1 "), "wire-1")
