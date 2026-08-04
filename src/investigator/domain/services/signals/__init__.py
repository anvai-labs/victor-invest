"""
Signal Generation Module

Provides entry/exit signal generation for stock analysis.
"""

from investigator.domain.services.signals.entry_exit_engine import (
    EntryExitEngine,
    EntrySignal,
    ExitSignal,
    OptimalEntryZone,
    ScalingStrategy,
    SignalConfidence,
    SignalTiming,
    SignalType,
    get_entry_exit_engine,
)
from investigator.domain.services.signals.signal_integrator import (
    IntegratedSignals,
    SignalIntegrator,
    get_signal_integrator,
)

__all__ = [
    "EntryExitEngine",
    # Entry/Exit Engine
    "EntrySignal",
    "ExitSignal",
    # Signal Integrator
    "IntegratedSignals",
    "OptimalEntryZone",
    "ScalingStrategy",
    "SignalConfidence",
    "SignalIntegrator",
    "SignalTiming",
    "SignalType",
    "get_entry_exit_engine",
    "get_signal_integrator",
]
