"""CPU-only synthetic trace profile: 200 components, 20 trials, 4000 events."""
import cProfile
import pstats
from statistics import median
from timeit import repeat

from benchstudio import Component, Connection, SystemEvent, SystemSpec, audit_system_trace


def fixture():
    count, trials = 200, 20
    nodes = tuple(Component(str(i), "agent", "synthetic", "r1", inputs=("in",), outputs=("out",))
                  for i in range(count))
    edges = tuple(Connection(str(i-1), "out", str(i), "in") for i in range(1, count))
    system = SystemSpec("synthetic-agent-chain", "r1", nodes, edges)
    events = [SystemEvent(str(trial), f"{trial}:{i}", str(i), "call", i, "synthetic-clock",
                          parent_event_id=f"{trial}:{i-1}" if i else None,
                          input_port="in" if i else None, output_port="out")
              for trial in range(trials) for i in range(count)]
    return system, events


def main():
    system, events = fixture()
    audit = lambda: audit_system_trace(system, events)
    result = audit()
    assert result.valid and result.observed_connections == system.connections
    assert not result.unobserved_connections
    elapsed = median(repeat(audit, number=1, repeat=5))
    print(f"Synthetic trace audit: {len(system.components)} components, {len(events)} events")
    print(f"Median of 5 runs: {elapsed:.6f}s; valid={result.valid}")
    profile = cProfile.Profile()
    profile.runcall(audit)
    pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(8)
    print("Measures metadata validation only; no model, simulator, GPU or physical agent.")


if __name__ == "__main__":
    main()
