"""CPU-only identity lookup microbenchmark; no model, simulator or GPU."""
import hashlib
from statistics import median
from timeit import repeat

from benchstudio import Component, SystemSpec
from benchstudio.system_spec import _canonical

spec = SystemSpec("synthetic-stack", "r1", tuple(
    Component(str(i), "agent", "synthetic", "r1") for i in range(10)
))


def uncached():
    return hashlib.sha256(_canonical(spec.to_dict())).hexdigest()


assert uncached() == spec.digest
before = median(repeat(uncached, number=2000, repeat=5))
after = median(repeat(lambda: spec.digest, number=2000, repeat=5))
print("Synthetic immutable 10-component system; median of five runs, 2000 lookups each")
print(f"Recompute: {before:.6f}s; cached: {after:.6f}s")
print("Same digest:", spec.digest)
print("This measures identity lookup only, not inference or end-to-end throughput.")
