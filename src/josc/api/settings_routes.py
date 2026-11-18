"""Read and update runtime settings exposed by the web UI."""

from __future__ import annotations

import json
import os
from typing import Any, List

from starlette.responses import JSONResponse

from ..consensus_key import mask_key
from ..exa_client import load_exa_keys, save_exa_keys
from .responses import _error


def _clean_keys(raw: Any) -> List[str]:
    if isinstance(raw, str):
        raw = raw.replace("\r", "").split("\n")
    if not isinstance(raw, list):
        return []
    keys: List[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


async def settings_exa(request: Any):
    if request.method == "GET":
        keys = load_exa_keys()
        return JSONResponse(
            {
                "keys": [{"masked": mask_key(key), "source": _key_source()} for key in keys],
                "count": len(keys),
                "env_override": bool(os.getenv("EXA_API_KEYS") or os.getenv("EXA_API_KEY")),
            }
        )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _error(ValueError("invalid JSON body"), 400)
    keys = _clean_keys(body.get("keys"))
    try:
        save_exa_keys(keys)
    except OSError as exc:
        return _error(RuntimeError(f"could not save settings: {exc}"), 500)
    return JSONResponse({"count": len(keys), "saved": True})


def _key_source() -> str:
    return (
        "env"
        if os.getenv("EXA_API_KEYS") or os.getenv("EXA_API_KEY")
        else "config"
    )
