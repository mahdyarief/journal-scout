import json

import httpx

from josc.exa import parse_mcp_body, parse_payload
from josc.exa_client import (
    call_exa_mcp,
    load_exa_keys,
    reset_key_index,
    save_exa_keys,
)


def _sse(payload: dict) -> str:
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


def _result(text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": text}]},
    }


def test_parse_mcp_body_accepts_sse():
    body = _sse(_result('{"ok": true}'))
    payload = parse_mcp_body(body)
    assert payload is not None
    assert payload["result"]["content"][0]["text"] == '{"ok": true}'


def test_parse_payload_decodes_json_text():
    assert parse_payload(_result('[{"title": "A"}]')) == [{"title": "A"}]


def test_load_and_save_keys_roundtrip(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"polite_email": "a@b.c"}), encoding="utf-8")

    save_exa_keys([" one ", "two", "one"], config_path=config)
    assert load_exa_keys(config_path=config) == ["one", "two"]

    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["polite_email"] == "a@b.c"


async def test_call_rotates_on_401(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    save_exa_keys(["bad-key", "good-key"], config_path=config)
    monkeypatch.setenv("EXA_API_KEYS", "")
    monkeypatch.setenv("EXA_API_KEY", "")
    monkeypatch.setattr("josc.exa_client.load_exa_keys", lambda *a, **k: ["bad-key", "good-key"])
    reset_key_index()

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        seen.append(auth)
        if auth.endswith("bad-key"):
            return httpx.Response(401, text="unauthorized")
        return httpx.Response(
            200,
            text=_sse(_result('[{"title": "Found", "url": "https://x"}]')),
            headers={"content-type": "text/event-stream"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await call_exa_mcp("web_search_exa", {"query": "x"}, client=client)

    assert result == [{"title": "Found", "url": "https://x"}]
    assert seen == ["Bearer bad-key", "Bearer good-key"]


async def test_call_exhausts_keys_and_raises(monkeypatch):
    monkeypatch.setattr("josc.exa_client.load_exa_keys", lambda *a, **k: ["only-key"])
    reset_key_index()

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, text="slow down"))
    )
    try:
        await call_exa_mcp("web_search_exa", {"query": "x"}, client=client)
    except Exception as exc:  # noqa: BLE001 - provider error surface
        assert "429" in str(exc)
    else:
        raise AssertionError("expected a rotation failure")
