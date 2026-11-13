
import pytest

import reva.campaigns.robopad_assay_claims as claims


@pytest.fixture
def setup_claims(tmp_path, monkeypatch):
    root = (tmp_path / "claims").resolve()
    root.mkdir()
    monkeypatch.setattr(claims, "GLOBAL_ROOT", root)
    receipt = tmp_path / "receipt.json"
    bindings = {key: "a" * 64 for key in claims.HASH_KEYS}
    bindings["output_path"] = str((tmp_path / "output").resolve())
    runs = claims.canonical_runs(0, 0)
    return root, receipt, bindings, runs


def test_complete_reservation_then_one_start(setup_claims):
    root, receipt, bindings, runs = setup_claims
    claims.reserve_child(root, receipt, expected_bindings=bindings, expected_runs=runs)
    token = claims.verify_and_start(root, receipt, expected_bindings=bindings, expected_runs=runs)
    assert claims.validate_claim(token, runs[0])
    with pytest.raises(FileExistsError):
        claims.verify_and_start(root, receipt, expected_bindings=bindings, expected_runs=runs)


def test_partial_failure_preserves_claims_without_receipt(setup_claims, monkeypatch):
    root, receipt, bindings, runs = setup_claims
    original = claims._exclusive
    counter = [0]

    def fail(path, body):
        counter[0] += 1
        if counter[0] == 3:
            raise OSError("injected failure")
        return original(path, body)

    monkeypatch.setattr(claims, "_exclusive", fail)
    with pytest.raises(OSError):
        claims.reserve_child(root, receipt, expected_bindings=bindings, expected_runs=runs)
    assert len(list(root.glob("*.json"))) == 2
    assert not receipt.exists()
    with pytest.raises(FileExistsError):
        claims.reserve_child(root, receipt, expected_bindings=bindings, expected_runs=runs)


def test_binding_run_and_tamper_checks_are_fail_closed(setup_claims):
    root, receipt, bindings, runs = setup_claims
    with pytest.raises(FileNotFoundError):
        claims.verify_and_start(root, receipt, expected_bindings=bindings, expected_runs=runs)
    with pytest.raises(ValueError):
        claims.reserve_child(root, receipt, expected_bindings=bindings, expected_runs=runs[:-1])
    claims.reserve_child(root, receipt, expected_bindings=bindings, expected_runs=runs)
    token = claims.verify_and_start(root, receipt, expected_bindings=bindings, expected_runs=runs)
    (root / (runs[0] + ".json")).write_text("{}")
    with pytest.raises(ValueError):
        claims.validate_claim(token, runs[0])


def test_canonical_run_counts_and_path_security(setup_claims):
    root, receipt, bindings, runs = setup_claims
    assert len(claims.canonical_runs(0, 0)) == 54
    assert len(claims.canonical_runs(2, 1)) == 62
    bindings["source_sha256"] = "Z" * 64
    with pytest.raises(ValueError):
        claims.reserve_child(root, receipt, expected_bindings=bindings, expected_runs=runs)
    with pytest.raises(ValueError):
        claims.validate_claim(object(), "../escape")
