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

"""Analyst-grade report assembly for Victor Invest.

A single typed ``AnalystReport`` contract plus a deterministic builder that
surfaces analytics already produced by the analysis pipeline (valuation models,
technical indicators, support/resistance, scenarios, quality flags) into one
coherent, institutional-style report — rendered to markdown and carrying a
provenance manifest. No LLM calls; pure assembly over computed data.
"""

from victor_invest.reporting.builder import build_analyst_report
from victor_invest.reporting.markdown import render_markdown
from victor_invest.reporting.provenance import build_provenance
from victor_invest.reporting.schema import (
    AnalystReport,
    Provenance,
    QualityFlags,
    RatingBlock,
    RiskItem,
    Scenario,
    ScenarioAnalysis,
    TechnicalSetup,
    ValuationModelLine,
    ValuationSummary,
)

__all__ = [
    "AnalystReport",
    "Provenance",
    "QualityFlags",
    "RatingBlock",
    "RiskItem",
    "Scenario",
    "ScenarioAnalysis",
    "TechnicalSetup",
    "ValuationModelLine",
    "ValuationSummary",
    "build_analyst_report",
    "build_provenance",
    "render_markdown",
]
