import base64
import binascii
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Iterable

from ..config import Settings

_REDACTION_PATTERNS = [
    re.compile(r"(api[_-]?key|secret|signature|token)=[^&\s]+", re.IGNORECASE),
    re.compile(r"\b(\+?260)?\d{9}\b"),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
    re.compile(r"\b\d{10,19}\b"),
]


def redact(value: object) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    for pattern in _REDACTION_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _candidate_signatures(header_value: str) -> Iterable[str]:
    for candidate in header_value.split():
        version, separator, signature = candidate.strip().partition(",")
        if separator and version == "v1" and signature:
            yield signature


def verify_lipila_signature(raw_body: bytes, headers: dict[str, str], settings: Settings) -> bool:
    """Verify a Lipila webhook against the configured signing secrets.

    Both the current and the previous secret are accepted so a rotation does not
    drop events that were signed moments before the swap.
    """
    normalized_headers = {key.lower(): value for key, value in headers.items()}
    webhook_id = normalized_headers.get("webhook-id")
    timestamp = normalized_headers.get("webhook-timestamp")
    signature = normalized_headers.get("webhook-signature")
    if not webhook_id or not timestamp or not signature:
        return False

    try:
        event_time = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return False

    age = abs((datetime.now(timezone.utc) - event_time).total_seconds())
    if age > settings.lipila_webhook_replay_window_seconds:
        return False

    signed_payload = f"{webhook_id}.{timestamp}.".encode("utf-8") + raw_body
    secrets = [settings.lipila_webhook_secret_current]
    if settings.lipila_webhook_secret_previous:
        secrets.append(settings.lipila_webhook_secret_previous)

    candidates = list(_candidate_signatures(signature))
    for secret in secrets:
        if not secret:
            continue
        try:
            key = base64.b64decode(secret, validate=True)
        except (binascii.Error, ValueError):
            continue
        if len(key) != 32:
            continue
        digest = hmac.new(key, signed_payload, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("ascii")
        if any(hmac.compare_digest(expected, candidate) for candidate in candidates):
            return True
    return False
