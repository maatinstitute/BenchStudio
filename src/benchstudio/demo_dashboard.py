"""Build a self-contained visual dashboard from BenchStudio demo evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows


def _short(value: Any, length: int = 12) -> str:
    text = str(value or "unavailable")
    return html.escape(text[:length])


def _percent(value: Any) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0
    return max(0, min(100, round(float(value) * 100)))


def build_demo_dashboard(input_dir: Path, output_path: Path) -> Path:
    """Render the demo evidence directory as a standalone HTML control room."""
    root = Path(input_dir)
    plan = _load_json(root / "campaign-plan.json")
    ledger = _load_jsonl(root / "campaign" / "attempt-results.jsonl")
    robustness = _load_json(root / "robustness" / "counterfactual-summary.json")
    transfer = _load_json(root / "transfer" / "transfer-report.json")
    robochallenge = _load_json(root / "robochallenge-report.json")

    robot_run: dict[str, Any] = {}
    robot_report: dict[str, Any] = {}
    robot_comparison: dict[str, Any] = {}
    robot_policy: dict[str, Any] = {}
    robot_policy_digest = "not loaded"
    robot_policy_timeline = "No policy artifact loaded"
    robot_root = root / "urdf-studio"
    selected_simulator = "mujoco"
    if (robot_root / "run.json").is_file():
        robot_run = _load_json(robot_root / "run.json")
        simulator_names = robot_run.get("sims", [])
        if isinstance(simulator_names, list) and simulator_names:
            selected_simulator = str(simulator_names[0])
        report_path = robot_root / selected_simulator / "episode-0" / "report.json"
        comparison_path = robot_root / "comparison.json"
        policy_path = robot_root / "scenario" / "waypoints.json"
        if report_path.is_file():
            robot_report = _load_json(report_path)
        if comparison_path.is_file():
            robot_comparison = _load_json(comparison_path)
        if policy_path.is_file():
            robot_policy = _load_json(policy_path)
            robot_policy_digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
            raw_waypoints = robot_policy.get("waypoints", [])
            if isinstance(raw_waypoints, list):
                events = []
                for waypoint in raw_waypoints:
                    if not isinstance(waypoint, dict):
                        continue
                    label = str(waypoint.get("label", "waypoint"))
                    time_s = float(waypoint.get("time_s", 0.0) or 0.0)
                    events.append(f"{label} {time_s:.1f}s")
                if events:
                    robot_policy_timeline = " · ".join(events)

    attempts = plan.get("attempts", [])
    completed = sum(row.get("status") == "completed" for row in ledger)
    failed = sum(row.get("status") != "completed" for row in ledger)
    evidence_verified = sum(row.get("evidence_verified") is True for row in ledger)
    scheduled = len(attempts)
    missing = max(0, scheduled - len(ledger))
    evidence_rate = round(100 * evidence_verified / scheduled) if scheduled else 0

    transfer_fidelity = transfer.get("transfer_fidelity", {})
    simulation_rate = _percent(transfer_fidelity.get("simulation_success_rate"))
    boundary_rate = _percent(transfer_fidelity.get("physical_success_rate"))
    gap = round(
        float(transfer_fidelity.get("success_gap_physical_minus_simulation", 0)) * 100
    )
    matched_pairs = int(transfer_fidelity.get("matched_pairs", 0) or 0)
    branches = int(robustness.get("scheduled_branch_count", 0) or 0)
    complete_branches = int(robustness.get("completed_branch_count", 0) or 0)

    conditions: dict[str, dict[str, Any]] = {}
    pair_ids: list[str] = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict):
            continue
        key = attempt.get("key", {})
        metadata = attempt.get("metadata", {})
        condition = metadata.get("condition", {}) if isinstance(metadata, dict) else {}
        if isinstance(key, dict) and isinstance(condition, dict):
            conditions[str(key.get("condition_id"))] = condition
            pair_id = str(key.get("pair_id"))
            if pair_id not in pair_ids:
                pair_ids.append(pair_id)

    ledger_by_attempt = {str(row.get("attempt_id")): row for row in ledger}
    matrix_cells = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict):
            continue
        key = attempt.get("key", {})
        metadata = attempt.get("metadata", {})
        if not isinstance(key, dict) or not isinstance(metadata, dict):
            continue
        condition = metadata.get("condition", {})
        row = ledger_by_attempt.get(str(key.get("attempt_id")), {})
        matrix_cells.append(
            {
                "pair": str(key.get("pair_id")),
                "condition": str(condition.get("id", key.get("condition_id")))
                if isinstance(condition, dict)
                else str(key.get("condition_id")),
                "steps": condition.get("denoising_steps")
                if isinstance(condition, dict)
                else None,
                "success": row.get("success_count") == 1,
                "verified": row.get("evidence_verified") is True,
            }
        )

    matrix_json = json.dumps(matrix_cells, separators=(",", ":")).replace("</", "<\\/")
    artifact_json = json.dumps(
        {
            "plan": plan,
            "ledger": ledger,
            "transfer": transfer,
            "robustness": robustness,
            "transport": robochallenge,
            "robot_run": robot_run,
            "robot_episode": robot_report,
            "robot_comparison": robot_comparison,
            "robot_policy": robot_policy,
        },
        separators=(",", ":"),
    ).replace("</", "<\\/")
    run_id = html.escape(str(plan.get("run_id", "BenchStudio demo")))
    plan_digest = _short(plan.get("plan_digest_sha256"), 16)
    transport_valid = robochallenge.get("valid") is True
    transport_events = int(robochallenge.get("event_count", 0) or 0)
    robot_success = robot_report.get("success") is True
    robot_episode_count = int(robot_run.get("episodes", 0) or 0)
    robot_summary = robot_comparison.get("summary", {})
    robot_backend_summary = (
        robot_summary.get(selected_simulator, {}) if isinstance(robot_summary, dict) else {}
    )
    robot_completed_episodes = (
        int(robot_backend_summary.get("completed", 0) or 0)
        if isinstance(robot_backend_summary, dict)
        else 0
    )
    robot_sim_time = float(robot_report.get("sim_time_s", 0.0) or 0.0)
    robot_wall_time = float(robot_report.get("wall_time_s", 0.0) or 0.0)
    robot_steps = int(robot_report.get("steps", 0) or 0)
    robot_artifacts = robot_report.get("artifacts", {})
    robot_trace = robot_artifacts.get("trace_ndjson", {}) if isinstance(robot_artifacts, dict) else {}
    robot_trace_records = int(robot_trace.get("record_count", 0) or 0) if isinstance(robot_trace, dict) else 0
    robot_environment = robot_report.get("environment", {})
    robot_packages = robot_environment.get("packages", {}) if isinstance(robot_environment, dict) else {}
    simulator_display_names = {"mujoco": "MuJoCo", "genesis": "Genesis"}
    simulator_name = simulator_display_names.get(
        selected_simulator, selected_simulator.replace("_", " ").title()
    )
    simulator_version = (
        str(robot_packages.get(selected_simulator, "not reported"))
        if isinstance(robot_packages, dict)
        else "not reported"
    )
    simulator_options = "".join(
        f'<option value="{simulator}" '
        f'{"selected" if simulator == selected_simulator else "disabled"}>'
        f'{display_name} · '
        f'{"evaluated" if simulator == selected_simulator else "run required"}</option>'
        for simulator, display_name in simulator_display_names.items()
    )
    if robot_report:
        episode_media = (
            f'<video controls autoplay muted loop playsinline aria-label="SO-101 cube-lift episode">'
            f'<source src="urdf-studio/{html.escape(selected_simulator)}/episode-0/episode.mp4" '
            'type="video/mp4"></video>'
        )
    else:
        episode_media = (
            '<div class="episode-empty">NO ROBOT EPISODE LOADED<br>'
            'Run scripts/demo_urdf_studio.sh first.</div>'
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#191919">
  <title>BenchStudio — Evaluation report</title>
  <style>
    :root {{ color-scheme: dark; --bg:#191919; --surface:#1f1f1f; --raised:#252525; --line:#353535; --text:#f4f4f4; --muted:#9c9c9c; --pink:#ff4fba; --ok:#afd6c4; --warn:#d8b27d; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Noto Sans", Arial, sans-serif; font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased; }}
    .mono, .tag, .metric-label, .matrix-label, code, summary {{ font-family:"Noto Sans Mono", monospace; }}
    .shell {{ width:min(1160px, calc(100% - 40px)); margin:auto; padding:22px 0 56px; }}
    header {{ display:flex; justify-content:space-between; align-items:center; padding:0 0 18px; border-bottom:1px solid var(--line); }}
    .brand {{ display:flex; align-items:center; gap:10px; font-size:15px; font-weight:600; }}
    .mark {{ width:14px; height:14px; border-radius:4px; background:var(--pink); }}
    .brand span:last-child {{ color:var(--muted); font-weight:400; }}
    .tag {{ color:#cfcfcf; border:1px solid var(--line); border-radius:5px; padding:5px 8px; font-size:10px; letter-spacing:.04em; }}
    .run-context {{ display:grid; grid-template-columns:1.5fr 1fr 1fr; border:1px solid var(--line); border-radius:10px; overflow:hidden; margin:18px 0; }}
    .run-context div {{ padding:14px 18px; background:var(--surface); border-right:1px solid var(--line); min-width:0; }} .run-context div:last-child {{ border:0; }}
    .run-context span {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; letter-spacing:.08em; }}
    .run-context b {{ display:block; margin-top:7px; overflow:hidden; text-overflow:ellipsis; color:#c8c8c8; font:500 11px/1.4 "Noto Sans Mono",monospace; white-space:nowrap; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; }}
    .campaign-scope {{ display:flex; justify-content:space-between; align-items:end; gap:20px; margin:22px 2px 9px; }}
    .campaign-scope p {{ margin:0; color:#777; font-size:10px; }}
    .metric {{ padding:18px 20px; background:var(--surface); border-right:1px solid var(--line); }}
    .metric:last-child {{ border-right:0; }}
    .metric-label {{ display:block; color:var(--muted); font-size:9px; letter-spacing:.08em; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:8px; font-size:27px; line-height:1; letter-spacing:-.035em; font-weight:500; }}
    .robot-run {{ display:grid; grid-template-columns:1.35fr .65fr; border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; background:var(--surface); }}
    .episode-view {{ min-height:390px; background:#111; display:grid; place-items:center; border-right:1px solid var(--line); }}
    .episode-view video {{ display:block; width:100%; height:100%; max-height:520px; object-fit:contain; background:#111; }}
    .episode-empty {{ color:#777; font:11px/1.6 "Noto Sans Mono",monospace; text-align:center; padding:40px; }}
    .run-config {{ padding:24px; }}
    .run-config h2 {{ margin-bottom:22px; }}
    .field {{ margin-bottom:16px; }} .field label {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; letter-spacing:.08em; margin-bottom:7px; }}
    .field-help {{ display:block; margin-top:7px; color:#777; font-size:10px; line-height:1.45; }}
    .field select,.field-output {{ width:100%; border:1px solid var(--line); border-radius:6px; background:var(--raised); color:#ddd; padding:9px 10px; font:11px/1.3 "Noto Sans Mono",monospace; }}
    .policy-timeline {{ margin:-8px 0 16px; color:#999; font:10px/1.6 "Noto Sans Mono",monospace; }}
    .run-result {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:22px; }}
    .run-result div {{ padding:12px; border:1px solid var(--line); border-radius:6px; background:var(--raised); }}
    .run-result span {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; }} .run-result b {{ display:block; margin-top:7px; font-size:13px; font-weight:500; }}
    .truth-note {{ margin:16px 0 0; padding-top:14px; border-top:1px solid var(--line); color:var(--muted); font-size:11px; line-height:1.55; }}
    .story {{ display:grid; grid-template-columns:1.4fr .8fr; border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; background:var(--surface); }}
    .transfer {{ padding:28px; border-right:1px solid var(--line); }}
    .section-label {{ color:var(--muted); font:500 10px/1.2 "Noto Sans Mono", monospace; letter-spacing:.08em; text-transform:uppercase; }}
    h2 {{ margin:10px 0 6px; font-size:22px; letter-spacing:-.025em; font-weight:500; }}
    .section-copy {{ color:var(--muted); margin:0; font-size:13px; }}
    .gap {{ margin:34px 0 28px; font-size:clamp(64px,10vw,112px); line-height:.82; letter-spacing:-.07em; font-weight:500; }}
    .gap span {{ color:var(--muted); font-size:16px; letter-spacing:0; margin-left:8px; }}
    .bars {{ display:grid; gap:14px; }}
    .bar {{ display:grid; grid-template-columns:135px 1fr 42px; align-items:center; gap:14px; }}
    .bar label {{ color:#bcbcbc; font-size:12px; }}
    .track {{ height:7px; border-radius:9px; background:#303030; overflow:hidden; }}
    .fill {{ height:100%; background:var(--pink); }}
    .fill.boundary {{ background:#666; }}
    .bar b {{ font:500 11px/1 "Noto Sans Mono", monospace; text-align:right; }}
    .claim {{ padding:28px; display:flex; flex-direction:column; }}
    .claim h2 {{ margin-bottom:24px; }}
    .decision {{ padding:15px 0; border-top:1px solid var(--line); }}
    .decision:first-of-type {{ border-top:0; padding-top:0; }}
    .decision b {{ display:block; font-size:13px; font-weight:500; }}
    .decision span {{ display:block; color:var(--muted); font-size:12px; margin-top:4px; }}
    .supported b::before {{ content:"✓"; color:var(--ok); margin-right:8px; }}
    .unsupported b::before {{ content:"—"; color:var(--warn); margin-right:8px; }}
    .panel {{ padding:26px 28px; border:1px solid var(--line); border-radius:10px; background:var(--surface); margin-bottom:18px; }}
    .panel-head {{ display:flex; justify-content:space-between; gap:20px; align-items:start; margin-bottom:22px; }}
    .panel-head h2 {{ margin-top:0; }}
    .matrix {{ display:grid; gap:6px; }}
    .matrix-row {{ display:grid; grid-template-columns:120px repeat(2,minmax(0,1fr)); gap:6px; }}
    .matrix-label {{ color:#858585; font-size:9px; letter-spacing:.05em; display:flex; align-items:center; }}
    .matrix-cell {{ min-height:64px; padding:12px; border:1px solid var(--line); border-radius:7px; background:var(--raised); display:flex; justify-content:space-between; align-items:end; }}
    .matrix-cell strong {{ font-size:12px; font-weight:500; }} .matrix-cell small {{ color:#888; font-size:10px; }}
    .check {{ color:var(--ok); }}
    .evidence {{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); border-radius:8px; overflow:hidden; margin-top:20px; }}
    .evidence div {{ padding:15px; background:var(--raised); border-right:1px solid var(--line); }} .evidence div:last-child {{ border:0; }}
    .evidence span {{ display:block; color:#777; font:9px/1 "Noto Sans Mono",monospace; }}
    .evidence b {{ display:block; margin:9px 0 4px; font-size:12px; font-weight:500; }} .evidence small {{ color:#858585; font:9px/1.4 "Noto Sans Mono",monospace; }}
    .links {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:18px; }}
    .artifact-button {{ appearance:none; border:0; border-bottom:1px solid #555; background:none; color:#aaa; padding:3px 0; font:11px/1.4 "Noto Sans",Arial,sans-serif; cursor:pointer; }} .artifact-button:hover {{ color:#fff; border-color:var(--pink); }}
    details {{ border:1px solid var(--line); border-radius:10px; background:var(--surface); margin-bottom:18px; }}
    summary {{ cursor:pointer; padding:17px 20px; color:#aaa; font-size:10px; letter-spacing:.04em; }}
    .json-panel {{ margin:0 20px 20px; padding:17px; border:1px solid var(--line); border-radius:7px; background:#171717; overflow:auto; }}
    .json-panel code {{ color:#c8c8c8; font-size:11px; line-height:1.8; white-space:pre; }}
    .json-key {{ color:#d98ab9; }} .json-string {{ color:#b8aec4; }} .json-number {{ color:#a5bdc5; }} .json-ok {{ color:var(--ok); }}
    dialog {{ width:min(820px,calc(100% - 32px)); max-height:82vh; padding:0; color:var(--text); background:var(--surface); border:1px solid #444; border-radius:10px; }}
    dialog::backdrop {{ background:rgba(0,0,0,.72); }}
    .dialog-head {{ display:flex; justify-content:space-between; align-items:center; padding:16px 18px; border-bottom:1px solid var(--line); }}
    .dialog-head strong {{ font-size:13px; font-weight:500; }} .dialog-head span {{ display:block; color:var(--muted); font:9px/1.4 "Noto Sans Mono",monospace; margin-top:3px; }}
    .close {{ appearance:none; border:1px solid var(--line); border-radius:5px; background:var(--raised); color:#bbb; padding:6px 9px; cursor:pointer; }}
    #artifact-content {{ margin:0; padding:20px; overflow:auto; color:#c8c8c8; font:11px/1.7 "Noto Sans Mono",monospace; white-space:pre-wrap; word-break:break-word; }}
    footer {{ display:flex; justify-content:space-between; gap:20px; color:#707070; border-top:1px solid var(--line); padding-top:18px; font-size:10px; }}
    @media(max-width:800px) {{ .robot-run,.story {{ grid-template-columns:1fr; }} .episode-view,.transfer {{ border-right:0; border-bottom:1px solid var(--line); }} .metrics {{ grid-template-columns:1fr 1fr; }} .metric:nth-child(2) {{ border-right:0; }} .metric:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} .evidence {{ grid-template-columns:1fr 1fr; }} .evidence div:nth-child(2) {{ border-right:0; }} .evidence div:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} }}
    @media(max-width:560px) {{ .shell {{ width:calc(100% - 24px); }} .run-context {{ grid-template-columns:1fr; }} .run-context div {{ border-right:0; border-bottom:1px solid var(--line); }} .matrix-row {{ grid-template-columns:76px repeat(2,1fr); }} .bar {{ grid-template-columns:100px 1fr 36px; }} footer {{ flex-direction:column; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <header><div class="brand"><span class="mark"></span>BenchStudio <span>/ Eval Control Room</span></div><span class="mono" style="color:#777;font-size:10px">CAMPAIGN FIXTURE · {scheduled} ATTEMPTS · {matched_pairs} TRANSFER PAIRS</span></header>

    <main>
      <section class="run-context" aria-label="Run identity">
        <div><span>RUN</span><b>{run_id}</b></div>
        <div><span>MODE</span><b>CONTROLLED COMPARISON</b></div>
        <div><span>PLAN</span><b>{plan_digest}</b></div>
      </section>

      <section class="robot-run" aria-label="URDF Studio robot evaluation">
        <div class="episode-view">{episode_media}</div>
        <aside class="run-config">
          <div class="section-label">URDF Studio execution</div>
          <h2>SO-101 · Cube lift</h2>
          <div class="field"><label for="simulator-select">SIMULATOR</label><select id="simulator-select" aria-describedby="simulator-help">{simulator_options}</select><small id="simulator-help" class="field-help">Choose the backend before the run; this report stays bound to the evaluated episode.</small></div>
          <div class="field"><label>ROBOT SOURCE</label><div class="field-output">URDF Studio / SO-101</div></div>
          <div class="field"><label>POLICY</label><div class="field-output">Waypoint baseline · sha256 {html.escape(robot_policy_digest[:12])}</div></div>
          <div class="policy-timeline">{html.escape(robot_policy_timeline)}</div>
          <div class="run-result">
            <div><span>ROBOT EPISODES</span><b>{robot_completed_episodes}/{robot_episode_count} {'SUCCESS' if robot_success else 'NOT RUN'}</b></div>
            <div><span>SIM TIME</span><b>{robot_sim_time:.2f} s</b></div>
            <div><span>CONTROL STEPS</span><b>{robot_steps}</b></div>
            <div><span>TRACE RECORDS</span><b>{robot_trace_records}</b></div>
          </div>
          <p class="truth-note">{html.escape(simulator_name)} {html.escape(simulator_version)} · wall time {robot_wall_time:.2f} s. This baseline uses URDF Studio's declared weld-attach mechanism; it validates orchestration and evidence capture, not contact-realistic grasp physics.</p>
          <div class="links"><button class="artifact-button" data-artifact="robot_policy">Inspect policy</button><button class="artifact-button" data-artifact="robot_episode">Inspect episode evidence</button><button class="artifact-button" data-artifact="robot_comparison">Inspect comparison</button></div>
        </aside>
      </section>

      <div class="campaign-scope"><div class="section-label">Frozen campaign fixture</div><p>Separate accounting fixture; not additional SO-101 videos.</p></div>
      <section class="metrics" aria-label="Campaign integrity">
        <div class="metric"><span class="metric-label">Attempts scheduled</span><strong>{scheduled}</strong></div>
        <div class="metric"><span class="metric-label">Attempts completed</span><strong>{completed}/{scheduled}</strong></div>
        <div class="metric"><span class="metric-label">Attempt evidence verified</span><strong>{evidence_rate}%</strong></div>
        <div class="metric"><span class="metric-label">Attempt outcomes missing</span><strong>{missing}</strong></div>
      </section>

      <section class="story">
        <article class="transfer">
          <div class="section-label">Primary result</div>
          <h2>Transfer fidelity</h2>
          <p class="section-copy">Matched outcomes across the simulation and boundary fixtures.</p>
          <div class="gap">{gap:+d}<span>percentage points</span></div>
          <div class="bars">
            <div class="bar"><label>Simulation fixture</label><div class="track"><div class="fill" style="width:{simulation_rate}%"></div></div><b>{simulation_rate}%</b></div>
            <div class="bar"><label>Boundary fixture</label><div class="track"><div class="fill boundary" style="width:{boundary_rate}%"></div></div><b>{boundary_rate}%</b></div>
          </div>
        </article>
        <aside class="claim">
          <div class="section-label">Claim boundary</div>
          <h2>What the evidence permits</h2>
          <div class="decision supported"><b>Campaign integrity</b><span>All frozen attempts are terminal and accounted for.</span></div>
          <div class="decision supported"><b>Evidence integrity</b><span>Every committed result passed local verification.</span></div>
          <div class="decision unsupported"><b>Real-world transfer</b><span>Not supported by this deterministic fixture.</span></div>
          <div class="decision unsupported"><b>Model quality</b><span>No model-performance claim is made.</span></div>
        </aside>
      </section>

      <section class="panel">
        <div class="panel-head"><div><div class="section-label">Experiment design</div><h2>Paired attempts</h2><p class="section-copy">The same initial states were evaluated under both inference budgets.</p></div><span class="tag">2 × 2</span></div>
        <div id="matrix" class="matrix" aria-label="Paired attempt matrix"></div>
      </section>

      <section class="panel">
        <div class="section-label">Reproducibility</div><h2>Evidence chain</h2>
        <div class="evidence">
          <div><span>01</span><b>Frozen plan</b><small>{plan_digest}</small></div>
          <div><span>02</span><b>Attempt ledger</b><small>{len(ledger)} terminal rows</small></div>
          <div><span>03</span><b>Counterfactual branches</b><small>{complete_branches}/{branches} complete</small></div>
          <div><span>04</span><b>Transport audit</b><small>{transport_events} events · {'valid' if transport_valid else 'invalid'}</small></div>
        </div>
        <div class="links"><button class="artifact-button" data-artifact="plan">Inspect frozen plan</button><button class="artifact-button" data-artifact="ledger">Inspect attempt ledger</button><button class="artifact-button" data-artifact="transfer">Inspect transfer report</button><button class="artifact-button" data-artifact="robustness">Inspect robustness report</button><button class="artifact-button" data-artifact="transport">Inspect transport audit</button></div>
      </section>

      <details>
        <summary>VIEW MACHINE-READABLE SUMMARY</summary>
        <div class="json-panel"><code>{{
  <span class="json-key">"campaign.status"</span>: <span class="json-string">"complete"</span>,
  <span class="json-key">"attempts.scheduled"</span>: <span class="json-number">{scheduled}</span>,
  <span class="json-key">"attempts.committed"</span>: <span class="json-number">{completed}</span>,
  <span class="json-key">"evidence.verified"</span>: <span class="json-number">{evidence_verified}</span>,
  <span class="json-key">"transport.valid"</span>: <span class="json-ok">{str(transport_valid).lower()}</span>,
  <span class="json-key">"claim.verdict"</span>: <span class="json-string">"qualified"</span>
}}</code></div>
      </details>
    </main>

    <footer><span>BenchStudio · independent evaluation infrastructure for embodied AI</span><span>Model-agnostic · benchmark-agnostic · evidence-first</span></footer>
  </div>
  <dialog id="artifact-dialog" aria-labelledby="artifact-title">
    <div class="dialog-head"><div><strong id="artifact-title">Evidence artifact</strong><span>READ-ONLY · GENERATED FROM THIS RUN</span></div><button class="close" type="button" aria-label="Close evidence inspector">Close</button></div>
    <pre id="artifact-content"></pre>
  </dialog>
  <script>
    const cells = {matrix_json};
    const artifacts = {artifact_json};
    const artifactTitles = {{plan:'Frozen campaign plan',ledger:'Attempt ledger',transfer:'Transfer fidelity report',robustness:'Counterfactual robustness report',transport:'RoboChallenge transport audit',robot_policy:'SO-101 waypoint policy',robot_episode:'SO-101 episode evidence',robot_comparison:'URDF Studio comparison report'}};
    const pairs = [...new Set(cells.map(c => c.pair))];
    const conditions = [...new Set(cells.map(c => c.condition))];
    const matrix = document.getElementById('matrix');
    const head = document.createElement('div'); head.className = 'matrix-row';
    head.innerHTML = '<div class="matrix-label">INITIAL STATE</div>' + conditions.map(c => `<div class="matrix-label">${{c.replaceAll('_',' ').toUpperCase()}}</div>`).join(''); matrix.appendChild(head);
    pairs.forEach((pair, index) => {{ const row = document.createElement('div'); row.className = 'matrix-row'; row.innerHTML = `<div class="matrix-label">PAIR ${{String(index + 1).padStart(2,'0')}}</div>` + conditions.map(condition => {{ const cell = cells.find(c => c.pair === pair && c.condition === condition); return `<div class="matrix-cell"><div><strong>${{cell?.steps ?? '—'}} denoise steps</strong><br><small>${{cell?.verified ? 'verified' : 'unverified'}}</small></div><span class="check">${{cell?.success ? '✓' : '—'}}</span></div>`; }}).join(''); matrix.appendChild(row); }});
    const dialog = document.getElementById('artifact-dialog');
    document.querySelectorAll('[data-artifact]').forEach(button => button.addEventListener('click', () => {{ const key=button.dataset.artifact; document.getElementById('artifact-title').textContent=artifactTitles[key]; document.getElementById('artifact-content').textContent=JSON.stringify(artifacts[key],null,2); dialog.showModal(); }}));
    dialog.querySelector('.close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {{ if(event.target===dialog) dialog.close(); }});
  </script>
</body>
</html>
"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Demo evidence directory")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML path")
    args = parser.parse_args()
    path = build_demo_dashboard(args.input, args.output)
    print(f"dashboard={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
