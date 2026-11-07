"""Cooperative async scheduling for models, agent groups and runtime adapters."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import inspect
from typing import Mapping

from .system_pipeline import System


def _positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


async def invoke(runtime, value):
    """Invoke cooperative code; synchronous functions must not block the loop."""
    output = runtime(value)
    return await output if inspect.isawaitable(output) else output


async def ordered_map(function, values, *, concurrency):
    """Use bounded workers, preserve input order and drain tasks on any exit."""
    _positive(concurrency, "concurrency")
    values = tuple(values)
    results = [None] * len(values)
    remaining = iter(enumerate(values))

    async def worker():
        for index, value in remaining:
            results[index] = await function(value)

    tasks = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(values)))]
    try:
        await asyncio.gather(*tasks)
        return results
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class ResourcePool:
    """Named concurrency limits shared by runtimes on one event loop.

    A slot is an admission limit, not a GPU memory reservation or sandbox.
    Acquire all required resources in a single lease; nested leases are unsupported.
    """
    def __init__(self, capacities: Mapping[str, int]):
        if not capacities or any(not isinstance(k, str) or not k.strip() for k in capacities):
            raise ValueError("resource names must be nonempty")
        for capacity in capacities.values():
            _positive(capacity, "capacity")
        self._slots = {name: asyncio.Semaphore(capacity) for name, capacity in capacities.items()}
        self._loop = None

    def validate(self, names):
        names = tuple(names)
        if any(not isinstance(name, str) or name not in self._slots for name in names):
            raise ValueError("unknown resource")
        if len(names) != len(set(names)):
            raise ValueError("duplicate resource")
        return tuple(sorted(names))

    @asynccontextmanager
    async def lease(self, names):
        names = self.validate(names)
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError("ResourcePool cannot be shared across event loops")
        self._loop = loop
        acquired = []
        try:
            for name in names:
                await self._slots[name].acquire()
                acquired.append(name)
            yield
        finally:
            for name in reversed(acquired):
                self._slots[name].release()


class AgentGroup:
    """Broadcast an input to named agents and reduce their ordered outputs.

    This implements parallel fan-out and aggregation, not arbitrary graph
    execution. Each member owns its session state, tools and permissions.
    """
    def __init__(self, agents: Mapping[str, System], *, reducer, concurrency=1,
                 pool=None, resources=None):
        _positive(concurrency, "concurrency")
        if not agents or any(not isinstance(k, str) or not k.strip() or
                             not isinstance(v, System) for k, v in agents.items()):
            raise ValueError("agents must map nonempty names to System objects")
        if not callable(reducer):
            raise TypeError("reducer must be callable")
        self.agents = dict(agents)
        self.reducer = reducer
        self.concurrency = concurrency
        self.pool = pool
        self.resources = {name: tuple(request) for name, request in (resources or {}).items()}
        if set(self.resources) - set(self.agents):
            raise ValueError("resources refer to unknown agent")
        if self.resources and pool is None:
            raise ValueError("resource requests require a ResourcePool")
        if pool is not None:
            for request in self.resources.values():
                pool.validate(request)

    async def __call__(self, value):
        async def run_member(item):
            name, system = item
            if self.pool is None:
                return await invoke(system.runtime, value)
            async with self.pool.lease(self.resources.get(name, ())):
                return await invoke(system.runtime, value)
        outputs = await ordered_map(run_member, self.agents.items(), concurrency=self.concurrency)
        return await invoke(self.reducer, dict(zip(self.agents, outputs)))
