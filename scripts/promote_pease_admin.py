#!/usr/bin/env python3
"""Promote a Supabase user to Pease ADMIN via the service-role API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env")

EMAIL = (sys.argv[1] if len(sys.argv) > 1 else "peaseadeniji@gmail.com").strip().lower()
SUPABASE_URL = (os.environ.get("HF_SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY = os.environ.get("HF_SUPABASE_SERVICE_ROLE_KEY") or ""


def main() -> int:
    if not SUPABASE_URL or not SERVICE_KEY:
        print("Missing HF_SUPABASE_URL or HF_SUPABASE_SERVICE_ROLE_KEY.", file=sys.stderr)
        return 1

    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30.0) as client:
        listed = client.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=headers,
            params={"page": 1, "per_page": 200},
        )
        listed.raise_for_status()
        users = listed.json().get("users") or []
        match = next(
            (
                user
                for user in users
                if str(user.get("email") or "").strip().lower() == EMAIL
            ),
            None,
        )
        if match is None:
            print(f"No Supabase user found for {EMAIL}.", file=sys.stderr)
            return 1

        user_id = match["id"]
        app_metadata = dict(match.get("app_metadata") or {})
        user_metadata = dict(match.get("user_metadata") or {})
        app_metadata["pease_role"] = "ADMIN"
        app_metadata["role"] = "ADMIN"
        user_metadata["pease_role"] = "ADMIN"

        updated = client.put(
            f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
            headers=headers,
            json={
                "app_metadata": app_metadata,
                "user_metadata": user_metadata,
            },
        )
        updated.raise_for_status()
        body = updated.json()
        print(
            f"Promoted {body.get('email')} ({user_id}) to ADMIN. "
            "Sign out and sign back in to refresh the JWT."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
