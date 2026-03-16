"""Compatibility helpers for Victor handler registration APIs.

Supports both:
- Older Victor versions that expose `handler_decorator` and `BaseHandler`
- Newer Victor versions with explicit `register_handler` and no BaseHandler module
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

if TYPE_CHECKING:
    from victor.framework.extensions import ComputeNode, WorkflowContext
    from victor.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# BaseHandler compatibility
# -----------------------------------------------------------------------------

try:
    from victor.framework.workflows.base_handler import BaseHandler
except Exception:

    class BaseHandler:  # type: ignore[no-redef]
        """Compatibility base class for class-based compute handlers."""

        async def execute(
            self,
            node: "ComputeNode",
            context: "WorkflowContext",
            tool_registry: "ToolRegistry",
        ):
            raise NotImplementedError("BaseHandler.execute() must be implemented")

        async def __call__(self, node, context, tool_registry):
            from victor.framework.extensions import ExecutorNodeStatus, NodeResult

            start_time = time.time()
            try:
                output, tool_calls_used = await self.execute(node, context, tool_registry)

                output_key = getattr(node, "output_key", None) or getattr(node, "id", "output")
                if hasattr(context, "set"):
                    context.set(output_key, output)
                elif isinstance(context, dict):
                    context[output_key] = output

                return NodeResult(
                    node_id=node.id,
                    status=ExecutorNodeStatus.COMPLETED,
                    output=output,
                    duration_seconds=time.time() - start_time,
                    tool_calls_used=int(tool_calls_used or 0),
                )
            except Exception as exc:
                return NodeResult(
                    node_id=getattr(node, "id", "unknown"),
                    status=ExecutorNodeStatus.FAILED,
                    error=str(exc),
                    duration_seconds=time.time() - start_time,
                    tool_calls_used=0,
                )


# -----------------------------------------------------------------------------
# handler_decorator compatibility
# -----------------------------------------------------------------------------

try:
    from victor.framework.handler_registry import handler_decorator as handler_decorator
except Exception:
    _T = TypeVar("_T")

    def _register_with_handler_registry(
        name: str,
        instance: Any,
        vertical: Optional[str],
        description: Optional[str],
    ) -> None:
        try:
            # Try new Victor API first (register_vertical_handlers, register_global_handler)
            from victor.framework.handler_registry import (
                register_global_handler,
                register_vertical_handlers,
            )

            if vertical:
                # Register as vertical handler
                register_vertical_handlers(
                    vertical_name=vertical,
                    handlers={name: instance},
                    category="general",
                    description=description or "",
                )
            else:
                # Register as global handler
                register_global_handler(
                    name=name,
                    handler=instance,
                    category="global",
                )
        except Exception:
            # Fallback to old Victor 0.5.0 API (get_handler_registry())
            try:
                from victor.framework.handler_registry import get_handler_registry

                registry = get_handler_registry()
                if vertical:
                    # Old API: register_vertical(vertical_name, handlers_dict)
                    registry.register_vertical(
                        vertical_name=vertical,
                        handlers={name: instance},
                        category="general",
                        description=description or "",
                    )
                else:
                    # Old API: register_global(name, handler)
                    registry.register_global(
                        name=name,
                        handler=instance,
                        category="global",
                    )
            except Exception as exc:
                logger.debug("Handler registry registration skipped for %s: %s", name, exc)

    def _register_with_executor(name: str, instance: Any) -> None:
        try:
            from victor.framework.extensions import register_compute_handler

            register_compute_handler(name, instance)
        except Exception as exc:
            logger.debug("Executor registration skipped for %s: %s", name, exc)

    def handler_decorator(
        name: str,
        *,
        vertical: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable[[type[_T]], type[_T]]:
        """Decorator compatibility shim for class-based handlers."""

        def _decorator(handler_cls: type[_T]) -> type[_T]:
            try:
                instance = handler_cls()
            except Exception as exc:
                logger.warning("Could not instantiate handler %s for registration: %s", name, exc)
                return handler_cls

            _register_with_handler_registry(name, instance, vertical, description)
            _register_with_executor(name, instance)
            return handler_cls

        return _decorator


__all__ = ["BaseHandler", "handler_decorator"]
