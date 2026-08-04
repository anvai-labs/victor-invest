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

"""Enhanced safety integration for victor-invest using SafetyCoordinator.

This module provides investment/finance-specific safety rules and integration with
the framework's SafetyCoordinator for enhanced safety enforcement.

Design Pattern: Extension + Delegation
- Defines investment-specific safety rules
- Registers them with SafetyCoordinator
- Provides safety checking interface for investment operations

Integration Point:
    Use in InvestAssistant.get_extensions() as enhanced safety extension
"""

from __future__ import annotations

import logging
from typing import Any

from victor_contracts.safety import SafetyAction, SafetyCategory, SafetyCoordinator, SafetyRule
from victor_contracts.verticals.protocols import SafetyExtensionProtocol
from victor_contracts.verticals.protocols.promoted_types import SafetyPatternData as SafetyPattern

logger = logging.getLogger(__name__)


class InvestmentSafetyRules:
    """Investment/Finance-specific safety rules for the SafetyCoordinator.

    Provides comprehensive safety rules for investment operations including:
    - Trading operations (no real money without explicit confirmation)
    - Portfolio operations (destructive changes blocked)
    - Data privacy (financial information protection)
    - Risk level warnings (high-risk investment strategies)
    """

    @staticmethod
    def get_trading_rules() -> list[SafetyRule]:
        """Get trading safety rules.

        Returns:
            List of safety rules for trading operations
        """
        return [
            # Real money trading is BLOCKED without confirmation
            SafetyRule(
                rule_id="invest_real_money_trade",
                category=SafetyCategory.SHELL,
                pattern=r"trade.*--real|buy.*--live|execute.*order.*production",
                description="Execute real money trade",
                action=SafetyAction.BLOCK,
                severity=10,
                tool_names=["shell", "execute_bash", "trading"],
            ),
            # High-risk trading strategies require confirmation
            SafetyRule(
                rule_id="invest_high_risk_strategy",
                category=SafetyCategory.SHELL,
                pattern=r"(leverage|margin|short|option|futures).*--high|strategy.*--aggressive",
                description="High-risk trading strategy (leverage, short, options)",
                action=SafetyAction.REQUIRE_CONFIRMATION,
                severity=8,
                confirmation_prompt="This is a high-risk strategy. Ensure you understand the risks. Continue?",
                tool_names=["shell", "execute_bash", "trading"],
            ),
            # Bulk trading operations require confirmation
            SafetyRule(
                rule_id="invest_bulk_trading",
                category=SafetyCategory.SHELL,
                pattern=r"trade.*--bulk|order.*multiple|execute.*--all",
                description="Bulk trading operations",
                action=SafetyAction.REQUIRE_CONFIRMATION,
                severity=7,
                confirmation_prompt="This will execute multiple trades. Review carefully. Continue?",
                tool_names=["shell", "execute_bash", "trading"],
            ),
        ]

    @staticmethod
    def get_portfolio_rules() -> list[SafetyRule]:
        """Get portfolio management safety rules.

        Returns:
            List of safety rules for portfolio operations
        """
        return [
            # Deleting portfolio data is BLOCKED
            SafetyRule(
                rule_id="invest_delete_portfolio",
                category=SafetyCategory.FILE,
                pattern=r"delete.*portfolio|drop.*holdings|wipe.*positions",
                description="Delete portfolio or holdings data",
                action=SafetyAction.BLOCK,
                severity=10,
                tool_names=["shell", "execute_bash", "file_ops"],
            ),
            # Overwriting portfolio records requires confirmation
            SafetyRule(
                rule_id="invest_overwrite_portfolio",
                category=SafetyCategory.FILE,
                pattern=r"overwrite.*portfolio|update.*holdings.*--force",
                description="Overwrite portfolio records",
                action=SafetyAction.REQUIRE_CONFIRMATION,
                severity=8,
                confirmation_prompt="This will modify portfolio records. Consider backing up. Continue?",
                tool_names=["shell", "execute_bash", "file_ops"],
            ),
            # Rebalancing entire portfolio requires confirmation
            SafetyRule(
                rule_id="invest_rebalance_all",
                category=SafetyCategory.SHELL,
                pattern=r"rebalance.*--all|restructure.*portfolio",
                description="Rebalance or restructure entire portfolio",
                action=SafetyAction.REQUIRE_CONFIRMATION,
                severity=6,
                confirmation_prompt="Portfolio rebalancing will trigger many trades. Review carefully. Continue?",
                tool_names=["shell", "execute_bash", "trading"],
            ),
        ]

    @staticmethod
    def get_data_privacy_rules() -> list[SafetyRule]:
        """Get financial data privacy safety rules.

        Returns:
            List of safety rules for data privacy
        """
        return [
            # Sharing financial data requires confirmation
            SafetyRule(
                rule_id="invest_share_financial_data",
                category=SafetyCategory.SHELL,
                pattern=r"share.*portfolio|upload.*transactions|publish.*holdings",
                description="Share or upload financial data",
                action=SafetyAction.REQUIRE_CONFIRMATION,
                severity=9,
                confirmation_prompt="This may expose sensitive financial information. Ensure consent and privacy compliance. Continue?",
                tool_names=["shell", "execute_bash", "web", "file_ops"],
            ),
            # Exporting account credentials is BLOCKED
            SafetyRule(
                rule_id="invest_export_credentials",
                category=SafetyCategory.FILE,
                pattern=r"export.*api.*key|save.*credentials|write.*.*password",
                description="Export account credentials or API keys",
                action=SafetyAction.BLOCK,
                severity=10,
                tool_names=["shell", "execute_bash", "file_ops"],
            ),
        ]

    @staticmethod
    def get_api_rules() -> list[SafetyRule]:
        """Get API access safety rules.

        Returns:
            List of safety rules for API operations
        """
        return [
            # Bulk API calls require confirmation
            SafetyRule(
                rule_id="invest_bulk_api_calls",
                category=SafetyCategory.SHELL,
                pattern=r"api.*call.*bulk|query.*--all.*tickers|fetch.*--multiple",
                description="Bulk API calls to financial data providers",
                action=SafetyAction.WARN,
                severity=5,
                tool_names=["shell", "execute_bash", "web"],
            ),
            # High-frequency trading pattern requires confirmation
            SafetyRule(
                rule_id="invest_hft_pattern",
                category=SafetyCategory.SHELL,
                pattern=r"(hft|high.*frequency|microsecond|millisecond).*trading",
                description="High-frequency trading pattern detected",
                action=SafetyAction.REQUIRE_CONFIRMATION,
                severity=7,
                confirmation_prompt="HFT requires specialized infrastructure and approval. Continue?",
                tool_names=["shell", "execute_bash", "trading"],
            ),
        ]

    @staticmethod
    def get_all_rules() -> list[SafetyRule]:
        """Get all investment-specific safety rules.

        Returns:
            List of all safety rules for investment operations
        """
        rules = []
        rules.extend(InvestmentSafetyRules.get_trading_rules())
        rules.extend(InvestmentSafetyRules.get_portfolio_rules())
        rules.extend(InvestmentSafetyRules.get_data_privacy_rules())
        rules.extend(InvestmentSafetyRules.get_api_rules())
        return rules


