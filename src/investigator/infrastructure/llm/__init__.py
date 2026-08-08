"""
LLM Infrastructure

Completions run through victor's provider registry (Sandhi transport), fronted by
VRAM-budgeted admission control.

The hand-rolled Ollama client and multi-server pool that used to live here were
removed: victor already provides transport, retries, circuit breaking, rate
limiting, health checks and endpoint failover across 41 providers. What it does
not provide is per-model VRAM budgeting, so DynamicLLMSemaphore stays and gates
every call.
"""

# vram_calculator contains utility functions, not classes
from investigator.infrastructure.llm import vram_calculator
from investigator.infrastructure.llm.provider_adapter import VictorProviderClient
from investigator.infrastructure.llm.semaphore import DynamicLLMSemaphore

__all__ = [
    "DynamicLLMSemaphore",
    "VictorProviderClient",
    "vram_calculator",
]
