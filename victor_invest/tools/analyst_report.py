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

"""Analyst report tool.

Assembles a typed, institutional-style :class:`AnalystReport` from an analysis
result (AnalysisWorkflowState or its dict form) and returns both the structured
report and a rendered markdown document. Deterministic; never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from victor_invest.reporting import build_analyst_report, render_markdown
from victor_invest.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class AnalystReportTool(BaseTool):
    """Build an institutional-style analyst report from an analysis result."""

    name = "analyst_report"
    description = (
        "Assemble a typed analyst report (rating, valuation with fair-value range, "
        "scenario analysis, technical setup, financial-health screens, provenance) "
        "from an analysis result and render it to markdown."
    )

    async def execute(
        self,
        _exec_ctx: Optional[Dict[str, Any]] = None,
        state: Optional[Any] = None,
        as_of: Optional[str] = None,
        render: bool = True,
        **kwargs: Any,
    ) -> ToolResult:
        """Build the report.

        Args:
            state: AnalysisWorkflowState or dict (synthesis/fundamental/technical/...).
            as_of: Optional data as-of date string for provenance.
            render: When True, also include rendered markdown in the output.
        """
        try:
            if state is None:
                return ToolResult.create_failure("analyst_report requires an analysis 'state'")
            report = build_analyst_report(state, data_as_of=as_of)
            output: Dict[str, Any] = {"report": report.to_dict()}
            if render:
                output["markdown"] = render_markdown(report)
            return ToolResult.create_success(
                output=output,
                metadata={"tool": self.name, "symbol": report.symbol},
            )
        except Exception as exc:  # noqa: BLE001 - tools never raise
            logger.error("AnalystReportTool failed: %s", exc)
            return ToolResult.create_failure(str(exc))
