"""Resolve explicitly named installed backends; no downloads or implicit code search."""
from importlib import metadata


def load_backend(group, name):
    matches = list(metadata.entry_points(group=group, name=name))
    if len(matches) != 1:
        raise ValueError(f"expected one installed {group} backend named {name!r}; found {len(matches)}")
    factory = matches[0].load()
    if not callable(factory):
        raise TypeError(f"backend {name!r} must expose a callable factory")
    return factory


def requirement_issues(runtime):
    requirements = getattr(runtime, "requirements", {})
    if not isinstance(requirements, dict):
        raise TypeError("runtime requirements must map distribution names to exact versions or None")
    issues = []
    for name, expected in requirements.items():
        if not isinstance(name, str) or not name or (expected is not None and not isinstance(expected, str)):
            raise TypeError("invalid runtime requirement")
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            issues.append(f"missing dependency: {name}")
            continue
        if expected is not None and actual != expected:
            issues.append(f"{name}: installed {actual}, required {expected}")
    return issues
