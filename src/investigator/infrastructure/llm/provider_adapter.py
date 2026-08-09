"""Ollama-shaped facade over victor's provider registry.

The legacy agent layer reaches its LLM through exactly one method --
``self.ollama.generate(model=..., prompt=..., system=..., format=...)`` -- and
reads ``response["response"]`` back. This module keeps that contract while moving
the transport underneath it to victor's ``ProviderRegistry``.

Why move it at all: the hand-rolled stack here reimplemented what victor already
does better and for 41 providers rather than one -- HTTP transport, retries,
circuit breaking, rate limiting, health checks, multi-endpoint failover, model
pull/list. Victor's own Ollama provider delegates completion to the Sandhi typed
variant, so inference is metered there too. ``handlers.py`` already states the
intent: "Always uses Victor's provider framework for proper retry logic and error
handling."

What victor does *not* replace is VRAM-budgeted admission control. Victor's
endpoint selection picks the first reachable server; it does not estimate a
model's memory footprint and gate concurrency so that concurrent requests fit in
local memory. ``DynamicLLMSemaphore`` does, so it stays in front of every call as
a thin admission layer. That is the one piece of the old stack worth keeping.

Translation notes, because the two wire formats differ:

* ``system=`` has no OpenAI-payload key; it becomes a ``system``-role message.
* ``format="json"`` is Ollama-native. Victor's transport merges ``**kwargs``
  straight into an OpenAI-shaped payload, so passing it through would inject a
  meaningless ``format`` key instead of requesting JSON. It maps to
  ``response_format={"type": "json_object"}``.
* Reasoning models (qwen3, deepseek-r1) return their answer in a reasoning field
  with empty content. The old client promoted that to ``response``; so does this,
  because dropping it silently blanks those models' output.
"""

from __future__ import annotations

import logging
from typing import Any, Self

from investigator.infrastructure.llm.semaphore import DynamicLLMContext

logger = logging.getLogger(__name__)

# Keys victor may use for a reasoning model's hidden chain of thought.
_REASONING_KEYS = ("reasoning_content", "reasoning", "thinking")

# Providers that load weights into this machine's memory. Only these are worth
# gating: an Anthropic or OpenAI call consumes no local VRAM, so making it wait on
# a local memory budget would block on a resource it never touches.
_LOCAL_PROVIDERS = frozenset(
    {
        "ollama",
        "llamacpp",
        "llama-cpp",
        "llama.cpp",
        "lmstudio",
        "mlx",
        "mlx-lm",
        "applesilicon",
        "vllm",
    }
)


