import json

import httpx

from app.llm.ollama_provider import unload_other_models


def _transport(loaded: list[str], calls: list[tuple[str, dict]], fail_ps: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            if fail_ps:
                return httpx.Response(500)
            return httpx.Response(200, json={"models": [{"model": m} for m in loaded]})
        if request.url.path == "/api/generate":
            calls.append((request.url.path, json.loads(request.content)))
            return httpx.Response(200, json={"done": True})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_unloads_only_other_models():
    calls: list[tuple[str, dict]] = []
    t = _transport(["gemma4:26b", "qwen3.5:4b"], calls)
    out = await unload_other_models("http://ollama.test", "qwen3.5:4b", transport=t)
    assert out == ["gemma4:26b"]
    assert calls == [("/api/generate", {"model": "gemma4:26b", "keep_alive": 0})]


async def test_nothing_to_unload_when_only_target_loaded():
    calls: list[tuple[str, dict]] = []
    t = _transport(["qwen3.5:4b"], calls)
    assert await unload_other_models("http://ollama.test", "qwen3.5:4b", transport=t) == []
    assert calls == []


async def test_errors_are_swallowed():
    calls: list[tuple[str, dict]] = []
    t = _transport([], calls, fail_ps=True)
    assert await unload_other_models("http://ollama.test", "x", transport=t) == []

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kapali")

    assert (
        await unload_other_models(
            "http://ollama.test", "x", transport=httpx.MockTransport(boom)
        )
        == []
    )
