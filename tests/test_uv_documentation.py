from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_documented_python_commands_use_locked_uv() -> None:
    paths = [
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "examples").glob("*/README.md")),
        *sorted((ROOT / "scripts").glob("*.sh")),
    ]
    failures: list[str] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            command = line.strip()
            if command.startswith(("python ", "python3 ", "PYTHONPATH=src python ")):
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {command}")
            if "pip install" in command or "python -m pip" in command:
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {command}")
            if command.startswith("uv run ") and "--locked" not in command:
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {command}")
            if command.startswith("uv sync ") and "--locked" not in command:
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {command}")

    assert not failures, "commands must use the locked uv environment:\n" + "\n".join(failures)
