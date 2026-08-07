"""Context-size calculation must tolerate a request that carries no metadata.

``LLMRequest.metadata`` is declared ``dict[str, Any] | None`` and defaults to
``None``. ``LLMExecutionHandler.handle`` calls ``calculate_dynamic_context_size``
for every request, so a request built without metadata -- the documented default
-- reached an unguarded ``request.metadata.get(...)``. The rest of the module
guards the same attribute in three other places, so the omission was local.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from investigator.infrastructure.llm.llm_interfaces import LLMRequest
from investigator.infrastructure.llm.llm_processors import LLMExecutionHandler


class _StubModelConfigManager:
    """Returns fixed context params so the test asserts on branching, not tuning."""

    def get_optimal_context_size(self, **_kwargs: Any) -> dict[str, int]:
        return {"num_ctx": 8192, "num_predict": 1024}


def _make_handler() -> LLMExecutionHandler:
    """Build the handler without its Ollama/config collaborators.

    ``__init__`` constructs an ``OllamaAPIClient`` and reaches for global config;
    the method under test touches none of that, so bypassing the constructor
    keeps this a unit test rather than an integration one.
    """
    handler = object.__new__(LLMExecutionHandler)
    handler.logger = logging.getLogger("test.llm_execution")
    handler.model_config_manager = _StubModelConfigManager()
    # get_model_capabilities() reads this cache before hitting the API.
    handler.model_capabilities_cache = {"test-model": {"context_size": 8192}}
    return handler


@pytest.mark.unit
def test_context_size_handles_request_without_metadata() -> None:
    """A request using the default ``metadata=None`` must not raise."""
    handler = _make_handler()
    request = LLMRequest(model="test-model", prompt="hello", num_predict=1024)

    assert request.metadata is None, "guards the premise: metadata defaults to None"

    params = handler.calculate_dynamic_context_size(request)

    assert params["num_ctx"] == 8192
    assert params["num_predict"] > 0


@pytest.mark.unit
def test_context_size_still_reads_task_type_when_metadata_present() -> None:
    """The no-metadata fix must not stop task_type from being honoured."""
    handler = _make_handler()
    request = LLMRequest(
        model="test-model",
        prompt="hello",
        num_predict=1024,
        metadata={"task_type": "synthesis"},
    )

    params = handler.calculate_dynamic_context_size(request)

    assert params["num_ctx"] == 8192


@pytest.mark.unit
def test_context_size_accepts_enum_like_task_type() -> None:
    """task_type may arrive as an enum member; ``.value`` is unwrapped."""

    class _TaskType:
        value = "technical_analysis"

    handler = _make_handler()
    request = LLMRequest(
        model="test-model",
        prompt="hello",
        num_predict=1024,
        metadata={"task_type": _TaskType()},
    )

    params = handler.calculate_dynamic_context_size(request)

    assert params["num_ctx"] == 8192