class EnhancedInvestSafetyExtension(SafetyExtensionProtocol):
    """Enhanced safety extension for Investments using SafetyCoordinator.

    This class provides the SafetyExtensionProtocol interface while
    delegating to the framework's SafetyCoordinator for actual
    safety checking.

    Example:
        extension = EnhancedInvestSafetyExtension()

        # Check if an operation is safe
        result = extension.check_operation("trading", ["buy", "--real", "AAPL"])
        if not result.is_safe:
            print(f"Blocked: {result.block_reason}")
    """

    def __init__(
        self,
        strict_mode: bool = False,
        enable_custom_rules: bool = True,
    ):
        """Initialize the enhanced safety extension.

        Args:
            strict_mode: If True, treat warnings as blocks
            enable_custom_rules: If True, enable custom investment-specific rules
        """
        self._strict_mode = strict_mode
        self._enable_custom_rules = enable_custom_rules

        # Create SafetyCoordinator with investment-specific rules
        self._coordinator = SafetyCoordinator(
            strict_mode=strict_mode,
            enable_default_rules=True,
        )

        # Register investment-specific rules
        if enable_custom_rules:
            for rule in InvestmentSafetyRules.get_all_rules():
                self._coordinator.register_rule(rule)

        logger.info(
            f"EnhancedInvestSafetyExtension initialized with {len(self._coordinator.list_rules())} safety rules"
        )

    def check_operation(
        self,
        tool_name: str,
        args: list[str],
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Check if an operation is safe.

        Args:
            tool_name: Name of the tool being called
            args: Arguments to the tool
            context: Optional context for the check

        Returns:
            SafetyCheckResult from the coordinator
        """
        return self._coordinator.check_safety(tool_name, args, context)

    def is_operation_safe(
        self,
        tool_name: str,
        args: list[str],
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Quick check if an operation is safe.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            context: Optional context

        Returns:
            True if operation is safe, False otherwise
        """
        return self._coordinator.is_operation_safe(tool_name, args, context)  # type: ignore[no-any-return]

    def get_bash_patterns(self) -> list[SafetyPattern]:
        """Get investment-specific bash command patterns.

        Returns:
            List of safety patterns for dangerous bash commands
        """
        return []

    def get_file_patterns(self) -> list[SafetyPattern]:
        """Get investment-specific file operation patterns.

        Returns:
            List of safety patterns for file operations
        """
        return []

    def get_tool_restrictions(self) -> dict[str, list[str]]:
        """Get tool-specific argument restrictions.

        Returns:
            Dictionary mapping tool names to restricted arguments
        """
        return {
            "trading": ["buy --real", "sell --real", "trade --live"],
            "shell": ["rm -rf portfolio/*", "delete holdings/*"],
        }

    def get_coordinator(self) -> SafetyCoordinator:
        """Get the underlying SafetyCoordinator.

        Returns:
            SafetyCoordinator instance
        """
        return self._coordinator

    def add_custom_rule(self, rule: SafetyRule) -> None:
        """Add a custom safety rule.

        Args:
            rule: Safety rule to add
        """
        self._coordinator.register_rule(rule)
        logger.debug(f"Added custom safety rule: {rule.rule_id}")

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a safety rule.

        Args:
            rule_id: ID of the rule to remove

        Returns:
            True if rule was removed, False if not found
        """
        return self._coordinator.unregister_rule(rule_id)  # type: ignore[no-any-return]

    def get_safety_stats(self) -> dict[str, Any]:
        """Get safety statistics.

        Returns:
            Dictionary with safety statistics
        """
        return self._coordinator.get_stats_dict()  # type: ignore[no-any-return]


def create_investment_safety_rules() -> EnhancedInvestSafetyExtension:
    """Entry point factory for victor.safety_rules."""
    return EnhancedInvestSafetyExtension()


__all__ = [
    "EnhancedInvestSafetyExtension",
    "InvestmentSafetyRules",
    "create_investment_safety_rules",
]
