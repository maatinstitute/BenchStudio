"""A stateful agent fixture uses exactly the same case-execution engine as simulators."""
import json
from types import SimpleNamespace

import pytest

import benchstudio as bs
from benchstudio.backends import CaseResult


class AgentBackend:
    cases = ("dialogue-a", "dialogue-b")
    supports_timeout = False

    def __init__(self, fail_first=False, error=None):
        self.events, self.records = [], []
        self.fail_first, self.error = fail_first, error
        self.model = None

    def check(self, config):
        return ()

    def start(self, config):
        self.events.append("start")
        self.model = object()

    def execute_case(self, case, *, attempt, config):
        self.events.append(("begin", case, attempt))
        conversation = []
        try:
            assert self.model is not None
            conversation.append("agent-message")
            if self.error is not None:
                raise self.error
            return CaseResult(not (self.fail_first and attempt == 1),
                {"messages": tuple(conversation), "task_success": False, "model_id": id(self.model)})
        finally:
            self.events.append(("end", case, attempt))

    def close(self):
        self.events.append("close")
        self.model = None

    def record(self, case, result, *, attempt):
        self.records.append((case, attempt, result))

    def finish(self):
        return SimpleNamespace(records=tuple(self.records), summary=lambda: "retained agent interactions")


def test_engine_reuses_worker_without_reusing_conversation_state(tmp_path):
    backend = AgentBackend()
    engine = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(output_dir=tmp_path / "out"))
    assert engine.check().configuration_valid and not backend.events
    result = engine.run()
    assert len(result.records) == 2
    assert [event[0] for event in backend.events[1:-1]] == ["begin", "end", "begin", "end"]
    assert len({record[2].output["model_id"] for record in result.records}) == 1
    assert all(record[2].output["messages"] == ("agent-message",) for record in result.records)
    assert backend.events[-1] == "close" and backend.model is None
    assert all(record[2].completed for record in result.records)
    assert all(record[2].output["task_success"] is False for record in result.records)
    assert json.loads((tmp_path / "out/execution.json").read_text())["status"] == "completed"


@pytest.mark.parametrize("retries,expected", [(0, 1), (1, 4)])
def test_retry_policy_is_explicit_and_only_for_incomplete_execution(tmp_path, retries, expected):
    backend = AgentBackend(fail_first=True)
    engine = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(
        max_retries=retries, output_dir=tmp_path / "out"))
    result = engine.run()
    assert len(result.records) == expected
    rows = [json.loads(line) for line in (tmp_path / "out/cases.jsonl").read_text().splitlines()]
    assert len(rows) == expected
    assert json.loads((tmp_path / "out/execution.json").read_text())["status"] == (
        "incomplete" if retries == 0 else "completed")


@pytest.mark.parametrize("error", [RuntimeError("broken instrument"), KeyboardInterrupt()])
def test_exception_and_interrupt_close_and_retain_without_retry(tmp_path, error):
    backend = AgentBackend(error=error)
    engine = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(
        max_retries=9, output_dir=tmp_path / "out"))
    with pytest.raises(type(error)):
        engine.run()
    assert len(backend.records) == 1
    assert backend.events[-2:] == [("end", "dialogue-a", 1), "close"]
    record = json.loads((tmp_path / "out/execution.json").read_text())
    assert record["status"] == "execution_failed" and record["error_type"] == type(error).__name__


def test_unsupported_timeout_and_existing_output_fail_before_work(tmp_path):
    backend = AgentBackend()
    engine = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(timeout=.1))
    assert not engine.check().configuration_valid
    with pytest.raises(ValueError, match="timeout"):
        engine.run()
    engine = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(output_dir=tmp_path))
    with pytest.raises(ValueError, match="already exists"):
        engine.run()
    assert not backend.events


def test_continuation_is_explicit(tmp_path):
    backend = AgentBackend(fail_first=True)
    result = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(
        continue_on_error=True, output_dir=tmp_path / "out")).run()
    assert len(result.records) == 2
    assert json.loads((tmp_path / "out/execution.json").read_text())["status"] == "incomplete"


def test_existing_pipeline_uses_the_same_execution_engine():
    backend = AgentBackend()
    evaluation = bs.pipeline("evaluate", backend=backend)
    assert isinstance(evaluation, bs.EvaluationEngine)
    assert len(evaluation.run().records) == 2


def test_worker_cleanup_failure_stops_without_reexecuting_cases(tmp_path):
    class BrokenCleanup(AgentBackend):
        def close(self):
            super().close()
            raise RuntimeError("cleanup failed")
    backend = BrokenCleanup()
    evaluation = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(
        output_dir=tmp_path / "out", max_retries=3))
    with pytest.raises(RuntimeError, match="cleanup failed"):
        evaluation.run()
    assert len(backend.records) == 2
    assert json.loads((tmp_path / "out/execution.json").read_text())["status"] == "execution_failed"



def test_native_retry_flags_are_not_silently_applied_to_callable_models():
    system = bs.System.from_callable(lambda value: pytest.fail("model called"), name="m", revision="r")
    benchmark = bs.Benchmark("b", "r", [1], [1], lambda a, b: bs.Score(), "r")
    evaluation = bs.EvaluationEngine(system=system, benchmark=benchmark,
                                   config=bs.EvaluationConfig(max_retries=1))
    assert not evaluation.check().configuration_valid
    with pytest.raises(TypeError, match="execution backend"):
        evaluation.run()


def test_partial_worker_start_is_closed_and_original_error_preserved(tmp_path):
    class BrokenWorker(AgentBackend):
        def start(self, config):
            super().start(config)
            raise ValueError("worker start failed")
        def close(self):
            super().close()
            raise RuntimeError("close also failed")
    backend = BrokenWorker()
    engine = bs.EvaluationEngine(backend=backend, config=bs.EvaluationConfig(output_dir=tmp_path / "out"))
    with pytest.raises(ValueError, match="start failed") as caught:
        engine.run()
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert backend.events == ["start", "close"] and backend.model is None
    assert not backend.records
