"""PII and secret redaction helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RedactionFinding:
    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    findings: list[RedactionFinding] = field(default_factory=list)


PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("TOKEN", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9_]{10,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"), "[TOKEN_REDACTED]"),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL_REDACTED]"),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN_REDACTED]"),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\w)"), "[PHONE_REDACTED]"),
    ("IIN", re.compile(r"(?<!\d)\d{12}(?!\d)"), "[IIN_REDACTED]"),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[CARD_REDACTED]"),
]


def redact_pii(text: str) -> RedactionResult:
    """Redact common PII/secrets from text.

    The function intentionally returns only finding spans/kinds and not raw
    matched values, so callers can safely log the result metadata.
    """
    current = str(text or "")
    findings: list[RedactionFinding] = []
    for kind, pattern, replacement in PATTERNS:
        matches = list(pattern.finditer(current))
        if not matches:
            continue
        findings.extend(RedactionFinding(kind=kind, start=match.start(), end=match.end()) for match in matches)
        current = pattern.sub(replacement, current)

    return RedactionResult(redacted_text=current, findings=findings)


def redact_secrets_for_audit(value: Any) -> Any:
    """Redact strings inside JSON-compatible audit metadata."""
    if isinstance(value, str):
        return redact_pii(value).redacted_text
    if isinstance(value, dict):
        return {str(key): redact_secrets_for_audit(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets_for_audit(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets_for_audit(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
