"""The boundary between this package and the victor-ai host must be explicit.

``test_pyproject_framework_is_optional`` asserts that victor-ai is not a base
dependency: the host installs the framework, and this package is a plugin
discovered through entry points. That claim is only meaningful if the surface
reachable without the host is actually defined, so this module pins it:

* **Definition surface** -- ``victor_invest`` and ``victor_invest.vertical``.
  Entry-point discovery loads these before any host is guaranteed, so they must
  import with the host absent.

* **Execution surface** -- ``victor_invest.tools``. These subclass the host's
  ``BaseTool``, so they genuinely cannot load without it. The requirement is not
  that they work, but that they fail *legibly*: a raw
  ``ModuleNotFoundError: No module named 'victor'`` names an internal module and
  no remedy, which is what a user actually saw before this change.

The host is simulated as absent with a meta-path hook rather than by uninstalling
anything, so the tests are hermetic and run in a normal dev environment.
"""

from __future__ import annotations

import builtins
import importlib
import sys

import pytest

HOST_ROOT = "victor"

DEFINITION_SURFACE = ["victor_invest", "victor_invest.vertical"]
EXECUTION_SURFACE = ["victor_invest.tools", "victor_invest.tools.base"]


class _HostBlocker:
    """Make the victor-ai host look uninstalled for the duration of a test."""

    def find_spec(self, name, path=None, target=None):
        if name == HOST_ROOT or name.startswith(f"{HOST_ROOT}."):
            # CPython always populates `name` on ModuleNotFoundError, and the
            # production code keys off it to tell "host absent" from "fault inside
            # the host". Omitting it here made the double lie about real behaviour.
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None


@pytest.fixture
def without_host(monkeypatch):
    """Run the body with the host absent and the affected modules unimported."""
    for name in list(sys.modules):
        if name == HOST_ROOT or name.startswith(f"{HOST_ROOT}.") or name.startswith("victor_invest"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    blocker = _HostBlocker()
    monkeypatch.setattr(sys, "meta_path", [blocker, *sys.meta_path])
    yield


@pytest.mark.parametrize("module", DEFINITION_SURFACE)
def test_definition_surface_imports_without_the_host(without_host, module):
    """Entry-point discovery must not require the framework to be installed."""
    importlib.import_module(module)


@pytest.mark.parametrize("module", EXECUTION_SURFACE)
def test_execution_surface_reports_the_missing_host(without_host, module):
    """Failing here is expected; failing opaquely is not."""
    with pytest.raises(ImportError) as excinfo:
        importlib.import_module(module)

    message = str(excinfo.value)
    assert "victor-invest[runtime]" in message, (
        f"Importing {module} without the host produced {message!r}, which does not tell "
        f"the user how to fix it. It should name the extra that installs the host."
    )
    assert "victor-ai" in message, f"{message!r} should name the missing distribution, not just a module path"


@pytest.mark.parametrize("module", EXECUTION_SURFACE)
def test_missing_host_error_is_catchable_as_importerror(without_host, module):
    """cli.py guards on ImportError, so the richer error must remain a subclass."""
    with pytest.raises(ImportError):
        importlib.import_module(module)


def test_execution_surface_imports_normally_when_the_host_is_present():
    """The diagnostic path must not disturb the ordinary one."""
    for module in EXECUTION_SURFACE:
        assert importlib.import_module(module) is not None


def test_missing_host_error_preserves_the_original_cause(without_host):
    """The underlying ModuleNotFoundError must stay reachable for debugging."""
    with pytest.raises(ImportError) as excinfo:
        importlib.import_module("victor_invest.tools.base")
    assert isinstance(excinfo.value.__cause__, ModuleNotFoundError)


def test_host_error_type_is_exported_for_callers():
    """Callers that want to distinguish this case need a name to catch."""
    from victor_invest._host import MissingVictorHostError

    assert issubclass(MissingVictorHostError, ImportError)
    assert not issubclass(MissingVictorHostError, builtins.SyntaxError)
