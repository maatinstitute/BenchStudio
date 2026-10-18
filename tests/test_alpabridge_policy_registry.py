from __future__ import annotations

from types import SimpleNamespace

import pytest

from benchstudio.integrations import (
    DriverPolicy,
    PolicyRegistry,
    load_external_policy_modules,
    read_finite_float_tuple,
    read_positive_finite_float,
)


def context(checkpoint=None, tokenizer=None):
    return SimpleNamespace(
        checkpoint_path=checkpoint,
        tokenizer_checkpoint_path=tokenizer,
    )


def test_registry_is_sorted_and_rejects_duplicate_names():
    registry = PolicyRegistry()
    registry.register(DriverPolicy("z", lambda _: "z"))
    registry.register(DriverPolicy("a", lambda _: "a"))
    assert registry.available() == ("a", "z")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DriverPolicy("a", lambda _: "again"))


def test_build_enforces_checkpoint_requirements_before_factory():
    calls = []
    registry = PolicyRegistry()
    registry.register(
        DriverPolicy(
            "needs-both",
            lambda value: calls.append(value),
            requires_checkpoint=True,
            requires_tokenizer_checkpoint=True,
        )
    )
    with pytest.raises(ValueError, match="checkpoint path"):
        registry.build("needs-both", context())
    with pytest.raises(ValueError, match="tokenizer checkpoint path"):
        registry.build("needs-both", context("weights"))
    value = context("weights", "tokenizer")
    registry.build("needs-both", value)
    assert calls == [value]


def test_environment_parsing_is_fail_closed(monkeypatch):
    monkeypatch.setenv("BENCHSTUDIO_SCALAR", "nan")
    assert read_positive_finite_float("BENCHSTUDIO_SCALAR", 8.0) == 8.0
    monkeypatch.setenv("BENCHSTUDIO_TUPLE", "-2,0,1.5")
    assert read_finite_float_tuple("BENCHSTUDIO_TUPLE", (1.0,)) == (-2.0, 0.0, 1.5)
    monkeypatch.setenv("BENCHSTUDIO_TUPLE", "junk,2")
    assert read_finite_float_tuple("BENCHSTUDIO_TUPLE", (1.0,)) == (1.0,)


def test_external_module_loader_is_explicit_and_fatal_for_missing_modules(monkeypatch):
    monkeypatch.delenv("ALPABRIDGE_EXTRA_POLICY_MODULES", raising=False)
    assert load_external_policy_modules() == ()
    assert load_external_policy_modules("json, ,copy") == ("json", "copy")
    with pytest.raises(ModuleNotFoundError):
        load_external_policy_modules("benchstudio.module_that_does_not_exist")
