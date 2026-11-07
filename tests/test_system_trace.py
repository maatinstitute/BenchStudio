from benchstudio.system_spec import Component, Connection, SystemSpec
from benchstudio.system_trace import SystemEvent, audit_system_trace


def graph():
    return SystemSpec("robot-world-system", "r1", (
        Component("world", "world_model", "model-a", "v1", outputs=("prediction",)),
        Component("agent", "agent", "planner", "v1", inputs=("world",), outputs=("plan",)),
        Component("actor", "vla", "policy", "v1", inputs=("plan",), outputs=("action",)),
    ), (
        Connection("world", "prediction", "agent", "world"),
        Connection("agent", "plan", "actor", "plan"),
    ))


def event(eid, component, time, parent=None, inp=None, out=None, clock="sim"):
    return SystemEvent("trial1", eid, component, "call", time, clock,
                       parent_event_id=parent, input_port=inp, output_port=out)


def test_real_graph_event_links_are_auditable():
    events = [
        event("wm", "world", 1, out="prediction"),
        event("plan", "agent", 2, "wm", "world", "plan"),
        event("act", "actor", 3, "plan", "plan", "action"),
    ]
    result = audit_system_trace(graph(), events)
    assert result.valid and len(result.observed_connections) == 2
    assert not result.unobserved_connections


def test_cross_component_mismatch_is_not_silent():
    events = [event("wm", "world", 1, out="prediction"),
              event("act", "actor", 2, "wm", "plan")]
    result = audit_system_trace(graph(), events)
    assert not result.valid
    assert any("undeclared" in reason for reason in result.issues)


def test_unobserved_edges_are_reported_not_fabricated():
    result = audit_system_trace(graph(), [event("wm", "world", 1, out="prediction")])
    assert result.valid and len(result.unobserved_connections) == 2


def test_bad_parent_order_and_cross_trial_fail():
    events = [event("p", "world", 100, out="prediction"),
              event("c", "agent", 50, "p", "world")]
    assert not audit_system_trace(graph(), events).valid
    second = SystemEvent("other", "c", "agent", "call", 200, "sim",
                         parent_event_id="p", input_port="world")
    assert any("different trial" in issue for issue in
               audit_system_trace(graph(), [events[0], second]).issues)


def test_different_clocks_not_assumed_synchronized():
    result = audit_system_trace(graph(), [
        event("p", "world", 100, out="prediction", clock="host"),
        event("c", "agent", 1, "p", "world", clock="sim"),
    ])
    assert result.valid and result.clock_domains == ("host", "sim")



def test_self_parent_and_equal_time_parent_cycles_are_invalid():
    s = graph()
    assert not audit_system_trace(s, [event("a", "world", 1, "a")]).valid
    result = audit_system_trace(s, [event("a", "world", 1, "b"),
                                   event("b", "world", 1, "a")])
    assert not result.valid
    assert any("cyclic" in issue for issue in result.issues)


def test_large_trace_connection_lookup_scales_with_events():
    from unittest.mock import patch
    count, trials = 200, 20
    nodes = tuple(Component(str(i), "agent", "synthetic", "r1", inputs=("in",), outputs=("out",))
                  for i in range(count))
    edges = tuple(Connection(str(i-1), "out", str(i), "in") for i in range(1, count))
    system = SystemSpec("synthetic-chain", "r1", nodes, edges)
    events = [SystemEvent(str(t), f"{t}:{i}", str(i), "call", i, "clock",
                          parent_event_id=f"{t}:{i-1}" if i else None,
                          input_port="in" if i else None, output_port="out")
              for t in range(trials) for i in range(count)]
    comparisons = []
    original_eq = Connection.__eq__
    def counted_eq(a, b):
        comparisons.append(1)
        return original_eq(a, b)
    with patch.object(Connection, "__eq__", counted_eq):
        result = audit_system_trace(system, events)
    assert result.valid
    assert result.observed_connections == system.connections
    assert not result.unobserved_connections
    assert len(comparisons) < len(events) * 4


def test_indexed_connection_lookup_keeps_rejecting_wrong_ports():
    events = [event("p", "world", 1, out="prediction"),
              event("c", "agent", 2, "p", "not-declared")]
    result = audit_system_trace(graph(), events)
    assert not result.valid
    assert any("undeclared input port" in issue for issue in result.issues)
    assert any("undeclared cross-component connection" in issue for issue in result.issues)
    assert not result.observed_connections
