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

"""Enhanced conversation management for victor-invest using ConversationCoordinator.

This module provides investment/finance-specific conversation management features using
the framework's ConversationCoordinator for better context tracking and
summarization.

Design Pattern: Extension + Delegation
- Provides investment-specific conversation management
- Delegates to framework ConversationCoordinator
- Tracks investment-specific context (trades analyzed, decisions tracked, portfolio changes)

Integration Point:
    Use in InvestAssistant for enhanced conversation tracking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from victor.agent.coordinators.conversation_coordinator import (
    ConversationCoordinator,
    ConversationStats,
    TurnType,
)

logger = logging.getLogger(__name__)


@dataclass
class InvestmentContext:
    """Investment/Finance-specific conversation context.

    Tracks:
    - Trades analyzed and discussed
    - Investment decisions made
    - Portfolio changes considered
    - Risk assessments performed
    - Research and analysis conducted
    - Market data consulted

    Attributes:
        trades_analyzed: List of trades analyzed
        investment_decisions: List of investment decisions tracked
        portfolio_considerations: List of portfolio change considerations
        risk_assessments: List of risk assessments performed
        research_conducted: List of research and analysis activities
        market_data_sources: List of market data sources consulted
        watchlist_updates: List of watchlist additions/removals
    """

    trades_analyzed: List[Dict[str, Any]] = field(default_factory=list)
    investment_decisions: List[Dict[str, Any]] = field(default_factory=list)
    portfolio_considerations: List[Dict[str, Any]] = field(default_factory=list)
    risk_assessments: List[Dict[str, Any]] = field(default_factory=list)
    research_conducted: List[Dict[str, Any]] = field(default_factory=list)
    market_data_sources: List[str] = field(default_factory=list)
    watchlist_updates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trades_analyzed": self.trades_analyzed,
            "investment_decisions": self.investment_decisions,
            "portfolio_considerations": self.portfolio_considerations,
            "risk_assessments": self.risk_assessments,
            "research_conducted": self.research_conducted,
            "market_data_sources": self.market_data_sources,
            "watchlist_updates": self.watchlist_updates,
        }

    def add_trade_analyzed(
        self,
        symbol: str,
        action: str,
        analysis_type: str,
        conclusion: str,
    ) -> None:
        """Record a trade analysis.

        Args:
            symbol: Trading symbol
            action: Buy/Sell/Hold
            analysis_type: Technical, Fundamental, etc.
            conclusion: Analysis conclusion
        """
        self.trades_analyzed.append(
            {
                "symbol": symbol,
                "action": action,
                "analysis_type": analysis_type,
                "conclusion": conclusion,
            }
        )
        logger.debug(f"Recorded trade analysis: {action} {symbol} ({analysis_type})")

    def add_investment_decision(
        self,
        decision: str,
        symbol: Optional[str] = None,
        rationale: str = "",
    ) -> None:
        """Record an investment decision.

        Args:
            decision: Decision made (buy, sell, hold, wait)
            symbol: Optional symbol
            rationale: Rationale for the decision
        """
        self.investment_decisions.append(
            {
                "decision": decision,
                "symbol": symbol,
                "rationale": rationale,
            }
        )
        logger.debug(f"Recorded investment decision: {decision}")

    def add_portfolio_consideration(
        self,
        consideration: str,
        impact: str = "unknown",
    ) -> None:
        """Record a portfolio change consideration.

        Args:
            consideration: What was considered
            impact: Expected impact
        """
        self.portfolio_considerations.append(
            {
                "consideration": consideration,
                "impact": impact,
            }
        )
        logger.debug(f"Recorded portfolio consideration: {consideration}")

    def add_risk_assessment(
        self,
        risk_type: str,
        level: str,
        mitigation: str = "",
    ) -> None:
        """Record a risk assessment.

        Args:
            risk_type: Type of risk (market, credit, liquidity, etc.)
            level: Risk level (low, medium, high, extreme)
            mitigation: Mitigation strategy
        """
        self.risk_assessments.append(
            {
                "risk_type": risk_type,
                "level": level,
                "mitigation": mitigation,
            }
        )
        logger.debug(f"Recorded risk assessment: {risk_type} ({level})")


class EnhancedInvestConversationManager:
    """Enhanced conversation manager for Investments using ConversationCoordinator.

    Provides:
    - Standard conversation tracking via ConversationCoordinator
    - Investment-specific context tracking (trades, decisions, risk, research)
    - Automatic summarization of investment work
    - Investment-focused conversation history

    Example:
        manager = EnhancedInvestConversationManager()

        # Add a user message
        manager.add_message("user", "Should I buy AAPL stock?", TurnType.USER)

        # Track analysis
        manager.track_trade_analyzed("AAPL", "buy", "Technical", "Bullish trend")

        # Track decision
        manager.track_investment_decision("hold", "AAPL", "Wait for better entry point")

        # Get conversation summary
        summary = manager.get_investment_summary()
    """

    def __init__(
        self,
        max_history_turns: int = 50,
        summarization_threshold: int = 40,
        enable_deduplication: bool = True,
        enable_statistics: bool = True,
    ):
        """Initialize the enhanced conversation manager.

        Args:
            max_history_turns: Maximum turns to keep in history
            summarization_threshold: Turns before triggering summarization
            enable_deduplication: Whether to enable message deduplication
            enable_statistics: Whether to track conversation statistics
        """
        self._conversation_coordinator = ConversationCoordinator(
            max_history_turns=max_history_turns,
            summarization_threshold=summarization_threshold,
            enable_deduplication=enable_deduplication,
            enable_statistics=enable_statistics,
        )

        self._investment_context = InvestmentContext()

        logger.info(
            f"EnhancedInvestConversationManager initialized with "
            f"max_turns={max_history_turns}"
        )

    # =========================================================================
    # Message Management (delegates to ConversationCoordinator)
    # =========================================================================

    def add_message(
        self,
        role: str,
        content: str,
        turn_type: TurnType,
        metadata: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Add a message to the conversation.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
            turn_type: Type of turn
            metadata: Optional metadata
            tool_calls: Optional tool calls made in this turn

        Returns:
            Turn ID for the added message
        """
        return self._conversation_coordinator.add_message(
            role, content, turn_type, metadata, tool_calls
        )

    def get_history(
        self,
        max_turns: Optional[int] = None,
        include_system: bool = True,
        include_tool: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get conversation history.

        Args:
            max_turns: Maximum number of turns to return
            include_system: Whether to include system messages
            include_tool: Whether to include tool messages

        Returns:
            List of message dictionaries
        """
        return self._conversation_coordinator.get_history(
            max_turns, include_system, include_tool
        )

    def clear_history(self, keep_summaries: bool = True) -> None:
        """Clear conversation history.

        Args:
            keep_summaries: Whether to keep conversation summaries
        """
        self._conversation_coordinator.clear_history(keep_summaries)
        if not keep_summaries:
            self._investment_context = InvestmentContext()
        logger.info("Conversation history cleared")

    # =========================================================================
    # Investment-Specific Context Tracking
    # =========================================================================

    def track_trade_analyzed(
        self,
        symbol: str,
        action: str,
        analysis_type: str,
        conclusion: str,
    ) -> None:
        """Track a trade analysis.

        Args:
            symbol: Trading symbol
            action: Buy/Sell/Hold
            analysis_type: Technical, Fundamental, etc.
            conclusion: Analysis conclusion
        """
        self._investment_context.add_trade_analyzed(
            symbol, action, analysis_type, conclusion
        )

    def track_investment_decision(
        self,
        decision: str,
        symbol: Optional[str] = None,
        rationale: str = "",
    ) -> None:
        """Track an investment decision.

        Args:
            decision: Decision made (buy, sell, hold, wait)
            symbol: Optional symbol
            rationale: Rationale for the decision
        """
        self._investment_context.add_investment_decision(decision, symbol, rationale)

    def track_portfolio_consideration(
        self,
        consideration: str,
        impact: str = "unknown",
    ) -> None:
        """Track a portfolio change consideration.

        Args:
            consideration: What was considered
            impact: Expected impact
        """
        self._investment_context.add_portfolio_consideration(consideration, impact)

    def track_risk_assessment(
        self,
        risk_type: str,
        level: str,
        mitigation: str = "",
    ) -> None:
        """Track a risk assessment.

        Args:
            risk_type: Type of risk
            level: Risk level
            mitigation: Mitigation strategy
        """
        self._investment_context.add_risk_assessment(risk_type, level, mitigation)

    # =========================================================================
    # Summarization
    # =========================================================================

    def needs_summarization(self) -> bool:
        """Check if conversation needs summarization.

        Returns:
            True if summarization is recommended
        """
        return self._conversation_coordinator.needs_summarization()

    def add_summary(self, summary: str) -> None:
        """Add a conversation summary.

        Args:
            summary: Summary text
        """
        self._conversation_coordinator.add_summary(summary)

    def get_investment_summary(self) -> str:
        """Get an investment-focused conversation summary.

        Returns:
            Formatted summary of investment work done
        """
        parts = []

        ctx = self._investment_context

        # Trades analyzed
        if ctx.trades_analyzed:
            parts.append("## Trades Analyzed")
            for trade in ctx.trades_analyzed:
                parts.append(
                    f"- {trade['action']} {trade['symbol']} ({trade['analysis_type']}): {trade['conclusion']}"
                )
            parts.append("")

        # Investment decisions
        if ctx.investment_decisions:
            parts.append("## Investment Decisions")
            for decision in ctx.investment_decisions:
                symbol = f" {decision['symbol']}" if decision.get("symbol") else ""
                parts.append(
                    f"- {decision['decision']}{symbol}: {decision.get('rationale', '')}"
                )
            parts.append("")

        # Risk assessments
        if ctx.risk_assessments:
            parts.append("## Risk Assessments")
            for risk in ctx.risk_assessments:
                mitigation = (
                    f" (mitigation: {risk['mitigation']})"
                    if risk.get("mitigation")
                    else ""
                )
                parts.append(f"- {risk['risk_type']}: {risk['level']}{mitigation}")
            parts.append("")

        # Conversation stats
        stats = self._conversation_coordinator.get_stats()
        parts.append("## Conversation Stats")
        parts.append(f"- Total turns: {stats.total_turns}")
        parts.append(f"- User turns: {stats.user_turns}")
        parts.append(f"- Assistant turns: {stats.assistant_turns}")
        parts.append(f"- Tool calls: {stats.tool_calls}")

        return "\n".join(parts)

    # =========================================================================
    # Statistics and Observability
    # =========================================================================

    def get_stats(self) -> ConversationStats:
        """Get conversation statistics.

        Returns:
            ConversationStats object
        """
        return self._conversation_coordinator.get_stats()

    def get_investment_context(self) -> InvestmentContext:
        """Get the investment context.

        Returns:
            InvestmentContext object
        """
        return self._investment_context

    def get_observability_data(self) -> Dict[str, Any]:
        """Get observability data for dashboard integration.

        Returns:
            Dictionary with observability data
        """
        conv_obs = self._conversation_coordinator.get_observability_data()

        return {
            **conv_obs,
            "investment_context": self._investment_context.to_dict(),
            "vertical": "invest",
        }

    def get_conversation_coordinator(self) -> ConversationCoordinator:
        """Get the underlying ConversationCoordinator.

        Returns:
            ConversationCoordinator instance
        """
        return self._conversation_coordinator


__all__ = [
    "InvestmentContext",
    "EnhancedInvestConversationManager",
]
