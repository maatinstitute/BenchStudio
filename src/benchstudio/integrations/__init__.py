"""Optional integration boundaries that do not own simulator or robot authority."""

from .robochallenge import (
    RoboChallengeAction,
    RoboChallengeObservation,
    RoboChallengeObserveOnlyAdapter,
    validate_robochallenge_message,
)

__all__ = [
    "RoboChallengeAction",
    "RoboChallengeObservation",
    "RoboChallengeObserveOnlyAdapter",
    "validate_robochallenge_message",
]
