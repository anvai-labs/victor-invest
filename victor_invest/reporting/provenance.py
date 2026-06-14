# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
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

"""Reproducibility manifest for analyst reports."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Optional

from victor_invest.reporting.schema import Provenance


def _git_sha() -> Optional[str]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        ).stdout.strip()
        return sha or None
    except Exception:
        return None


def _config_version() -> Optional[str]:
    try:
        from investigator.config import get_config

        config = get_config()
        version = getattr(config, "version", None)
        if version:
            return str(version)
        # config may be a dict-like
        getter = getattr(config, "get", None)
        if callable(getter):
            value = getter("version") or getter("config_version")
            return str(value) if value else None
    except Exception:
        return None
    return None


def build_provenance(
    *,
    data_as_of: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    workflow_mode: Optional[str] = None,
    synthesis_method: Optional[str] = None,
) -> Provenance:
    """Assemble a provenance manifest (code SHA, config version, timestamps, model)."""
    return Provenance(
        generated_at=datetime.now(timezone.utc).isoformat(),
        code_sha=_git_sha(),
        config_version=_config_version(),
        data_as_of=data_as_of,
        llm_provider=llm_provider,
        llm_model=llm_model,
        workflow_mode=workflow_mode,
        synthesis_method=synthesis_method,
    )