class _NullAdmission:
    """No-op stand-in for DynamicLLMContext on providers that use no local VRAM."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _infer_task_type(prompt: str) -> str:
    """Classify the prompt so the semaphore can size the allocation.

    Carried over from the client this replaces: the semaphore budgets differently
    per task type, and the only signal available at this layer is the prompt.
    """
    lowered = prompt.lower()
    if "analysis" in lowered:
        if "technical" in lowered:
            return "technical"
        if "fundamental" in lowered:
            return "fundamental"
        if "sec" in lowered or "filing" in lowered:
            return "sec"
        if "synthesis" in lowered or "recommendation" in lowered:
            return "synthesis"
    return "summary"


def _extract_reasoning(response: Any) -> str:
    """Pull the reasoning text out of whichever field victor used."""
    metadata = getattr(response, "metadata", None)
    if isinstance(metadata, dict):
        for key in _REASONING_KEYS:
            value = metadata.get(key)
            if value:
                return str(value)
    for key in _REASONING_KEYS:
        value = getattr(response, key, None)
        if value:
            return str(value)
    return ""


class VictorProviderClient:
    """Drop-in replacement for ``OllamaClient`` and ``ResourceAwareOllamaPool``.

    Both exposed ``generate(model, prompt, **kwargs) -> dict``; the orchestrator
    handed the pool to agents as ``ollama_client``, so a single class satisfies
    both roles.
    """

    def __init__(
        self,
        provider_name: str = "ollama",
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **provider_kwargs: Any,
    ) -> None:
        self.provider_name = provider_name
        self.default_model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._provider_kwargs = provider_kwargs
        self._provider: Any | None = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _get_provider(self, model: str) -> Any:
        """Create the victor provider on first use and reuse it thereafter."""
        if self._provider is None:
            # victor_contracts rather than victor_invest.compat.providers: this
            # module sits in investigator/, and importing the vertical from here
            # would invert the dependency direction. victor_contracts is already a
            # declared dependency, and it is what that factory calls anyway.
            try:
                from victor_contracts.provider_runtime import ProviderRegistry
            except ImportError as exc:  # pragma: no cover - depends on install
                raise RuntimeError("victor-contracts is not installed, so no LLM provider is available.") from exc

            self._provider = ProviderRegistry.create(
                self.provider_name,
                model=model or self.default_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                **self._provider_kwargs,
            )
            if self._provider is None:
                raise RuntimeError(
                    f"Could not create victor provider {self.provider_name!r}. Is it registered and configured?"
                )
        return self._provider

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        close = getattr(self._provider, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                self.logger.debug("Provider close failed", exc_info=True)

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        format: str | None = None,
        prompt_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a completion, returning Ollama's native response dict.

        Args:
            format: ``"json"`` requests a JSON object, translated to the
                OpenAI-compatible ``response_format``.
            prompt_name: Carried for logging parity with the client this replaces;
                it never reached the wire there either.

        Returns:
            A dict with ``response`` (primary text), ``thinking``,
            ``_raw_response`` and ``_raw_thinking``, matching what the agent layer
            and ``llm_response_processor`` already expect.
        """
        from victor_contracts.provider_runtime import Message

        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        call_kwargs: dict[str, Any] = dict(extra_kwargs)
        if format == "json":
            call_kwargs["response_format"] = {"type": "json_object"}
        elif format:
            self.logger.debug("Ignoring unsupported format %r", format)

        provider = self._get_provider(model)

        # Admission control: gate on estimated VRAM before the request goes out,
        # but only where the weights actually live on this machine. The context
        # manager releases on the way out, including on exception -- a leaked
        # allocation would eventually stall every later request.
        if self.provider_name.lower() in _LOCAL_PROVIDERS:
            admission: Any = DynamicLLMContext(
                model=model,
                task_type=_infer_task_type(prompt),
                prompt_tokens=len(prompt) // 4,
                response_tokens=max_tokens or self.max_tokens,
            )
        else:
            admission = _NullAdmission()

        async with admission:
            response = await provider.chat(
                messages=messages,
                model=model,
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=self.max_tokens if max_tokens is None else max_tokens,
                **call_kwargs,
            )

        content = str(getattr(response, "content", "") or "")
        thinking = _extract_reasoning(response)

        # Reasoning models put the answer in the reasoning field and leave content
        # empty. Promote it, or those models read as having returned nothing.
        primary = thinking if (thinking and not content) else content
        if thinking and not content:
            self.logger.info("Using reasoning field as primary response for %s", model)

        usage = getattr(response, "usage", None) or {}
        return {
            "model": model,
            "response": primary,
            "thinking": thinking,
            "_raw_response": content,
            "_raw_thinking": thinking,
            "done": True,
            "prompt_eval_count": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            "eval_count": usage.get("completion_tokens") if isinstance(usage, dict) else None,
        }

    async def health_check(self) -> bool:
        """Report whether the provider is reachable.

        Listing models is the cheapest round trip that proves the endpoint answers,
        which is what the status commands actually want to know.
        """
        try:
            await self.list_models()
            return True
        except Exception as exc:
            self.logger.debug("Provider health check failed: %s", exc)
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """List models available to the provider."""
        provider = self._get_provider(self.default_model or "")
        return await provider.list_models()

    async def pull_model(self, model: str) -> Any:
        """Pull a model, yielding the provider's progress records."""
        provider = self._get_provider(model)
        return provider.pull_model(model)
