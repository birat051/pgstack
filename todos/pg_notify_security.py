"""Helpers for guarding LISTEN / NOTIFY payloads (see PR 06 + PR 08)."""

from __future__ import annotations

import json
from typing import Any


def todo_update_payload_allowed_for_user(payload: str | None, *, viewer_pk: int) -> bool:
    """
    Return True iff ``todo_updates`` JSON should be forwarded to the WebSocket
    subscribed as ``viewer_pk``. Missing or malformed payloads are refused.
    """
    if not payload:
        return False
    try:
        raw: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError:
        return False
    raw_owner_id = raw.get('owner_id')
    if isinstance(raw_owner_id, bool):  # json true/false misuse
        return False
    if isinstance(raw_owner_id, int):
        return raw_owner_id == viewer_pk
    if isinstance(raw_owner_id, str) and raw_owner_id.isdigit():
        return int(raw_owner_id) == viewer_pk
    return False
