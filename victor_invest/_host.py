"""Explicit boundary between this package and the victor-ai host runtime.

This package declares ``victor-ai`` an *optional* dependency: it is a plugin, and
the host that loads it supplies the framework. That split is intentional and is
asserted by ``test_pyproject_framework_is_optional``.

The consequence is that part of this package is reachable without the host and
part is not:

* the **definition** surface -- package metadata, the vertical, the plugin object
  -- must import host-free, because entry-point discovery loads it before any
  host is guaranteed;
* the **execution** surface -- the tools, which subclass the host's ``BaseTool``
  -- cannot, because the base class itself lives in the host.

The second case is legitimate. Reporting it as a bare
``ModuleNotFoundError: No module named 'victor'`` is not: that names an internal
module, not the distribution that is missing, and offers no remedy. This module
converts it into an error that says which surface needed the host and how to
install it, while keeping the original exception as ``__cause__``.
"""

from __future__ import annotations

RUNTIME_EXTRA = "victor-invest[runtime]"
HOST_DISTRIBUTION = "victor-ai"


class MissingVictorHostError(ImportError):
    """A surface required the victor-ai host runtime and it is not installed.

    Subclasses :class:`ImportError` deliberately: existing callers guard on
    ``except ImportError`` (see ``victor_invest/cli.py``) and must keep working.
    """

    def __init__(self, surface: str, module: str) -> None:
        super().__init__(
            f"{surface} requires the Victor host runtime, which is not installed: "
            f"could not import {module!r} from the {HOST_DISTRIBUTION} distribution. "
            f"This package declares {HOST_DISTRIBUTION} optional because the host "
            f"normally provides it. To use this surface standalone, install: "
            f"pip install '{RUNTIME_EXTRA}'"
        )
        self.surface = surface
        self.module = module


def is_missing_host(exc: ModuleNotFoundError) -> bool:
    """Whether *exc* is the host being absent, rather than a fault inside it.

    A missing dependency *within* victor-ai is a different problem and must keep
    its own traceback instead of being relabelled as "host not installed".
    """
    name = exc.name or ""
    return name == "victor" or name.startswith("victor.")
