"""The victor-backed client must be a drop-in for the Ollama client it replaces.

The legacy agent layer reaches its LLM through exactly one method --
``self.ollama.generate(...)``, 22 call sites, all the same shape -- and reads
``response["response"]`` back. That single seam is what makes replacing the
hand-rolled Ollama transport with victor's provider registry (whose transport is
Sandhi) a contained change rather than a rewrite.

Two properties matter and are pinned here:

* **Shape fidelity.** ``generate`` still returns Ollama's native dict, including
  the reasoning-model fallback where an empty ``response`` with a populated
  ``thinking`` field promotes ``thinking`` to primary. Getting that wrong would
  silently blank out qwen3/deepseek-r1 output.
* **Admission control survives.** Victor covers transport, retries, circuit
  breaking and multi-endpoint failover, but it does *not* do VRAM-budgeted
  admission. ``DynamicLLMContext`` stays in front, so concurrent requests are
  still gated to fit local memory.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from investigator.infrastructure.llm.provider_adapter import VictorProviderClient


class _Response:
    """Stands in for victor's CompletionResponse."""

    def __init__(self, content: str = "", metadata: dict[str, Any] | None = None, usage=None):
        self.content = content
        self.metadata = metadata
        self.usage = usage
        self.model = "test-model"


def _client(
    response: _Response,
    recorder: dict | None = None,
    provider_name: str = "ollama",
) -> VictorProviderClient:
    provider = MagicMock()

    async def _chat(**kwargs):
        if recorder is not None:
            recorder.update(kwargs)
        return response

    provider.chat = _chat
    client = VictorProviderClient(provider_name=provider_name)
    client._provider = provider
    return client


@pytest.fixture(autouse=True)
def _no_real_admission_control(monkeypatch):
    """Keep these tests off the host's actual memory.

    The real ``DynamicLLMContext`` consults detected VRAM. Letting unit tests
    depend on that makes them pass or hang according to the machine they run on --
    which is precisely how the hang below reached CI.
    """

    class _NoopContext:
        def __init__(self, model, **kwargs):
            self.model = model

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(
        "investigator.infrastructure.llm.provider_adapter.DynamicLLMContext",
        _NoopContext,
    )


@pytest.mark.asyncio
async def test_generate_returns_the_ollama_response_shape():
    """Agents read response["response"]; that key must survive the swap."""
    client = _client(_Response(content="hello world"))

    result = await client.generate(model="test-model", prompt="hi")

    assert result["response"] == "hello world"
    assert result["_raw_response"] == "hello world"
    assert result["done"] is True
    assert result["model"] == "test-model"


@pytest.mark.asyncio
async def test_reasoning_model_thinking_is_promoted_to_primary():
    """An empty content with populated reasoning must not read as an empty answer."""
    client = _client(_Response(content="", metadata={"reasoning_content": "the actual answer"}))

    result = await client.generate(model="qwen3", prompt="hi")

    assert result["response"] == "the actual answer", (
        "reasoning-model output was dropped: content was empty and thinking was not promoted"
    )
    assert result["thinking"] == "the actual answer"
    assert result["_raw_response"] == ""


@pytest.mark.asyncio
async def test_content_wins_when_both_are_present():
    """Only promote thinking when there is no content to promote over."""
    client = _client(_Response(content="real answer", metadata={"reasoning_content": "scratch work"}))

    result = await client.generate(model="qwen3", prompt="hi")

    assert result["response"] == "real answer"
    assert result["thinking"] == "scratch work"


@pytest.mark.asyncio
async def test_system_prompt_becomes_a_system_message():
    """The Ollama `system=` kwarg has no OpenAI-payload equivalent but a role does."""
    recorder: dict = {}
    client = _client(_Response(content="ok"), recorder)

    await client.generate(model="m", prompt="user text", system="you are a bot")

    messages = recorder["messages"]
    assert [m.role for m in messages] == ["system", "user"]
    assert messages[0].content == "you are a bot"
    assert messages[1].content == "user text"


@pytest.mark.asyncio
async def test_json_format_is_translated_not_passed_through():
    """`format="json"` is Ollama-native; kwargs land in an OpenAI-shaped payload.

    Passing it through verbatim would inject a meaningless `format` key rather
    than actually requesting JSON.
    """
    recorder: dict = {}
    client = _client(_Response(content="{}"), recorder)

    await client.generate(model="m", prompt="p", format="json")

    assert "format" not in recorder, "Ollama-native `format` leaked into the OpenAI payload"
    assert recorder.get("response_format") == {"type": "json_object"}


@pytest.mark.asyncio
async def test_admission_control_wraps_every_generate(monkeypatch):
    """VRAM budgeting is the one thing victor does not replace; it must stay."""
    entered: list[str] = []
    exited: list[str] = []

    class _FakeContext:
        def __init__(self, model, **kwargs):
            self.model = model

        async def __aenter__(self):
            entered.append(self.model)
            return self

        async def __aexit__(self, *exc):
            exited.append(self.model)
            return False

    monkeypatch.setattr(
        "investigator.infrastructure.llm.provider_adapter.DynamicLLMContext",
        _FakeContext,
    )

    client = _client(_Response(content="ok"))
    await client.generate(model="big-model", prompt="p")

    assert entered == ["big-model"], "generate ran without acquiring a VRAM allocation"
    assert exited == ["big-model"], "the VRAM allocation was never released"


@pytest.mark.asyncio
async def test_allocation_is_released_when_the_provider_raises(monkeypatch):
    """A failed call must not leak its VRAM budget, or the pool deadlocks."""
    released: list[str] = []

    class _FakeContext:
        def __init__(self, model, **kwargs):
            self.model = model

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            released.append(self.model)
            return False

    monkeypatch.setattr(
        "investigator.infrastructure.llm.provider_adapter.DynamicLLMContext",
        _FakeContext,
    )

    provider = MagicMock()
    provider.chat = AsyncMock(side_effect=RuntimeError("provider exploded"))
    client = VictorProviderClient(provider_name="ollama")
    client._provider = provider

    with pytest.raises(RuntimeError):
        await client.generate(model="m", prompt="p")

    assert released == ["m"], "the allocation leaked when the provider raised"


@pytest.mark.asyncio
async def test_usable_as_an_async_context_manager():
    """OllamaClient was used via `async with`; call sites must not need editing."""
    client = _client(_Response(content="ok"))

    async with client as c:
        assert c is client


@pytest.mark.asyncio
async def test_cloud_providers_are_not_gated_on_local_vram(monkeypatch):
    """Admission control exists to protect local memory, so it must be local-only.

    An Anthropic or OpenAI call consumes no VRAM on this machine. Making it wait
    for a local memory budget would block on a resource it never uses.
    """
    gated: list[str] = []

    class _RecordingContext:
        def __init__(self, model, **kwargs):
            self.model = model

        async def __aenter__(self):
            gated.append(self.model)
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(
        "investigator.infrastructure.llm.provider_adapter.DynamicLLMContext",
        _RecordingContext,
    )

    cloud = _client(_Response(content="ok"), provider_name="anthropic")
    await cloud.generate(model="claude-sonnet-5", prompt="p")
    assert gated == [], "a cloud call was gated on local VRAM it does not consume"

    local = _client(_Response(content="ok"), provider_name="ollama")
    await local.generate(model="qwen3", prompt="p")
    assert gated == ["qwen3"], "a local call skipped VRAM admission control"
