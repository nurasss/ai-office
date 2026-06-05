#!/usr/bin/env python3
"""Telegram webhook smoke in dry/mock or explicit real mode."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Telegram webhook configuration.")
    parser.add_argument("--real", action="store_true", help="POST a mock update to APP_BASE_URL using TELEGRAM_WEBHOOK_SECRET.")
    args = parser.parse_args()

    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()

    payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123, "is_bot": False, "first_name": "Smoke"},
            "text": "/status",
        },
    }

    if not args.real:
        print("dry_run=true")
        print("webhook_url=" + base_url + "/api/telegram/webhook")
        print("payload=" + json.dumps(payload, sort_keys=True))
        print("Telegram dry-run smoke passed.")
        return 0

    if not secret:
        print("TELEGRAM_WEBHOOK_SECRET is required for --real.", file=sys.stderr)
        return 1

    request = urllib.request.Request(
        base_url + "/api/telegram/webhook",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": secret,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.read().decode("utf-8"))
    print("Telegram real webhook smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
