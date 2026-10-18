from benchstudio.analysis import InferenceEvent, audit_inference_schedule


def _event(phase: str, step: int) -> InferenceEvent:
    return InferenceEvent(
        "episode-1",
        step,
        phase,  # type: ignore[arg-type]
        "a" * 64,
        "b" * 64,
        2.5,
    )


def test_inference_schedule_requires_warmup_before_frozen_measured_steps():
    audit = audit_inference_schedule(
        [_event("warmup", 0), _event("measured", 0), _event("measured", 2)],
        expected_measured_steps=[0, 2],
        expected_episode_id="episode-1",
    )
    assert audit.valid is True
    assert audit.warmup_count == 1
    assert audit.measured_count == 2


def test_inference_schedule_rejects_interleaving_and_counter_mismatch():
    bad = _event("warmup", 1)
    measured = InferenceEvent("episode-1", 0, "measured", "a" * 64, "b" * 64, 2.5, 2, 1)
    audit = audit_inference_schedule(
        [_event("measured", 0), bad, measured], expected_measured_steps=[0, 1]
    )
    assert audit.valid is False
    assert "warmup events must precede measured events" in audit.issues
    assert any("counters disagree" in issue for issue in audit.issues)
