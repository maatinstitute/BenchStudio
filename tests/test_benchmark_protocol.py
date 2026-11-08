"""Synthetic LIBERO-shaped calendar; no LIBERO/model/simulator imports or states."""
import json
from types import SimpleNamespace

import pytest

import benchstudio as bs
from benchstudio.backends import BenchmarkCase, CaseResult


class NativeBatch:
    supports_timeout = False

    def __init__(self, system, benchmark, *, partial=False):
        self.system, self.benchmark, self.partial = system, benchmark, partial
        self.cases = benchmark.execution_ids
        self.started, self.closed, self.dispatched = 0, 0, []
        self.outcomes = {}

    def check(self, config):
        return ()

    def start(self, config):
        self.started += 1

    def execute_case(self, execution, *, attempt, config):
        self.dispatched.append(execution)
        units = [case for case in self.benchmark.cases if case.execution_id == execution]
        if self.partial:
            units = units[:-1]
        for unit in units:
            # One experimental unit involves multiple system invocations. This
            # is an in-memory state-machine fixture, not a simulator rollout.
            for tick in range(3):
                self.system.act(unit.dimensions, tick)
            self.outcomes[unit.case_id] = {"native_metric": unit.dimensions["condition"]}
        return CaseResult(True, self.outcomes)

    def record(self, execution, result, *, attempt):
        pass  # This fixture preserves its native result dictionary unchanged.

    def close(self):
        self.closed += 1

    def finish(self):
        missing = [case.case_id for case in self.benchmark.cases if case.case_id not in self.outcomes]
        return SimpleNamespace(outcomes=self.outcomes, missing=missing, successful=not missing,
                               summary=lambda: f"{len(self.outcomes)} native outcomes")


class SyntheticProtocol:
    supports_retries = False

    def __init__(self, grouped=True, partial=False):
        self.partial = partial
        self.bound = None
        self.cases = tuple(BenchmarkCase(
            f"synthetic-t{task}-state{state}-condition{condition}",
            {"suite": "synthetic", "task": task, "state": f"fixture-{state}",
             "seed": 7, "condition": condition},
            execution_id="native-program" if grouped else None,
        ) for task in range(2) for state in range(2) for condition in (2, 5))

    def bind(self, system, *, benchmark, config):
        self.bound = NativeBatch(system, benchmark, partial=self.partial)
        return self.bound


def study(protocol):
    return bs.Benchmark("synthetic-native-suite", "protocol-r1", protocol=protocol,
        evaluator_revision="native-evaluator-r1", environment_revision="synthetic-stack-r1")


def policy():
    calls = []
    return SimpleNamespace(act=lambda case, tick: calls.append((case, tick)), calls=calls)


def test_complete_calendar_is_not_one_model_call_or_one_native_trial(tmp_path):
    protocol, system = SyntheticProtocol(), policy()
    benchmark = study(protocol)
    evaluation = bs.pipeline(system=system, benchmark=benchmark,
        config=bs.EvaluationConfig(output_dir=tmp_path / "out"))
    check = evaluation.check()
    assert check.cases == 8 and check.executions == 1 and not check.native_verified
    assert "8 cases in 1 execution group" in check.summary()
    assert not system.calls and protocol.bound.started == 0
    result = evaluation()
    assert len(result.outcomes) == 8 and len(system.calls) == 24
    assert protocol.bound.dispatched == ["native-program"]
    assert protocol.bound.started == protocol.bound.closed == 1
    plan = json.loads((tmp_path / "out/benchmark.json").read_text())
    assert plan["case_count"] == 8 and len(plan["execution_ids"]) == 1
    assert plan["protocol_digest"] == benchmark.protocol_digest
    receipt = json.loads((tmp_path / "out/cases.jsonl").read_text())
    assert len(receipt["planned_benchmark_case_ids"]) == 8
    assert all("condition" in case["dimensions"] for case in plan["cases"])


def test_native_completion_does_not_fabricate_missing_scientific_outcomes(tmp_path):
    benchmark = study(SyntheticProtocol(partial=True))
    result = bs.pipeline(system=policy(), benchmark=benchmark,
        config=bs.EvaluationConfig(output_dir=tmp_path / "out"))()
    assert len(result.outcomes) == 7 and len(result.missing) == 1 and not result.successful
    receipt = json.loads((tmp_path / "out/cases.jsonl").read_text())
    assert receipt["completed"] is True  # Execution receipt, not a coverage verdict.
    assert result.missing[0] not in result.outcomes


def test_protocol_can_dispatch_individual_units_without_changing_the_engine():
    protocol = SyntheticProtocol(grouped=False)
    benchmark = study(protocol)
    result = bs.pipeline(system=policy(), benchmark=benchmark)()
    assert len(protocol.bound.dispatched) == len(result.outcomes) == 8


def test_scientific_protocol_does_not_inherit_generic_retry_permission(tmp_path):
    protocol = SyntheticProtocol()
    benchmark = study(protocol)
    protocol.supports_retries = True  # Does not alter the frozen benchmark policy.
    evaluation = bs.pipeline(system=policy(), benchmark=benchmark,
        config=bs.EvaluationConfig(output_dir=tmp_path / "out", max_retries=1))
    with pytest.raises(ValueError, match="does not permit"):
        evaluation()
    assert protocol.bound.started == 0 and not (tmp_path / "out").exists()


def test_backend_cannot_silently_change_the_bound_calendar():
    class WrongProtocol(SyntheticProtocol):
        def bind(self, system, *, benchmark, config):
            backend = super().bind(system, benchmark=benchmark, config=config)
            backend.cases = ("wrong-execution",)
            return backend
    with pytest.raises(ValueError, match="frozen benchmark calendar"):
        bs.pipeline(system=policy(), benchmark=study(WrongProtocol()))


def test_case_dimensions_are_immutable_and_bound_into_protocol_identity():
    protocol = SyntheticProtocol()
    a = study(protocol)
    with pytest.raises(TypeError):
        a.cases[0].dimensions["condition"] = 100
    other = SyntheticProtocol()
    first = other.cases[0]
    other.cases = (BenchmarkCase(first.case_id, {**first.dimensions, "seed": 99}, first.execution_id),) + other.cases[1:]
    assert study(other).protocol_digest != a.protocol_digest
    with pytest.raises(TypeError, match="native identities"):
        a.key(0)


def test_protocol_and_offline_rows_cannot_be_accidentally_combined():
    with pytest.raises(ValueError, match="not both"):
        bs.Benchmark("bad", "r1", [1], [1], lambda a, b: bs.Score(), "r1",
                     protocol=SyntheticProtocol(), environment_revision="synthetic")


def test_registered_benchmark_factory_can_return_a_complete_protocol(monkeypatch):
    benchmark = study(SyntheticProtocol())
    monkeypatch.setattr("benchstudio.backend_loading.load_backend",
                        lambda group, name: lambda **options: benchmark)
    assert bs.Benchmark.load("installed-suite", revision="protocol-r1") is benchmark
    with pytest.raises(ValueError, match="different revision"):
        bs.Benchmark.load("installed-suite", revision="wrong")


def test_native_protocol_authority_cannot_be_invented_by_offline_scorer_flag():
    with pytest.raises(ValueError, match="native evaluator"):
        bs.Benchmark("bad-authority", "r1", protocol=SyntheticProtocol(),
            evaluator_revision="r1", environment_revision="r1", authoritative=True)
