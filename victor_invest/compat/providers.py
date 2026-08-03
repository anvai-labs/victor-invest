"""Provider factory — isolates victor.providers imports.

External verticals should use this factory instead of importing
ProviderRegistry directly from victor.providers.registry.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_provider(
    provider_name: str,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> Any:
    """Create an LLM provider instance via victor's ProviderRegistry.

    Isolates the victor.providers import to this single module.
    Returns None if victor-ai is not installed.
    """
    try:
        from victor_contracts.provider_runtime import ProviderRegistry

        return ProviderRegistry.create(
            provider_name,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
    except ImportError:
        logger.warning("victor-ai not installed — cannot create provider %s", provider_name)
        return None
    except Exception as e:
        logger.error("Failed to create provider %s: %s", provider_name, e)
        return None
