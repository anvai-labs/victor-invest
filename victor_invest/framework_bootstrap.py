# Copyright 2025 Vijaykumar Singh <vijay@anvaiops.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared Victor framework bootstrap utilities for investment workflows."""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from victor.framework import Agent

from victor_invest.role_provider import register_investment_role_provider
from victor_invest.tools import register_investment_tools
from victor_invest.vertical.investment_vertical import InvestmentVertical

logger = logging.getLogger(__name__)

# Victor framework-compatible environment variables
VICTOR_PROVIDER = os.getenv("VICTOR_PROVIDER", "")
VICTOR_MODEL = os.getenv("VICTOR_MODEL", "")

# Legacy default (for backward compatibility)
DEFAULT_SYNTHESIS_MODEL = "gpt-oss:20b"

# Provider-specific default models
PROVIDER_DEFAULT_MODELS = {
    "ollama": DEFAULT_SYNTHESIS_MODEL,
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
}


def resolve_provider_from_env(fallback: str = "ollama") -> str:
    """Resolve LLM provider from Victor framework environment variables.

    Priority:
    1. VICTOR_PROVIDER environment variable
    2. Provider parameter passed to function
    3. Fallback default (ollama)

    Args:
        fallback: Default provider if no env var set (default: "ollama")

    Returns:
        Provider name (ollama, anthropic, openai)
    """
    # Check Victor framework environment variable
    env_provider = os.getenv("VICTOR_PROVIDER", "").strip().lower()
    if env_provider:
        # Validate provider
        valid_providers = {"ollama", "anthropic", "openai"}
        if env_provider in valid_providers:
            logger.debug(f"Using provider from VICTOR_PROVIDER: {env_provider}")
            return env_provider
        else:
            logger.warning(
                f"Invalid VICTOR_PROVIDER '{env_provider}'. "
                f"Must be one of: {', '.join(valid_providers)}. Using fallback: {fallback}"
            )
            return fallback

    return fallback


def resolve_model_from_env(provider: str, model: Optional[str]) -> Optional[str]:
    """Resolve model name from Victor framework environment variables.

    Priority:
    1. Explicit model parameter
    2. VICTOR_MODEL environment variable
    3. Provider-specific default from config.yaml
    4. Provider-specific code default

    Args:
        provider: LLM provider (ollama, anthropic, openai)
        model: Explicitly specified model name

    Returns:
        Model name or None (let provider use its default)
    """
    # 1. Explicit model parameter takes precedence
    if model is not None:
        logger.debug(f"Using explicit model parameter: {model}")
        return model

    # 2. Check Victor framework environment variable
    env_model = os.getenv("VICTOR_MODEL", "").strip()
    if env_model:
        logger.debug(f"Using model from VICTOR_MODEL: {env_model}")
        return env_model

    # 3. Try to get from config.yaml (provider-specific)
    try:
        from investigator.config import get_config

        config = get_config()

        if provider == "ollama":
            model_config = config.ollama.models.get("synthesis")
            if model_config:
                logger.debug(f"Using model from config.yaml ollama.models.synthesis: {model_config}")
                return str(model_config)
        elif provider == "anthropic":
            # Check for victor_llm config section (new)
            if hasattr(config, "victor_llm"):
                anthropic_config = config.victor_llm.get("anthropic", {})
                model_config = anthropic_config.get("model")
                if model_config:
                    logger.debug(f"Using model from config.yaml victor_llm.anthropic.model: {model_config}")
                    return str(model_config)
        elif provider == "openai":
            if hasattr(config, "victor_llm"):
                openai_config = config.victor_llm.get("openai", {})
                model_config = openai_config.get("model")
                if model_config:
                    logger.debug(f"Using model from config.yaml victor_llm.openai.model: {model_config}")
                    return str(model_config)
    except Exception as e:
        logger.debug(f"Could not load model from config.yaml: {e}")

    # 4. Use provider-specific code default
    default_model = PROVIDER_DEFAULT_MODELS.get(provider)
    if default_model:
        logger.debug(f"Using provider default model: {provider} -> {default_model}")
        return default_model

    # For non-default providers, return None to let Victor use its own defaults
    logger.debug(f"No default model for provider '{provider}', using Victor's default")
    return None


def resolve_investment_model(provider: str, model: Optional[str]) -> Optional[str]:
    """Resolve model for investment workflows with provider-aware defaults.

    This function now delegates to resolve_model_from_env for unified
    environment variable handling.

    Args:
        provider: LLM provider (ollama, anthropic, openai)
        model: Explicitly specified model name

    Returns:
        Model name or None (let provider use its default)
    """
    return resolve_model_from_env(provider, model)


def prepare_orchestrator_for_investment(
    orchestrator,
    warning_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Register and enable investment tools on a Victor orchestrator."""
    warn = warning_callback or logger.warning

    try:
        stats = register_investment_tools(orchestrator.tools)
        if stats.get("errors"):
            warn(f"Tool registration warnings: {stats['errors']}")
    except Exception as exc:
        warn(f"Investment tool registration failed: {exc}")
        return

    try:
        orchestrator.set_enabled_tools(set(InvestmentVertical.get_tools()))
        if hasattr(orchestrator, "tool_selector"):
            orchestrator.tool_selector.invalidate_tool_cache()
    except Exception as exc:
        warn(f"Tool enablement refresh skipped: {exc}")


async def create_investment_orchestrator(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    *,
    ensure_handlers: Optional[Callable[[], None]] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    warning_callback: Optional[Callable[[str], None]] = None,
):
    """Create Victor orchestrator preconfigured for investment workflows.

    Args:
        provider: LLM provider (ollama, anthropic, openai). If None, uses
            VICTOR_PROVIDER env var or defaults to 'ollama'
        model: Model name. If None, uses VICTOR_MODEL env var or provider default
        ensure_handlers: Optional callback to ensure handlers are registered
        temperature: LLM temperature (default: 0.3)
        max_tokens: Max tokens in response (default: 4096)
        warning_callback: Optional callback for warnings

    Returns:
        Configured Victor orchestrator ready for investment workflows
    """
    if ensure_handlers:
        ensure_handlers()

    # Register role provider for the standalone app path.
    # In the plugin path this is done by InvestmentPlugin.on_activate().
    register_investment_role_provider()

    # Resolve provider from environment if not specified
    resolved_provider = resolve_provider_from_env(fallback=provider or "ollama")
    resolved_model = resolve_model_from_env(resolved_provider, model)

    logger.info(f"Creating Victor Agent: provider={resolved_provider}, model={resolved_model or '(default)'}")

    agent = await Agent.create(
        provider=resolved_provider,
        model=resolved_model,
        vertical=InvestmentVertical,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    orchestrator = agent.get_orchestrator()
    prepare_orchestrator_for_investment(orchestrator, warning_callback=warning_callback)
    return orchestrator


__all__ = [
    "DEFAULT_SYNTHESIS_MODEL",
    "PROVIDER_DEFAULT_MODELS",
    "resolve_provider_from_env",
    "resolve_model_from_env",
    "resolve_investment_model",
    "prepare_orchestrator_for_investment",
    "create_investment_orchestrator",
]
