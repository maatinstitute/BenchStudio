from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_source_snapshot_verifier_checks_files_and_detects_tampering(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_file = source_root / "src" / "module.py"
    source_file.parent.mkdir()
    source_file.write_text("value = 1\n", encoding="utf-8")
    digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
    manifest = tmp_path / "snapshot.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "reva_source_snapshot_v1",
                "repository": "example",
                "commit": "abc",
                "files": {"src/module.py": digest},
            }
        ),
        encoding="utf-8",
    )
    script = Path(__file__).parents[1] / "scripts/verify_source_snapshot.py"
    valid = subprocess.run(
        [sys.executable, str(script), str(manifest), str(source_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["valid"] is True

    source_file.write_text("value = 2\n", encoding="utf-8")
    tampered = subprocess.run(
        [sys.executable, str(script), str(manifest), str(source_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tampered.returncode == 2
    report = json.loads(tampered.stdout)
    assert report["valid"] is False
    assert report["mismatches"][0]["reason"] == "digest_mismatch"
