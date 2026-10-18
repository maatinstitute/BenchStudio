from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterCapabilities:
    command_acknowledgment: bool = False
    queue_consumption_feedback: bool = False
    execution_timestamps: bool = False
    zero_order_hold: bool = False
    asynchronous_action_queue: bool = False


def validate_adapter_capabilities(
    capabilities: AdapterCapabilities, *, require_execution_timestamps: bool = False
) -> list[str]:
    issues: list[str] = []
    if capabilities.queue_consumption_feedback and not capabilities.asynchronous_action_queue:
        issues.append("queue_consumption_feedback requires asynchronous_action_queue")
    if capabilities.command_acknowledgment and not capabilities.execution_timestamps:
        issues.append("command_acknowledgment requires execution_timestamps")
    if require_execution_timestamps and not capabilities.execution_timestamps:
        issues.append("execution_timestamps are required by this evaluation profile")
    return issues
