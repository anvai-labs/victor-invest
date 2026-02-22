"""
Application Layer

Orchestration and high-level services.
"""

from typing import TYPE_CHECKING, Any

from investigator.application.analysis_service import AnalysisService
from investigator.application.orchestrator import (
    AgentOrchestrator,
    AnalysisMode,
    OrchestrationTask,
    Priority,
)
from investigator.application.result_formatter import (
    OutputDetailLevel,
    format_analysis_output,
)
from investigator.application.victor_result_converter import (
    convert_victor_state_to_agent_format,
)

if TYPE_CHECKING:
    from investigator.application.synthesizer import InvestmentSynthesizer


def __getattr__(name: str) -> Any:
    """Lazily import heavyweight application modules on demand."""
    if name == "InvestmentSynthesizer":
        from investigator.application.synthesizer import (
            InvestmentSynthesizer as _InvestmentSynthesizer,
        )

        return _InvestmentSynthesizer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AgentOrchestrator",
    "AnalysisMode",
    "Priority",
    "OrchestrationTask",
    "AnalysisService",
    "InvestmentSynthesizer",
    "OutputDetailLevel",
    "format_analysis_output",
    "convert_victor_state_to_agent_format",
]
