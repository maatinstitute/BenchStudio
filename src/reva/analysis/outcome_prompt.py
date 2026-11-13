"""Shared outcome prompt seam used by training and inference callers."""

from __future__ import annotations

try:
    from .metadata_conditioning import condition_prompt, prompt_mode_metadata
except ImportError:  # direct execution with experiments/ as the import root
    from metadata_conditioning import condition_prompt, prompt_mode_metadata


def training_prompt(task: str, recorded_outcome: str | None) -> str:
    """Build a training prompt from a recorded episode label only."""
    if recorded_outcome == "unknown":
        raise ValueError("unknown outcome cannot enter a training prompt")
    mode = "task_only" if recorded_outcome is None else "recorded_outcome"
    return condition_prompt(task, prompt_mode_metadata(mode, recorded_outcome=recorded_outcome))


def inference_prompt(task: str, desired_outcome: str = "success") -> str:
    """Build an inference request; an execution result is never an input."""
    if desired_outcome != "success":
        raise ValueError("outcome-conditioned inference is frozen to desired success")
    return condition_prompt(task, prompt_mode_metadata("desired_success"))
