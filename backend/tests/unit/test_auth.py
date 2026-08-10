from unittest import TestCase

import jwt

from app.core.auth import AuthenticatedUser, _user_from_payload
from app.core.config import settings


class AuthConfigTests(TestCase):
    def test_auth_disabled_without_jwt_secret(self) -> None:
        self.assertFalse(settings.auth_enabled)


class AuthPayloadTests(TestCase):
    def test_user_from_payload_maps_email_and_role(self) -> None:
        user = _user_from_payload(
            {
                "sub": "11111111-2222-3333-4444-555555555555",
                "email": "analyst@example.com",
                "app_metadata": {"role": "authenticated"},
            }
        )

        self.assertEqual(user.id, "11111111-2222-3333-4444-555555555555")
        self.assertEqual(user.email, "analyst@example.com")
        self.assertEqual(user.role, "authenticated")

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
