"""Framework-independent binding of user-configured Python inference calls."""
from __future__ import annotations

import inspect
from typing import Mapping

from .system_spec import _canonical, _thaw


class DeclaredCallable:
    """Pass inputs/outputs unchanged; check only the explicit declaration."""

    def __init__(self, function, configuration=None):
        self.__wrapped__ = function
        self._configuration = configuration
        self._snapshot = None if configuration is None else _canonical(_thaw(configuration))

    @property
    def requirements(self):
        return getattr(self.__wrapped__, "requirements", {})

    @property
    def supports_async(self):
        return getattr(self.__wrapped__, "supports_async", True)

    def _verify_declaration(self):
        if self._configuration is not None:
            if _canonical(_thaw(self._configuration)) != self._snapshot:
                raise ValueError("declared configuration changed; construct a new System before execution")

    def __call__(self, inputs):
        self._verify_declaration()
        return self.__wrapped__(inputs)


class BatchedCallable(DeclaredCallable):
    """A native batch function returning one opaque output per ordered input."""
    supports_async = False

    def __call__(self, inputs):
        return self.generate_batch([inputs])[0]

    def generate_batch(self, inputs):
        self._verify_declaration()
        inputs = list(inputs)
        if not inputs:
            return []
        outputs = self.__wrapped__(inputs)
        if inspect.isawaitable(outputs):
            if inspect.iscoroutine(outputs):
                outputs.close()
            raise TypeError("batched callables must be synchronous")
        if isinstance(outputs, (str, bytes, Mapping)):
            raise TypeError("batched callable must return a sequence of per-input outputs")
        outputs = list(outputs)
        if len(outputs) != len(inputs):
            raise ValueError("native output count differs from input count")
        return outputs
