#!/usr/bin/env python3
"""
InvestiGator - LLM Processing Interfaces
Copyright (c) 2025 Vijaykumar Singh
Licensed under the Apache License 2.0

LLM Processing Interfaces and Abstract Classes
Defines contracts for pattern-based LLM operations
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

# ============================================================================
# LLM Data Models
# ============================================================================


@dataclass
class LLMRequest:
    """LLM request with metadata"""

    model: str
    prompt: str
    system_prompt: str | None = None
    temperature: float = 0.3
    top_p: float = 0.9
    num_ctx: int | None = None
    num_predict: int | None = None
    timeout: int | None = None
    metadata: dict[str, Any] | None = None
    priority: int = 5  # 1=highest, 10=lowest
    request_id: str | None = None
    timestamp: datetime | None = None


@dataclass
class LLMResponse:
    """LLM response with processing info"""

    content: str
    model: str
    processing_time_ms: int
    tokens_used: int | None = None
    metadata: dict[str, Any] | None = None
    error: str | None = None
    request_id: str | None = None
    timestamp: datetime | None = None


class LLMTaskType(Enum):
    """Types of LLM analysis tasks"""

    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    TECHNICAL_ANALYSIS = "technical_analysis"
    SYNTHESIS = "synthesis"
    QUARTERLY_SUMMARY = "quarterly_summary"
    COMPREHENSIVE_ANALYSIS = "comprehensive_analysis"
    RISK_ASSESSMENT = "risk_assessment"


class LLMPriority(Enum):
    """LLM request priorities"""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 5
    LOW = 8
    BACKGROUND = 10


# ============================================================================
# Strategy Pattern Interfaces
# ============================================================================


class ILLMStrategy(ABC):
    """Strategy interface for different LLM analysis approaches"""

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get strategy identifier"""

    @abstractmethod
    def prepare_request(self, task_type: LLMTaskType, data: dict[str, Any]) -> LLMRequest:
        """Prepare LLM request for specific task"""

    @abstractmethod
    def process_response(self, response: LLMResponse, task_type: LLMTaskType) -> dict[str, Any]:
        """Process LLM response into structured data"""

    @abstractmethod
    def get_model_for_task(self, task_type: LLMTaskType) -> str:
        """Get appropriate model for task type"""


class ILLMProcessor(ABC):
    """Processor interface for executing LLM requests"""

    @abstractmethod
    def process_request(self, request: LLMRequest) -> LLMResponse:
        """Process a single LLM request"""

    @abstractmethod
    def process_batch(self, requests: list[LLMRequest]) -> list[LLMResponse]:
        """Process multiple LLM requests"""

    @abstractmethod
    def get_queue_size(self) -> int:
        """Get current queue size"""


# ============================================================================
# Chain of Responsibility Interfaces
# ============================================================================


class ILLMHandler(ABC):
    """Handler interface for LLM processing chain"""

    def __init__(self):
        self._next_handler: ILLMHandler | None = None

    def set_next(self, handler: "ILLMHandler") -> "ILLMHandler":
        """Set next handler in chain"""
        self._next_handler = handler
        return handler

    @abstractmethod
    def handle(self, request: LLMRequest) -> LLMResponse | None:
        """Handle LLM request or pass to next handler"""

    def _handle_next(self, request: LLMRequest) -> LLMResponse | None:
        """Pass request to next handler if exists"""
        if self._next_handler:
            return self._next_handler.handle(request)
        return None


# ============================================================================
# Observer Pattern Interfaces
# ============================================================================


class ILLMObserver(ABC):
    """Observer interface for LLM processing events"""

    @abstractmethod
    def on_request_queued(self, request: LLMRequest) -> None:
        """Called when request is added to queue"""

    @abstractmethod
    def on_processing_started(self, request: LLMRequest) -> None:
        """Called when processing starts"""

    @abstractmethod
    def on_processing_completed(self, request: LLMRequest, response: LLMResponse) -> None:
        """Called when processing completes"""

    @abstractmethod
    def on_processing_error(self, request: LLMRequest, error: Exception) -> None:
        """Called when processing fails"""


class ILLMSubject(ABC):
    """Subject interface for LLM processing events"""

    @abstractmethod
    def attach(self, observer: ILLMObserver) -> None:
        """Attach observer"""

    @abstractmethod
    def detach(self, observer: ILLMObserver) -> None:
        """Detach observer"""

    @abstractmethod
    def notify_queued(self, request: LLMRequest) -> None:
        """Notify observers of queued request"""

    @abstractmethod
    def notify_started(self, request: LLMRequest) -> None:
        """Notify observers of started processing"""

    @abstractmethod
    def notify_completed(self, request: LLMRequest, response: LLMResponse) -> None:
        """Notify observers of completed processing"""

    @abstractmethod
    def notify_error(self, request: LLMRequest, error: Exception) -> None:
        """Notify observers of processing error"""


# ============================================================================
# Template Method Interfaces
# ============================================================================


class ILLMAnalysisTemplate(ABC):
    """Template method interface for standardized analysis workflows"""

    def analyze(self, symbol: str, data: dict[str, Any], task_type: LLMTaskType) -> dict[str, Any]:
        """Template method for analysis workflow"""
        # Validate input
        if not self.validate_input(symbol, data, task_type):
            return self.create_error_result("Invalid input data")

        # Prepare request
        request = self.prepare_analysis_request(symbol, data, task_type)

        # Execute analysis
        response = self.execute_analysis(request)

        # Process results
        return self.process_analysis_results(response, task_type)

    @abstractmethod
    def validate_input(self, symbol: str, data: dict[str, Any], task_type: LLMTaskType) -> bool:
        """Validate input parameters"""

    @abstractmethod
    def prepare_analysis_request(self, symbol: str, data: dict[str, Any], task_type: LLMTaskType) -> LLMRequest:
        """Prepare LLM request for analysis"""

    @abstractmethod
    def execute_analysis(self, request: LLMRequest) -> LLMResponse:
        """Execute the analysis request"""

    @abstractmethod
    def process_analysis_results(self, response: LLMResponse, task_type: LLMTaskType) -> dict[str, Any]:
        """Process and format analysis results"""

    @abstractmethod
    def create_error_result(self, error_message: str) -> dict[str, Any]:
        """Create standardized error result"""


# ============================================================================
# Factory Interfaces
# ============================================================================


class ILLMFactory(ABC):
    """Factory interface for creating LLM components"""

    @abstractmethod
    def create_strategy(self, strategy_type: str, config: Any) -> ILLMStrategy:
        """Create LLM strategy instance"""

    @abstractmethod
    def create_processor(self, processor_type: str, config: Any) -> ILLMProcessor:
        """Create LLM processor instance"""

    @abstractmethod
    def create_handler_chain(self, config: Any) -> ILLMHandler:
        """Create handler chain for processing"""

    @abstractmethod
    def create_observer(self, observer_type: str, config: Any) -> ILLMObserver:
        """Create LLM observer instance"""


# ============================================================================
# Cache Integration Interfaces
# ============================================================================


class ILLMCacheStrategy(ABC):
    """Cache strategy interface for LLM responses"""

    @abstractmethod
    def get_cache_key(self, request: LLMRequest) -> str:
        """Generate cache key for request"""

    @abstractmethod
    def should_cache(self, request: LLMRequest, response: LLMResponse) -> bool:
        """Determine if response should be cached"""

    @abstractmethod
    def get_ttl(self, task_type: LLMTaskType) -> int:
        """Get cache TTL for task type"""

    @abstractmethod
    def is_cacheable_task(self, task_type: LLMTaskType) -> bool:
        """Check if task type is cacheable"""
