"""Exa MCP client with round-robin API-key rotation.

Mirrors the behaviour of the ``web-access`` plugin: keys are read from
``config.json`` (or ``EXA_API_KEYS``), sent as ``Authorization: Bearer`` and
rotated when Exa answers 401/429.  Request bodies are JSON-RPC ``tools/call``
payloads and both plain-JSON and SSE responses are supported.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

import httpx

from .config import CONFIG_FILE
from .exa import parse_mcp_body, parse_payload
from .models import ProviderError

EXA_MCP_URL = "https://mcp.exa.ai/mcp"
ROTATE_STATUSES = frozenset({401, 429})
_LOCK = asyncio.Lock()
_INDEX = 0


def _env_keys() -> List[str]:
    raw = os.getenv("EXA_API_KEYS", "")
    if raw:
        parts = raw.replace(";", ",").split(",")
    else:
        single = os.getenv("EXA_API_KEY", "")
        parts = [single] if single else []
    return [k.strip() for k in parts if isinstance(k, str) and k.strip()]


def load_exa_keys(config_path: Optional[Any] = None) -> List[str]:
    """Load Exa keys from the environment or ``config.json``.

    Environment keys take precedence so a deployment can override the UI
    settings without editing files.  Both ``["k1", "k2"]`` and
    ``{"keys": ["k1", "k2"]}`` shapes are accepted.
    """
    env_keys = _env_keys()
    if env_keys:
        return env_keys

    path = config_path or CONFIG_FILE
    data: Any = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    raw: Any = data.get("exa_api_keys") if isinstance(data, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("keys")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [k.strip() for k in raw if isinstance(k, str) and k.strip()]


def save_exa_keys(keys: List[str], config_path: Optional[Any] = None) -> None:
    """Persist Exa keys to ``config.json`` while preserving other settings."""
    path = config_path or CONFIG_FILE
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            pass
    cleaned: List[str] = []
    seen: set[str] = set()
    for key in keys:
        if not isinstance(key, str):
            continue
        key = key.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    data["exa_api_keys"] = cleaned
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    reset_key_index()


async def _next_key(keys: List[str]) -> Optional[str]:
    global _INDEX
    if not keys:
        return None
    async with _LOCK:
        index = _INDEX % len(keys)
        _INDEX = (index + 1) % len(keys)
        return keys[index]


def reset_key_index() -> None:
    """Reset the round-robin cursor (used by tests)."""
    global _INDEX
    _INDEX = 0


async def call_exa_mcp(
    tool_name: str,
    arguments: Dict[str, Any],
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 60.0,
) -> Any:
    """Call an Exa MCP tool, rotating keys on rate-limit/auth failures.

    Returns the decoded result payload (usually a list/dict).  Raises
    :class:`ProviderError` when every key has been exhausted or the endpoint
    reports an error.
    """
    keys = load_exa_keys()
    attempts = max(1, len(keys))
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=timeout)
    last_error: Optional[BaseException] = None
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
    )
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    try:
        for attempt in range(attempts):
            request_headers = dict(headers)
            key = await _next_key(keys)
            if key:
                request_headers["Authorization"] = f"Bearer {key}"
            try:
                response = await client.post(EXA_MCP_URL, content=body, headers=request_headers)
            except httpx.HTTPError as exc:
                last_error = exc
                continue

            if response.status_code in ROTATE_STATUSES and attempt < attempts - 1:
                last_error = ProviderError(
                    "exa", f"Exa HTTP {response.status_code} on key {attempt + 1}"
                )
                continue
            if not response.is_success:
                raise ProviderError(
                    "exa", f"Exa HTTP {response.status_code}: {response.text[:300]}"
                )

            payload = parse_mcp_body(response.text)
            if payload is None:
                raise ProviderError("exa", "Exa MCP returned an empty response")
            if "error" in payload:
                error = payload["error"] or {}
                message = error.get("message", "Unknown error")
                raise ProviderError("exa", f"Exa MCP error: {message}")
            result = payload.get("result")
            if isinstance(result, dict) and result.get("isError"):
                text = parse_payload(payload)
                raise ProviderError("exa", str(text) if text else "Exa MCP returned an error")
            parsed = parse_payload(payload)
            if parsed is None:
                raise ProviderError("exa", "Exa MCP returned empty content")
            return parsed

        if last_error:
            raise last_error
        raise ProviderError("exa", "Exa MCP request failed after all retries")
    finally:
        if owns_client:
            await client.aclose()
