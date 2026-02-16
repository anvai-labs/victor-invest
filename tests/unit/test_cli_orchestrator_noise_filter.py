import importlib
import logging

cli_orchestrator = importlib.import_module("cli_orchestrator")


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="victor.core.verticals.base",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_orchestrator_noise_filter_suppresses_known_external_vertical_messages():
    noise_filter = cli_orchestrator._VictorExternalVerticalNoiseFilter()

    conflict_msg = (
        "External vertical 'coding' has name 'coding' "
        "which conflicts with existing vertical CodingAssistant. Skipping registration."
    )
    missing_module_msg = (
        "Failed to load external vertical 'security_analysis' from entry point "
        "'victor.security_analysis:SecurityAnalysisAssistant': No module named 'victor.security_analysis'"
    )

    assert noise_filter.filter(_record(conflict_msg)) is False
    assert noise_filter.filter(_record(missing_module_msg)) is False


def test_orchestrator_noise_filter_keeps_other_messages():
    noise_filter = cli_orchestrator._VictorExternalVerticalNoiseFilter()
    normal_msg = "Failed to register vertical services: timeout contacting provider"
    assert noise_filter.filter(_record(normal_msg)) is True
