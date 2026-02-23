# Shared Module Refactoring - Compact Format Support

## Summary

Refactored compact format implementation to use shared modules, eliminating code duplication between victor-invest and investigator CLIs.

## Problem

Initial implementation had ~100 lines of conversion logic duplicated in `victor_invest/cli.py`:
- Manual transformation of `AnalysisWorkflowState` to agent orchestrator format
- Hardcoded field mappings
- No reusability
- Maintenance burden (changes needed in multiple places)

## Solution

Created shared converter module: `src/investigator/application/victor_result_converter.py`

### Before (Duplicated Code)

```python
# In victor_invest/cli.py (~100 lines)
def _convert_state_to_agent_format(state: AnalysisWorkflowState) -> dict:
    from datetime import datetime

    agent_format = {
        "symbol": state.symbol,
        "mode": state.mode.value,
        "started_at": datetime.now().isoformat(),
        # ... 90+ lines of manual transformations ...
    }
    return agent_format
```

### After (Shared Module)

```python
# In victor_invest/cli.py (~10 lines)
def _convert_state_to_agent_format(state: AnalysisWorkflowState) -> dict:
    from investigator.application import convert_victor_state_to_agent_format
    return convert_victor_state_to_agent_format(state)

# In src/investigator/application/victor_result_converter.py
def convert_victor_state_to_agent_format(state: Any) -> Dict[str, Any]:
    """Convert Victor AnalysisWorkflowState to agent orchestrator format."""
    # Reusable conversion logic with proper documentation
    ...
```

## Benefits

1. **Single Source of Truth**: One implementation for both CLIs
2. **Easier Maintenance**: Bug fixes apply to both CLIs automatically
3. **Better Testing**: Can test converter independently
4. **Reusability**: Other modules can import and use the converter
5. **Type Safety**: Proper type hints and documentation
6. **Consistency**: Both CLIs produce identical output

## Files Changed

### New Files

1. **`src/investigator/application/victor_result_converter.py`** (NEW)
   - `convert_victor_state_to_agent_format()`: Main converter function
   - `_extract_fundamental_data()`: Fundamental data extraction
   - `_extract_technical_data()`: Technical data extraction
   - `_get_state_attr()`: Safe attribute access helper

### Modified Files

1. **`src/investigator/application/__init__.py`**
   - Added export: `convert_victor_state_to_agent_format`
   - Makes converter accessible via `from investigator.application import ...`

2. **`victor_invest/cli.py`**
   - Refactored `_convert_state_to_agent_format()` to use shared module
   - Reduced from ~100 lines to ~10 lines
   - Maintains same functionality

## Usage Examples

### Basic Usage

```python
from investigator.application import convert_victor_state_to_agent_format

# Convert Victor workflow state
agent_format = convert_victor_state_to_agent_format(state)

# Use with result formatter
from investigator.application import format_analysis_output, OutputDetailLevel
compact = format_analysis_output(agent_format, OutputDetailLevel.COMPACT)
```

### Advanced Usage (Direct Import)

```python
from investigator.application.victor_result_converter import (
    convert_victor_state_to_agent_format,
    _extract_fundamental_data,
    _extract_technical_data,
)

# Convert full state
agent_format = convert_victor_state_to_agent_format(state)

# Or extract specific sections
fundamental = _extract_fundamental_data(state.fundamental_analysis)
technical = _extract_technical_data(state.technical_analysis)
```

## Testing

### Unit Testing the Converter

```python
import pytest
from investigator.application import convert_victor_state_to_agent_format
from victor_invest.workflows import AnalysisWorkflowState, AnalysisMode

def test_converter_basic():
    state = AnalysisWorkflowState(
        symbol="AAPL",
        mode=AnalysisMode.STANDARD,
        # ... other fields ...
    )
    result = convert_victor_state_to_agent_format(state)

    assert result["symbol"] == "AAPL"
    assert result["mode"] == "standard"
    assert "agents" in result
```

### Integration Testing

```python
# Test that compact format works with converter
from investigator.application import (
    convert_victor_state_to_agent_format,
    format_analysis_output,
    OutputDetailLevel,
)

agent_format = convert_victor_state_to_agent_format(state)
compact = format_analysis_output(agent_format, OutputDetailLevel.COMPACT)

assert compact["schema_version"] == "analysis.compact.v1"
```

## Code Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Lines of code** | ~100 (in cli.py) | ~10 (in cli.py) + ~180 (shared) | Reusable module |
| **Duplication** | Yes (cli.py only) | No (shared module) | ✅ Eliminated |
| **Testability** | Hard (embedded in CLI) | Easy (independent module) | ✅ Improved |
| **Maintainability** | Poor (changes in 2 places) | Good (single source) | ✅ Improved |
| **Reusability** | None | High (importable) | ✅ Added |

## Related Documentation

- `COMPACT_FORMAT_SUPPORT.md` - Compact format feature documentation
- `VALUATION_CONSOLIDATION_COMPLETE.md` - Shared valuation services
- `src/investigator/application/victor_result_converter.py` - Implementation

## Migration Notes

For developers maintaining the codebase:

1. **Import the shared converter**:
   ```python
   from investigator.application import convert_victor_state_to_agent_format
   ```

2. **Do not duplicate conversion logic** in new modules
3. **Extend the shared converter** if new transformations are needed
4. **Add tests** for any new conversion logic

## Future Enhancements

Potential improvements:

1. Add validation to ensure converted format has all required fields
2. Add type stubs for better IDE support
3. Add more unit tests for edge cases
4. Add performance benchmarks for large batches
5. Consider adding async version for async workflows
