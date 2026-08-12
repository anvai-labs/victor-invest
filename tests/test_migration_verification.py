"""
Test script to verify Victor framework handler migration.

This script verifies that all handlers have been successfully migrated
to use @handler_decorator + BaseHandler pattern as per Victor framework
best practices.

Run: python tests/test_migration_verification.py
"""

import inspect
import sys
from dataclasses import is_dataclass

# victor.framework.workflows.base_handler no longer exists -- victor-ai has never
# shipped a BaseHandler, and the deprecated contracts bridge that used to supply
# one has been retired. victor_invest.compat.handlers defines the class the
# handlers actually inherit from, so that is what this should assert against.
# Until now the stale import made the whole module uncollectable, which meant
# nothing here had run in a long time.
from victor_invest.compat.handlers import BaseHandler
from victor_invest.handlers import (
    AnalyzePeersHandler,
    FetchMacroDataHandler,
    FetchMarketDataHandler,
    FetchSECDataHandler,
    GenerateLookbackDatesHandler,
    GenerateReportHandler,
    IdentifyPeersHandler,
    ProcessBacktestBatchHandler,
    RunFundamentalAnalysisHandler,
    RunMarketContextHandler,
    RunSynthesisHandler,
    RunTechnicalAnalysisHandler,
    SaveRLPredictionsHandler,
    register_handlers,
)

# All expected handlers
ALL_HANDLERS = [
    FetchSECDataHandler,
    FetchMarketDataHandler,
    FetchMacroDataHandler,
    RunFundamentalAnalysisHandler,
    RunTechnicalAnalysisHandler,
    RunMarketContextHandler,
    RunSynthesisHandler,
    GenerateReportHandler,
    IdentifyPeersHandler,
    AnalyzePeersHandler,
    GenerateLookbackDatesHandler,
    ProcessBacktestBatchHandler,
    SaveRLPredictionsHandler,
]


def test_handler_migration():
    """Verify all handlers are properly migrated."""
    errors = []

    for handler_cls in ALL_HANDLERS:
        handler_name = handler_cls.__name__

        # Test 1: Extends BaseHandler
        if not issubclass(handler_cls, BaseHandler):
            errors.append(f"{handler_name} does not extend BaseHandler")

        # Test 2: Has execute() method
        if not hasattr(handler_cls, "execute"):
            errors.append(f"{handler_name} missing execute() method")
            continue

        # Test 3: execute() signature
        sig = inspect.signature(handler_cls.execute)
        params = list(sig.parameters.keys())
        expected_params = ["self", "node", "context", "tool_registry"]
        if params != expected_params:
            errors.append(f"{handler_name}.execute() has wrong params: {params}")

        # Test 4: Return type
        return_annotation = sig.return_annotation
        if "Tuple" not in str(return_annotation):
            errors.append(f"{handler_name}.execute() wrong return type: {return_annotation}")

        # Test 5: Is dataclass
        if not is_dataclass(handler_cls):
            errors.append(f"{handler_name} is not a dataclass")

    # Test 6: register_handlers() is no-op
    try:
        register_handlers()
    except Exception as e:
        errors.append(f"register_handlers() not a no-op: {e}")

    return errors


if __name__ == "__main__":
    print("Testing Victor Framework Handler Migration")
    print("=" * 60)

    errors = test_handler_migration()

    if errors:
        print("\n❌ Migration Tests Failed:")
        for error in errors:
            print(f"  ✗ {error}")
        sys.exit(1)
    else:
        print("\n✅ All Migration Tests Passed!")
        print(f"  ✓ All {len(ALL_HANDLERS)} handlers extend BaseHandler")
        print("  ✓ All handlers have execute() method")
        print("  ✓ All handlers return Tuple[Any, int]")
        print("  ✓ All handlers are dataclasses")
        print("  ✓ register_handlers() is no-op (backward compatible)")
        print("=" * 60)
        sys.exit(0)
