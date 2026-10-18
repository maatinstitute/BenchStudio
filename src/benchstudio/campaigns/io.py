"""Load declarative campaign documents without coupling the core to YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_campaign_document(path: Path) -> dict[str, Any]:
    """Load a JSON or optional YAML campaign mapping."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "YAML campaign files require the optional dependency; install benchstudio[yaml]"
            ) from exc
        value = yaml.safe_load(text)
    else:
        value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("campaign document must contain a top-level mapping")
    return value
