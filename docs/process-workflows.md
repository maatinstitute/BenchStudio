# Reusable process orchestration

BenchStudio owns trusted command execution and service lifetime management:

```python
import benchstudio as bs

check = bs.ProcessCommand("check", ("/env/bin/python", "check_inputs.py"), cwd="/project")
check.run("/results/operator-logs")
```

`ProcessCommand` uses argv without a shell, streams stdout/stderr to files,
retains an exit receipt, supports command timeouts and raises on failure.
`.service(logs, ready=callback, startup_timeout=...)` starts an owned background
service, waits for the caller's readiness test and cleans it up when the client
finishes or fails. These are trusted local commands, not a sandbox. Processes
must not daemonize away from the owned session. Task code owns port/semantic
readiness, scoring, qualification and authorization. No automatic retry occurs.

| Responsibility | Owner |
| --- | --- |
| Processes, stdout/stderr, exit status, service cleanup, timeouts | BenchStudio |
| Model-native interpreters and adapters | Native stack / RoboPAD recipe |
| R22/R25, 400 pairs, 800 attempts, within-model analysis | RoboPAD |
| Protocols A/E, parity, units, compiled counting, manifests, release hashes | RoboPAD |
| `bs.RefinementWorkspace` | Optional compatibility adapter to the RoboPAD offline helper |

The paper's `experiments/run_r22r25.py` is a recipe using this generic engine.
It must not move scientific rules into BenchStudio. It runs in BenchStudio's
supported Python; children use the separately pinned SmolVLA/OpenPI interpreters.
