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

"""Path setup utility for utils module imports.

This module ensures the project root is in sys.path to enable
imports from the utils directory regardless of where the code
is run from.
"""

import sys
from pathlib import Path


def ensure_project_root_in_path() -> None:
    """Ensure project root is in sys.path for utils module imports.

    This function adds the project root directory to sys.path if not
    already present, enabling imports like 'from utils.x import y'
    to work from any working directory.

    The project root is identified by looking for setup.py or
    pyproject.toml in the directory hierarchy.
    """
    # Check if already set up
    if "_project_root_setup_done" in sys.modules:
        return

    # Find project root (look for setup.py or pyproject.toml)
    current_path = Path(__file__).resolve()
    project_root = None

    for parent in [current_path, *current_path.parents]:
        if (parent / "setup.py").exists() or (parent / "pyproject.toml").exists():
            project_root = parent
            break

    if not project_root:
        # Fallback: assume project root is 3 levels up from this file
        # src/investigator/_path_setup.py -> project root
        project_root = current_path.parent.parent.parent

    # Add project root to sys.path if not already there
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)

    # Mark as done to avoid repeated processing
    sys.modules["_project_root_setup_done"] = True


def setup_utils_imports() -> None:
    """Alias for ensure_project_root_in_path() for backward compatibility."""
    ensure_project_root_in_path()


# Auto-setup on import
ensure_project_root_in_path()
