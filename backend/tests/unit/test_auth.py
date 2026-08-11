from unittest import TestCase
from decimal import Decimal

import jwt

from app.core.auth import AuthenticatedUser, _user_from_payload
from app.core.config import Settings, settings


class AuthConfigTests(TestCase):
    def test_auth_disabled_without_supabase_configuration(self) -> None:
        test_settings = Settings(hf_supabase_jwt_secret="", hf_supabase_url="")
        self.assertFalse(test_settings.auth_enabled)

    def test_auth_enabled_with_supabase_url_only(self) -> None:
        test_settings = Settings(
            hf_supabase_jwt_secret="",
            hf_supabase_url="https://example.supabase.co",
        )
        self.assertTrue(test_settings.auth_enabled)


class AuthPayloadTests(TestCase):
    def test_user_from_payload_maps_email_and_role(self) -> None:
        user = _user_from_payload(
            {
                "sub": "11111111-2222-3333-4444-555555555555",
                "email": "analyst@example.com",
                "app_metadata": {"role": "authenticated"},
                "user_metadata": {"starting_capital": "2500.50"},
            }
        )

        self.assertEqual(user.id, "11111111-2222-3333-4444-555555555555")
        self.assertEqual(user.email, "analyst@example.com")
        self.assertEqual(user.role, "authenticated")
        self.assertEqual(user.starting_capital, Decimal("2500.50"))

    def test_user_from_payload_enforces_minimum_starting_capital(self) -> None:
        user = _user_from_payload(
            {
                "sub": "11111111-2222-3333-4444-555555555555",
                "email": "analyst@example.com",
                "user_metadata": {"starting_capital": "250"},
            }
        )

        self.assertEqual(user.starting_capital, Decimal("1000.00"))

    def test_decode_supabase_token_round_trip_when_secret_configured(self) -> None:
        if not settings.hf_supabase_jwt_secret:
            self.skipTest("HF_SUPABASE_JWT_SECRET is not configured.")

        token = jwt.encode(
            {
                "sub": "11111111-2222-3333-4444-555555555555",
                "email": "analyst@example.com",
                "aud": "authenticated",
            },
            settings.hf_supabase_jwt_secret,
            algorithm="HS256",
        )

        payload = jwt.decode(
            token,
            settings.hf_supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        user = _user_from_payload(payload)

        self.assertIsInstance(user, AuthenticatedUser)
        self.assertEqual(user.email, "analyst@example.com")
