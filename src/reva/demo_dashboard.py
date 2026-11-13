"""Build a self-contained REVA study control room."""

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


def _optional_json(path: Path) -> dict[str, Any]:
    return _load_json(path) if path.is_file() else {}


def _fallback_study() -> dict[str, Any]:
    return {
        "schema": "reva.study_definition.v1",
        "study_id": "so101-cube-grasp-cross-sim-v1",
        "title": "SO-101 cube grasp",
        "episodes_per_simulator": 100,
        "simulators": [
            {"id": "mujoco", "label": "MuJoCo", "adapter": "native", "contact_source": "constraint solver"},
            {"id": "genesis", "label": "Genesis", "adapter": "native", "contact_source": "native rigid contact"},
            {"id": "isaac", "label": "Isaac Sim", "adapter": "connector required", "contact_source": "PhysX contact reports"},
        ],
        "pairing": {"unit": "episode_index", "seed_count": 100, "seed_derivation": "sha256(study_id, episode_index)", "manifest_reused_across_simulators": True, "retry_preserves_manifest": True, "pilot_seeds": [17, 29, 43, 61]},
        "randomization": {"cube_position_jitter_m": [0.012, 0.012, 0.0], "cube_yaw_jitter_rad": 0.2, "robot_initial_state": "frozen", "policy": "frozen per condition"},
        "shared_runtime": {"physics_timestep_s": 0.0002, "control_hz": 50.0, "checker_interval_steps": 5, "max_episode_steps": 400, "grasp_attach": "none"},
        "criteria": {
            "task": [
                {"id": "lift_height", "operator": ">=", "value": 0.1, "unit": "m"},
                {"id": "stable_duration", "operator": ">=", "value": 0.5, "unit": "s"},
                {"id": "stable_drift", "operator": "<=", "value": 0.015, "unit": "m"},
                {"id": "above_plane", "operator": ">=", "value": 0.0, "unit": "m"},
            ],
            "shared": ["terminal outcome for every scheduled episode", "same manifest and policy condition across simulators", "no kinematic attach or weld", "hashed report, trace, decisions, video, and telemetry", "retry lineage preserves episode identity"],
            "simulator_specific": {"mujoco": ["constraint force", "normal impulse", "contact penetration"], "genesis": ["native contact force", "contact count", "penetration"], "isaac": ["PhysX contact impulse", "pair contacts", "penetration"]},
        },
    }


def _format_value(value: Any) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _build_workbench_document(
    *,
    study: dict[str, Any],
    study_manifest: dict[str, Any],
    episodes: list[dict[str, Any]],
    recovery: dict[str, Any],
    policy_digest: str,
    selected_sim: str,
) -> str:
    """Build the interactive evaluation surface; the narrative report is separate."""
    simulators = study.get("simulators", [])
    simulator_ids = [str(item.get("id")) for item in simulators if isinstance(item, dict)]
    simulator_labels = {
        str(item.get("id")): str(item.get("label", item.get("id")))
        for item in simulators
        if isinstance(item, dict)
    }
    simulator_configs = {
        str(item.get("id")): item
        for item in simulators
        if isinstance(item, dict) and item.get("id")
    }
    shared_runtime = study.get("shared_runtime", {})
    shared_runtime = shared_runtime if isinstance(shared_runtime, dict) else {}
    physics_ms = float(shared_runtime.get("physics_timestep_s", 0.0002) or 0.0002) * 1000
    control_hz = float(shared_runtime.get("control_hz", 50.0) or 50.0)
    planned_rows = study_manifest.get("episodes", [])
    planned_rows = planned_rows if isinstance(planned_rows, list) else []
    run_payload: dict[str, Any] = {}
    for item in episodes:
        index = int(item.get("index", 0))
        report = item.get("report", {})
        analysis = item.get("analysis", {})
        cohort = item.get("cohort", {}) if isinstance(item.get("cohort"), dict) else {}
        manifest = item.get("manifest", {})
        contact_telemetry = analysis.get("physics_contact_telemetry", {}) if isinstance(analysis, dict) else {}
        contact = contact_telemetry.get("contact", {}) if isinstance(contact_telemetry, dict) else {}
        capture = contact_telemetry.get("capture", {}) if isinstance(contact_telemetry, dict) else {}
        timeline = analysis.get("timeline", {}) if isinstance(analysis, dict) else {}
        motion = analysis.get("motion", {}) if isinstance(analysis, dict) else {}
        video = cohort.get("video", {}) if isinstance(cohort.get("video"), dict) else {}
        video_sha = str(video.get("sha256") or "")
        video_path = f"urdf-studio/{video.get('path', f'{selected_sim}/episode-{index}/episode.mp4')}"
        if video_sha:
            video_path = f"{video_path}?v={video_sha[:12]}"
        run_payload[str(index)] = {
            "episode_index": index,
            "condition": cohort.get("label", f"Episode {index + 1:02d}"),
            "seed": cohort.get("seed", manifest.get("seed")),
            "success": report.get("success") is True,
            "stop_reason": report.get("stop_reason"),
            "steps": report.get("steps"),
            "sim_time_s": report.get("sim_time_s"),
            "failure_class": analysis.get("failure_class"),
            "explanation": analysis.get("explanation"),
            "changed_parameters": cohort.get("changed_parameters", {}),
            "policy_sha256": cohort.get("policy_sha256", policy_digest),
            "video_path": video_path,
            "video_sha256": video_sha or None,
            "report_path": cohort.get("report_path", f"{selected_sim}/episode-{index}/report.json"),
            "analysis_path": cohort.get("analysis_path", f"{selected_sim}/episode-{index}/contact-analysis.json"),
            "first_contact_ms": timeline.get("first_contact_ms"),
            "last_contact_ms": timeline.get("last_contact_ms"),
            "close_command_ms": timeline.get("close_command_ms"),
            "peak_force_n": contact.get("peak_normal_force_n"),
            "penetration_m": contact.get("maximum_penetration_m"),
            "contact_records": capture.get("contact_records"),
            "displacement_m": motion.get("horizontal_displacement_m"),
            "max_lift_m": motion.get("max_lift_m"),
            "equrevaence_verified": (
                contact_telemetry.get("equrevaence", {}).get("verified") is True
                if isinstance(contact_telemetry.get("equrevaence"), dict)
                else False
            ),
        }

    rows_html = []
    for index, row in enumerate(planned_rows):
        if not isinstance(row, dict):
            continue
        seed = row.get("seed", "—")
        condition = str(row.get("policy_condition", "production_candidate")).replace("_", " ")
        placements = row.get("object_placements", {})
        placements = placements if isinstance(placements, dict) else {}
        cube = placements.get("grasp_cube", {})
        cube = cube if isinstance(cube, dict) else {}
        cube_position = cube.get("position_xyz", [])
        pose_text = (
            "cube " + ", ".join(f"{float(value):.3f}" for value in cube_position[:3]) + " m"
            if isinstance(cube_position, list) and len(cube_position) >= 3
            else "cube pose —"
        )
        cells = []
        for simulator_id in simulator_ids:
            simulator_config = simulator_configs.get(simulator_id, {})
            adapter = str(simulator_config.get("adapter", "not configured"))
            contact_source = str(simulator_config.get("contact_source", "not configured"))
            if simulator_id == selected_sim and str(index) in run_payload:
                run = run_payload[str(index)]
                state = "pass" if run["success"] else "fail"
                label = "PASS" if run["success"] else "FAIL"
                detail = str(run.get("failure_class") or run.get("stop_reason") or "terminal").replace("_", " ")
            elif simulator_id == selected_sim:
                state, label, detail = "withheld", "WITHHELD", "preflight gate"
            else:
                state, label, detail = "unavailable", "NOT RUN", "adapter unavailable"
            cells.append(
                f'<button class="coverage-cell {state}" data-episode="{index}" data-simulator="{html.escape(simulator_id)}">'
                f'<span><b>{label}</b><small>{html.escape(detail)}</small></span>'
                f'<small class="cell-runtime">{physics_ms:g} ms · {control_hz:g} Hz<br>{html.escape(adapter)} · {html.escape(contact_source)}</small></button>'
            )
        episode_id = str(row.get("episode_id", f"episode-{index:03d}"))
        rows_html.append(
            '<div class="coverage-row" data-row-index="{index}" data-row-text="{search}">'
            '<div class="episode-id"><b>{episode}</b><span>seed {seed}</span><small>{condition}</small></div>{cells}</div>'.format(
                index=index,
                search=html.escape(f"{episode_id} {index} {seed} {condition} {pose_text}".lower()),
                episode=html.escape(episode_id),
                seed=html.escape(str(seed)),
                condition=html.escape(f"{condition} · {pose_text}"),
                cells="".join(cells),
            )
        )

    clock = study.get("shared_runtime", {}).get("clock_contract", {})
    if not isinstance(clock, dict):
        clock = {}
    run_json = json.dumps(run_payload, separators=(",", ":")).replace("</", "<\\/")
    manifest_json = json.dumps(planned_rows, separators=(",", ":")).replace("</", "<\\/")
    simulator_json = json.dumps(
        {
            str(item.get("id")): item
            for item in simulators
            if isinstance(item, dict) and item.get("id")
        },
        separators=(",", ":"),
    ).replace("</", "<\\/")
    runtime_json = json.dumps(
        study.get("shared_runtime", {}), separators=(",", ":")
    ).replace("</", "<\\/")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>REVA — Evaluation Workbench</title>
<style>
:root{{--bg:#151515;--panel:#1b1b1b;--raised:#222;--line:#343434;--text:#e9e9e9;--muted:#818181;--pink:#ff4fba;--ok:#9dcbb7;--warn:#d7ae70;--bad:#d08b7b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:13px/1.45 Inter,"Helvetica Neue",Arial,sans-serif;overflow:hidden}}button,input,select,code,.mono{{font-family:"SFMono-Regular",Consolas,monospace}}button{{color:inherit}}.app{{display:grid;grid-template-rows:48px 1fr;height:100vh}}.topbar{{display:flex;align-items:center;gap:24px;padding:0 16px;border-bottom:1px solid var(--line);background:#181818}}.brand{{display:flex;align-items:center;gap:8px;font-weight:650;white-space:nowrap}}.mark{{width:11px;height:11px;border-radius:3px;background:var(--pink)}}.mode-tabs{{display:flex;height:100%}}.mode-tabs button{{border:0;border-bottom:2px solid transparent;background:none;padding:0 15px;color:#888;cursor:pointer}}.mode-tabs button.active{{color:#eee;border-color:var(--pink)}}.topbar a{{margin-left:auto;color:#aaa;text-decoration:none;border-bottom:1px solid #555;font-size:11px}}.workspace{{display:grid;grid-template-columns:220px minmax(520px,1fr) 390px;min-height:0}}.sidebar,.inspector{{background:var(--panel);overflow:auto}}.sidebar{{border-right:1px solid var(--line);padding:16px}}.inspector{{border-left:1px solid var(--line)}}.kicker{{color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace;letter-spacing:.08em}}h1{{margin:7px 0 4px;font-size:17px;font-weight:560;letter-spacing:-.02em}}h2{{margin:5px 0;font-size:15px;font-weight:560}}p{{margin:5px 0;color:var(--muted)}}.study-id{{color:#666;font:9px/1.4 "SFMono-Regular",Consolas,monospace;overflow-wrap:anywhere}}.progress{{margin:18px 0}}.progress-head{{display:flex;justify-content:space-between;font-size:10px}}.track{{height:4px;background:#303030;margin-top:8px}}.fill{{width:4%;height:100%;background:var(--pink)}}.clock-list{{margin:18px 0;border-top:1px solid var(--line)}}.clock-list div{{padding:10px 0;border-bottom:1px solid var(--line)}}.clock-list span,.clock-list b{{display:block}}.clock-list span{{color:#777;font-size:9px}}.clock-list b{{margin-top:3px;font:500 10px/1.4 "SFMono-Regular",Consolas,monospace}}.filter{{margin-top:15px}}.filter label{{display:block;margin-bottom:6px;color:#777;font:9px/1 "SFMono-Regular",Consolas,monospace}}.filter input,.filter select{{width:100%;border:1px solid var(--line);border-radius:4px;background:#202020;color:#ddd;padding:8px;font-size:10px}}
.main-panel{{min-width:0;overflow:auto;background:#171717}}.view{{display:none}}.view.active{{display:block}}.report-view.active{{height:100%;min-height:0}}.report-frame{{display:block;width:100%;height:100%;min-height:calc(100vh - 48px);border:0;background:#171717}}.view-head{{position:sticky;top:0;z-index:4;display:flex;justify-content:space-between;align-items:end;padding:15px 18px;background:#191919;border-bottom:1px solid var(--line)}}.view-head p{{font-size:11px}}.legend{{display:flex;gap:12px;color:#777;font-size:9px}}.legend i{{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px}}.legend .actual{{background:var(--warn)}}.legend .withheld{{background:#666}}.legend .unavailable{{background:#333}}.coverage-head,.coverage-row{{display:grid;grid-template-columns:170px repeat({max(1,len(simulator_ids))},minmax(145px,1fr))}}.coverage-head{{position:sticky;top:68px;z-index:3;background:var(--raised);border-bottom:1px solid var(--line)}}.coverage-head div{{padding:9px 11px;color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace;border-right:1px solid var(--line)}}.coverage-row{{border-bottom:1px solid #292929}}.episode-id{{padding:9px 11px;border-right:1px solid var(--line)}}.episode-id b,.episode-id span,.episode-id small{{display:block}}.episode-id b{{font:500 10px/1.3 "SFMono-Regular",Consolas,monospace}}.episode-id span,.episode-id small{{color:#6f6f6f;font-size:8px}}.coverage-cell{{display:flex;justify-content:space-between;align-items:center;gap:8px;border:0;border-right:1px solid var(--line);background:none;padding:9px 11px;text-align:left;cursor:pointer}}.coverage-cell:hover,.coverage-cell.selected{{background:#292929;box-shadow:inset 2px 0 var(--pink)}}.coverage-cell b{{font-size:9px}}.coverage-cell small{{color:#6f6f6f;font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.coverage-cell.fail b{{color:var(--warn)}}.coverage-cell.pass b{{color:var(--ok)}}.coverage-cell.withheld b{{color:#888}}.coverage-cell.unavailable b{{color:#555}}
.inspector-head{{padding:15px 16px;border-bottom:1px solid var(--line)}}.inspector-head span{{color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace}}.inspector video{{display:block;width:100%;aspect-ratio:16/9;background:#090909;object-fit:contain}}.inspector video[hidden]{{display:none!important}}.inspect-block{{padding:14px 16px;border-bottom:1px solid var(--line)}}.inspect-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.inspect-grid div{{padding:9px;background:var(--raised);border:1px solid var(--line);border-radius:4px;min-width:0}}.inspect-grid span,.inspect-grid b{{display:block}}.inspect-grid span{{color:#777;font-size:8px}}.inspect-grid b{{margin-top:4px;font:500 10px/1.3 "SFMono-Regular",Consolas,monospace;overflow-wrap:anywhere}}.parameter-list{{font:9px/1.6 "SFMono-Regular",Consolas,monospace;color:#aaa;word-break:break-word}}.timeline{{position:relative;height:72px;margin-top:12px;border-left:1px solid #555;border-right:1px solid #555;background:repeating-linear-gradient(90deg,#242424 0,#242424 1px,transparent 1px,transparent 10%)}}.timeline .event{{position:absolute;height:10px;border-radius:2px}}.timeline .policy{{top:12px;background:#777}}.timeline .contact{{top:31px;background:var(--pink);min-width:2px}}.timeline .checker{{top:50px;width:1px;background:#666}}.timeline-labels{{display:flex;justify-content:space-between;color:#666;font-size:8px;margin-top:3px}}.compare-strip{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:8px}}.sim-viewport{{min-width:0;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:#111}}.sim-viewport video,.sim-empty{{width:100%;aspect-ratio:16/9;background:#090909}}.sim-empty{{display:grid;place-items:center;color:#666;font:8px/1.2 "SFMono-Regular",Consolas,monospace;text-align:center}}.sim-meta{{padding:7px}}.sim-meta b,.sim-meta span{{display:block}}.sim-meta b{{font-size:9px}}.sim-meta span{{color:#666;font-size:8px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.sim-meta .actual{{color:var(--ok)}}.sync-head{{display:flex;justify-content:space-between;gap:10px;align-items:center}}.sync-head output{{color:#aaa;font:9px/1.2 "SFMono-Regular",Consolas,monospace}}
.coverage-cell>span{{min-width:0}}.coverage-cell>span b,.coverage-cell>span small{{display:block}}.cell-runtime{{text-align:right;line-height:1.4!important;max-width:48%;white-space:normal!important}}.study-summary{{padding:11px;border:1px solid var(--line);border-radius:5px;background:#202020}}.study-summary>b{{display:block;margin:6px 0;color:var(--warn);font:600 10px/1.3 "SFMono-Regular",Consolas,monospace}}.study-summary dl{{display:grid;grid-template-columns:1fr auto;gap:3px 8px;margin:8px 0;font:8px/1.35 "SFMono-Regular",Consolas,monospace}}.study-summary dt{{color:#666}}.study-summary dd{{margin:0;color:#bbb;text-align:right}}.study-summary p{{font-size:9px}}.sim-params{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 5px;margin:7px 0 0;padding-top:6px;border-top:1px solid #303030;font:7px/1.3 "SFMono-Regular",Consolas,monospace}}.sim-params dt{{color:#555}}.sim-params dd{{margin:0;color:#999;text-align:right;overflow-wrap:anywhere}}.parameter-state{{color:#666;font:7px/1.2 "SFMono-Regular",Consolas,monospace;margin-top:6px}}.primary-viewport{{position:relative;background:#090909}}.primary-empty{{display:grid;place-items:center;min-height:218px;padding:28px;text-align:center}}.primary-empty[hidden]{{display:none!important}}.primary-empty b,.primary-empty span{{display:block}}.primary-empty b{{font:11px/1.3 "SFMono-Regular",Consolas,monospace;color:#aaa}}.primary-empty span{{margin-top:8px;color:#666;font-size:9px}}.sim-viewport{{padding:0;border:1px solid var(--line);color:inherit;text-align:left;cursor:pointer}}.sim-viewport.selected{{border-color:var(--pink);box-shadow:0 0 0 1px var(--pink)}}
.timeline .lane-label{{position:absolute;left:5px;z-index:2;color:#aaa;font:7px/1 "SFMono-Regular",Consolas,monospace}}.timeline .lane-policy{{top:13px}}.timeline .lane-contact{{top:32px}}.timeline .lane-checker{{top:52px}}.timeline .checker-band{{position:absolute;left:0;right:0;top:48px;height:16px;background:repeating-linear-gradient(90deg,transparent 0,transparent calc(10% - 1px),#555 calc(10% - 1px),#555 10%)}}.trace-readout{{display:grid;grid-template-columns:1fr auto;gap:4px 10px;margin:10px 0 0;font:8px/1.35 "SFMono-Regular",Consolas,monospace}}.trace-readout dt{{color:#666}}.trace-readout dd{{margin:0;color:#bbb;text-align:right}}.trace-note{{margin-top:9px!important;font-size:9px!important;line-height:1.45!important}}
@media(max-width:1050px){{.workspace{{grid-template-columns:190px 1fr 330px}}}}@media(max-width:820px){{body{{overflow:auto}}.app{{height:auto}}.workspace{{grid-template-columns:1fr}}.sidebar,.inspector{{border:0;border-bottom:1px solid var(--line)}}.main-panel{{max-height:70vh}}.inspector{{min-height:500px}}}}
</style></head><body><div class="app"><header class="topbar"><div class="brand"><span class="mark"></span>REVA <span style="color:#777;font-weight:400">/ Evaluation workbench</span></div></header>
<div class="workspace"><aside class="sidebar"><span class="kicker">ACTIVE STUDY</span><h1>{html.escape(str(study.get("title","Robot evaluation")))}</h1><div class="study-id">{html.escape(str(study.get("study_id","—")))}</div><div class="progress"><div class="progress-head"><span>PREFLIGHT</span><b>{len(episodes)} / {len(planned_rows)}</b></div><div class="track"><div class="fill"></div></div><p>Full batch blocked by task-success gate.</p></div><section class="study-summary"><span class="kicker">STUDY STATUS</span><b>BATCH BLOCKED</b><dl><dt>Executed</dt><dd>{len(episodes)} / {len(planned_rows)}</dd><dt>Task passes</dt><dd>{sum(1 for run in run_payload.values() if run["success"])} / {len(episodes)}</dd><dt>Recorded backend</dt><dd>{html.escape(simulator_labels.get(selected_sim,selected_sim))}</dd><dt>Awaiting data</dt><dd>{max(0,len(simulator_ids)-1)} backends</dd></dl><p>No successful lift was observed; unscheduled episodes remain withheld.</p></section><div class="clock-list"><div><span>PHYSICS CLOCK</span><b>{float(clock.get("physics_step_s",0.0002))*1000:g} ms / step</b></div><div><span>CONTROL CLOCK</span><b>{float(clock.get("control_tick_s",0.02))*1000:g} ms · {int(clock.get("physics_steps_per_control_tick",100))} physics steps</b></div><div><span>CHECKER CLOCK</span><b>{int(clock.get("checker_interval_control_ticks",5))} control ticks · {float(clock.get("checker_period_s",0.1))*1000:g} ms · {int(clock.get("physics_steps_per_checker_tick",500))} physics steps</b></div></div><div class="filter"><label for="episode-search">FILTER EPISODES</label><input id="episode-search" placeholder="episode, seed, condition, cube pose"></div><div class="filter"><label for="status-filter">STATUS</label><select id="status-filter"><option value="all">All</option><option value="fail">Failed preflight</option><option value="withheld">Withheld</option><option value="unavailable">Unavailable</option></select></div></aside>
<main class="main-panel"><section class="view active" id="view-coverage"><div class="view-head"><div><span class="kicker">100 EPISODES × {len(simulator_ids)} SIMULATORS</span><h2>Coverage matrix</h2><p>Select any cell to inspect its run or planned identity.</p></div><div class="legend"><span><i class="actual"></i>executed</span><span><i class="withheld"></i>withheld</span><span><i class="unavailable"></i>not run</span></div></div><div class="coverage-head"><div>EPISODE IDENTITY</div>{''.join(f'<div>{html.escape(simulator_labels.get(sid,sid))}</div>' for sid in simulator_ids)}</div>{''.join(rows_html)}</section>
</main>
<aside class="inspector"><div class="inspector-head"><span id="inspect-kicker">RUN INSPECTOR</span><h2 id="inspect-title">Select a matrix cell</h2><p id="inspect-summary">Episode evidence and cross-simulator status appear here.</p></div><div class="primary-viewport"><video id="inspect-video" controls muted playsinline hidden><source id="inspect-source" type="video/mp4"></video><div class="primary-empty" id="inspect-empty" hidden><div><b id="inspect-empty-title">AWAITING DATA</b><span id="inspect-empty-detail">No recording exists for this backend.</span></div></div></div><div class="inspect-block"><div class="inspect-grid"><div><span>STATUS</span><b id="inspect-status">—</b></div><div><span>SEED</span><b id="inspect-seed">—</b></div><div><span>DURATION</span><b id="inspect-duration">—</b></div><div><span>POLICY</span><b id="inspect-policy">—</b></div><div><span>EVIDENCE</span><b id="inspect-evidence">—</b></div><div><span>REPORT</span><b id="inspect-report">—</b></div></div></div><div class="inspect-block"><span class="kicker">PARAMETER DELTA / DIAGNOSIS</span><div class="parameter-list" id="inspect-detail">No cell selected.</div></div><div class="inspect-block"><span class="kicker">TIME-ALIGNED TRACE · SIMULATION CLOCK</span><div class="timeline" id="timeline"><span class="lane-label lane-policy">POLICY EXECUTION</span><span class="lane-label lane-contact">ROBOT–CUBE CONTACT</span><span class="lane-label lane-checker">SUCCESS CHECKS</span><div class="event policy" id="policy-event"></div><div class="event contact" id="contact-event"></div><div class="checker-band"></div></div><div class="timeline-labels"><span>0.000 s</span><span id="timeline-end">—</span></div><dl class="trace-readout"><dt>Contact onset</dt><dd id="trace-contact-onset">—</dd><dt>Contact end</dt><dd id="trace-contact-end">—</dd><dt>Contact duration</dt><dd id="trace-contact-duration">—</dd><dt>Peak normal solver force</dt><dd id="trace-peak-force">—</dd><dt>Physics sampling</dt><dd>0.2 ms · 5 kHz</dd><dt>Policy control</dt><dd>20 ms · 50 Hz</dd><dt>Success checker</dt><dd>100 ms · 10 Hz</dd></dl><p class="trace-note" id="timeline-caption">Times use simulation time. Force is a MuJoCo constraint-solver value from physics-step diagnostic replay; it is not calibrated hardware force.</p></div><div class="inspect-block"><div class="sync-head"><span class="kicker">SYNCHRONIZED VIEWPORTS</span><output id="sync-time">t = 0.00 s</output></div><div class="compare-strip" id="compare-strip"></div></div></aside></div></div>
<script>const simulatorConfig={simulator_json};const sharedRuntime={runtime_json};const simulatorOrder={json.dumps(simulator_ids)};function switchSimulator(simulator){{const selected=document.querySelector('.coverage-cell.selected');if(!selected)return;const target=document.querySelector(`.coverage-cell[data-episode="${{selected.dataset.episode}}"][data-simulator="${{simulator}}"]`);if(target)target.click();}}function decorateSimulatorParameters(){{document.querySelector('.sync-head .kicker').textContent='SIMULATOR SELECTOR';const selected=document.querySelector('.coverage-cell.selected');document.querySelectorAll('.sim-viewport').forEach((card,index)=>{{const simulator=simulatorOrder[index];card.dataset.simulator=simulator;card.setAttribute('role','button');card.tabIndex=0;card.classList.toggle('selected',selected?.dataset.simulator===simulator);card.onclick=()=>switchSimulator(simulator);card.onkeydown=event=>{{if(event.key==='Enter'||event.key===' '){{event.preventDefault();switchSimulator(simulator);}}}};if(card.querySelector('.sim-params'))return;const config=simulatorConfig[simulator]||{{}};const preview=card.querySelector('.sim-preview');const applied=Boolean(preview);if(preview){{const recorded=document.createElement('div');recorded.className='sim-empty';recorded.textContent='RECORDED DATA';preview.replaceWith(recorded);}}const clock=sharedRuntime.clock_contract||{{}};const rows=[['physics dt',`${{Number(sharedRuntime.physics_timestep_s||clock.physics_step_s||0)*1000}} ms`],['control',`${{Number(sharedRuntime.control_hz||0)}} Hz`],['checker',`${{Number(clock.checker_period_s||0)*1000}} ms`],['horizon',`${{sharedRuntime.max_episode_steps??'—'}} ticks`],['adapter',config.adapter||'not configured'],['contact',config.contact_source||'not configured']];const meta=card.querySelector('.sim-meta');const state=document.createElement('div');state.className='parameter-state';state.textContent=applied?'APPLIED PARAMETERS':'PLANNED PARAMETERS';const list=document.createElement('dl');list.className='sim-params';rows.forEach(([name,value])=>{{const term=document.createElement('dt');term.textContent=name;const detail=document.createElement('dd');detail.textContent=value;list.append(term,detail);}});meta.append(state,list);}});const video=document.getElementById('inspect-video');const empty=document.getElementById('inspect-empty');empty.hidden=!video.hidden;if(video.hidden&&selected){{const config=simulatorConfig[selected.dataset.simulator]||{{}};document.getElementById('inspect-empty-title').textContent=`${{config.label||selected.dataset.simulator}} · AWAITING DATA`;document.getElementById('inspect-empty-detail').textContent=`${{config.adapter||'adapter not configured'}} · ${{config.contact_source||'contact source not configured'}} · planned parameters shown below`;}}}}new MutationObserver(decorateSimulatorParameters).observe(document.getElementById('compare-strip'),{{childList:true}});</script>
<script>const runs={run_json};const manifest={manifest_json};const simulatorIds={json.dumps(simulator_ids)};const simulatorLabels={json.dumps(simulator_labels)};const selectedSimulator={json.dumps(selected_sim)};const tabs=document.querySelectorAll('[data-view]');tabs.forEach(tab=>tab.addEventListener('click',()=>{{tabs.forEach(item=>item.classList.toggle('active',item===tab));document.querySelectorAll('.view').forEach(view=>view.classList.toggle('active',view.id===`view-${{tab.dataset.view}}`));if(tab.dataset.view==='report'){{const frame=document.querySelector('.report-frame');if(!frame.src)frame.src=frame.dataset.src;}}}}));const cells=document.querySelectorAll('.coverage-cell');function fmt(value,digits=1){{return value==null?'—':Number(value).toFixed(digits)}}const masterVideo=document.getElementById('inspect-video');function syncViewports(){{document.getElementById('sync-time').textContent=`t = ${{masterVideo.currentTime.toFixed(2)}} s`;document.querySelectorAll('.sim-preview').forEach(preview=>{{if(Math.abs(preview.currentTime-masterVideo.currentTime)>.08)preview.currentTime=masterVideo.currentTime;if(masterVideo.paused)preview.pause();else preview.play().catch(()=>{{}});}});}}['timeupdate','play','pause','seeking','loadedmetadata'].forEach(event=>masterVideo.addEventListener(event,syncViewports));function selectCell(button){{cells.forEach(cell=>cell.classList.toggle('selected',cell===button));const index=Number(button.dataset.episode);const simulator=button.dataset.simulator;const plan=manifest[index]||{{}};const run=simulator===selectedSimulator?runs[String(index)]:null;document.getElementById('inspect-title').textContent=`${{plan.episode_id||`episode-${{String(index).padStart(3,'0')}}`}} · ${{simulatorLabels[simulator]||simulator}}`;document.getElementById('inspect-seed').textContent=plan.seed??'—';const video=masterVideo;if(run){{document.getElementById('inspect-status').textContent=run.success?'PASS':'FAIL';document.getElementById('inspect-duration').textContent=`${{fmt(run.sim_time_s)}} s · ${{run.steps}} control ticks`;document.getElementById('inspect-policy').textContent=String(run.policy_sha256||'').slice(0,12);document.getElementById('inspect-evidence').textContent=run.equrevaence_verified?'VERIFIED':'UNVERIFIED';document.getElementById('inspect-report').textContent=run.report_path||'—';document.getElementById('inspect-summary').textContent=run.explanation||run.failure_class||run.stop_reason;document.getElementById('inspect-detail').textContent=Object.entries(run.changed_parameters||{{}}).map(([k,v])=>`${{k}}=${{v}}`).join(' · ')||'baseline control';document.getElementById('inspect-source').src=run.video_path;video.hidden=false;video.load();const duration=Math.max(Number(run.sim_time_s)||1,.001);const close=Number(run.close_command_ms||0)/1000;const hasContact=run.first_contact_ms!=null&&run.last_contact_ms!=null;const first=hasContact?Number(run.first_contact_ms)/1000:0;const last=hasContact?Number(run.last_contact_ms)/1000:0;const policyEvent=document.getElementById('policy-event');policyEvent.style.left='0%';policyEvent.style.width=`${{Math.min(100,close/duration*100)}}%`;const contactEvent=document.getElementById('contact-event');contactEvent.style.left=hasContact?`${{Math.min(100,first/duration*100)}}%`:'0%';contactEvent.style.width=hasContact?`${{Math.max(.5,Math.min(100,(last-first)/duration*100))}}%`:'0';document.getElementById('timeline-end').textContent=`${{duration.toFixed(3)}} s`;document.getElementById('trace-contact-onset').textContent=hasContact?`${{first.toFixed(3)}} s`:'not observed';document.getElementById('trace-contact-end').textContent=hasContact?`${{last.toFixed(3)}} s`:'not observed';document.getElementById('trace-contact-duration').textContent=hasContact?`${{((last-first)*1000).toFixed(1)}} ms`:'0 ms';document.getElementById('trace-peak-force').textContent=run.peak_force_n==null?'not recorded':`${{Number(run.peak_force_n).toFixed(1)}} N`;document.getElementById('timeline-caption').textContent='Times use simulation time. Force is a MuJoCo constraint-solver value from physics-step diagnostic replay; it is not calibrated hardware force.';}}else{{document.getElementById('inspect-status').textContent=simulator===selectedSimulator?'WITHHELD':'NOT RUN';document.getElementById('inspect-duration').textContent='—';document.getElementById('inspect-policy').textContent=plan.policy_condition||'—';document.getElementById('inspect-evidence').textContent='NOT RECORDED';document.getElementById('inspect-report').textContent='—';document.getElementById('inspect-summary').textContent=simulator===selectedSimulator?'Blocked by preflight gate.':'Simulator execution is unavailable.';document.getElementById('inspect-detail').textContent=`planned cube pose ${{JSON.stringify(plan.object_placements?.grasp_cube?.position_xyz||[])}}`;video.hidden=true;document.getElementById('timeline-end').textContent='—';document.getElementById('trace-contact-onset').textContent='not recorded';document.getElementById('trace-contact-end').textContent='not recorded';document.getElementById('trace-contact-duration').textContent='—';document.getElementById('trace-peak-force').textContent='not recorded';document.getElementById('timeline-caption').textContent='No simulator trace exists for this cell; only the frozen clock and parameter plan are shown.';}}document.getElementById('compare-strip').innerHTML=simulatorIds.map(id=>{{const sameRun=id===selectedSimulator?runs[String(index)]:null;const label=simulatorLabels[id]||id;if(sameRun)return `<article class="sim-viewport"><video class="sim-preview" muted playsinline src="${{sameRun.video_path}}"></video><div class="sim-meta"><b>${{label}}</b><span class="actual">RECORDED · MATCHED CAMERA</span><span>trajectory available</span><span>divergence reference</span></div></article>`;return `<article class="sim-viewport"><div class="sim-empty">AWAITING<br>DATA</div><div class="sim-meta"><b>${{label}}</b><span>camera pending</span><span>trajectory pending</span><span>divergence —</span></div></article>`;}}).join('');syncViewports();}}cells.forEach(cell=>cell.addEventListener('click',()=>selectCell(cell)));const search=document.getElementById('episode-search');const status=document.getElementById('status-filter');function filterRows(){{const query=search.value.trim().toLowerCase();document.querySelectorAll('.coverage-row').forEach(row=>{{const text=row.dataset.rowText||'';const matchesText=!query||text.includes(query);const matchesStatus=status.value==='all'||row.querySelector(`.${{status.value}}`);row.style.display=matchesText&&matchesStatus?'grid':'none';}})}}search.addEventListener('input',filterRows);status.addEventListener('change',filterRows);const firstActual=document.querySelector('.coverage-cell.fail,.coverage-cell.pass');if(firstActual)selectCell(firstActual);</script></body></html>'''


def build_demo_dashboard(input_dir: Path, output_path: Path) -> Path:
    """Render a standalone cross-simulator study dashboard."""
    root = Path(input_dir)
    robot_root = root / "urdf-studio"
    run = _optional_json(robot_root / "run.json")
    comparison = _optional_json(robot_root / "comparison.json")
    simulator_debug = _optional_json(robot_root / "simulator-debug.json")
    recovery = _optional_json(robot_root / "recovery.json")
    pilot_cohort = _optional_json(robot_root / "pilot-cohort.json")
    study_manifest = _optional_json(robot_root / "study-manifest.json")
    policy_path = robot_root / "scenario" / "waypoints.json"
    policy = _optional_json(policy_path)
    study = _optional_json(robot_root / "scenario" / "study-definition.json") or _fallback_study()

    simulators = study.get("simulators", [])
    simulators = simulators if isinstance(simulators, list) else []
    per_sim = int(study.get("episodes_per_simulator", 100) or 100)
    study_id = html.escape(str(study.get("study_id", "unidentified-study")))
    study_title = html.escape(str(study.get("title", "Robot evaluation")))
    policy_digest = hashlib.sha256(policy_path.read_bytes()).hexdigest() if policy_path.is_file() else "not-loaded"
    pairing = study.get("pairing", {}) if isinstance(study.get("pairing"), dict) else {}
    randomization = study.get("randomization", {}) if isinstance(study.get("randomization"), dict) else {}
    runtime = study.get("shared_runtime", {}) if isinstance(study.get("shared_runtime"), dict) else {}
    criteria = study.get("criteria", {}) if isinstance(study.get("criteria"), dict) else {}
    backend_data = simulator_debug.get("backends", {}) if isinstance(simulator_debug.get("backends"), dict) else {}

    episode_count = int(run.get("episodes", 0) or 0)
    selected_sim = str((run.get("sims") or ["mujoco"])[0])
    episodes: list[dict[str, Any]] = []
    for index in range(episode_count):
        base = robot_root / selected_sim / f"episode-{index}"
        report = _optional_json(base / "report.json")
        if report:
            episodes.append({"index": index, "report": report, "manifest": _optional_json(robot_root / "manifests" / f"episode-{index}.json"), "analysis": _optional_json(base / "contact-analysis.json")})

    cohort_entries = pilot_cohort.get("entries", [])
    if isinstance(cohort_entries, list) and cohort_entries:
        cohort_episodes = []
        for entry in cohort_entries:
            if not isinstance(entry, dict):
                continue
            index = int(entry.get("episode_index", 0) or 0)
            report_path = robot_root / str(entry.get("report_path", ""))
            analysis_path = robot_root / str(entry.get("analysis_path", ""))
            report = _optional_json(report_path)
            if not report:
                continue
            cohort_episodes.append({
                "index": index,
                "report": report,
                "manifest": _optional_json(robot_root / "manifests" / f"episode-{index}.json"),
                "analysis": _optional_json(analysis_path),
                "cohort": entry,
            })
        if cohort_episodes:
            episodes = cohort_episodes

    pilot_passes = sum(item["report"].get("success") is True for item in episodes)
    pilot_failures = len(episodes) - pilot_passes
    withheld_count = max(0, per_sim - len(episodes))
    summary = comparison.get("summary", {}) if isinstance(comparison.get("summary"), dict) else {}

    analyses = [item.get("analysis", {}) for item in episodes]
    replay_verified = bool(analyses) and all(
        isinstance(analysis.get("physics_contact_telemetry"), dict)
        and isinstance(analysis["physics_contact_telemetry"].get("equrevaence"), dict)
        and analysis["physics_contact_telemetry"]["equrevaence"].get("verified") is True
        for analysis in analyses
    )
    telemetry_complete = bool(analyses) and all(
        isinstance(analysis.get("physics_contact_telemetry"), dict)
        and isinstance(analysis["physics_contact_telemetry"].get("capture"), dict)
        and analysis["physics_contact_telemetry"]["capture"].get("all_robot_cube_contacts_retained") is True
        for analysis in analyses
    )
    taxonomy_complete = bool(analyses) and all(analysis.get("failure_class") for analysis in analyses)
    gate_checks = [
        ("Scenario replay", replay_verified, "evaluated run and diagnostic replay agree"),
        ("Policy and assets", policy_digest != "not-loaded", "content-addressed inputs retained"),
        ("Contact telemetry", telemetry_complete, "physics-step contacts retained"),
        ("Failure taxonomy", taxonomy_complete, "every preflight has a classified outcome"),
        ("Task success observed", pilot_passes > 0, "at least one lift checker pass required"),
        ("Authorize 100 episodes", pilot_passes > 0, "blocked until the production candidate passes preflight"),
    ]
    gate_rows_html = "".join(
        '<div class="gate-row">'
        f'<span class="gate-icon {"pass" if passed else "fail"}">{"PASS" if passed else "FAIL"}</span>'
        f'<div><b>{html.escape(label)}</b><small>{html.escape(detail)}</small></div></div>'
        for label, passed, detail in gate_checks
    )

    planned_rows = study_manifest.get("episodes", [])
    manifest_rows_html = []
    if isinstance(planned_rows, list):
        for position, row in enumerate(planned_rows):
            if not isinstance(row, dict):
                continue
            placements = row.get("object_placements", {})
            cube = placements.get("grasp_cube", {}) if isinstance(placements, dict) else {}
            xyz = cube.get("position_xyz", []) if isinstance(cube, dict) else []
            pose_text = "—"
            if isinstance(xyz, list) and len(xyz) == 3:
                pose_text = f"{float(xyz[0]):.3f}, {float(xyz[1]):+.3f}, {float(xyz[2]):.3f}"
            status = "preflight executed" if position < len(episodes) else "withheld"
            manifest_rows_html.append(
                '<div class="manifest-row">'
                f'<div><b>{html.escape(str(row.get("episode_id", f"episode-{position:03d}")))}</b><span>index {position:03d}</span></div>'
                f'<div>{html.escape(str(row.get("seed", "—")))}</div>'
                f'<div>{html.escape(str(row.get("policy_condition", "production_candidate")).replace("_", " "))}</div>'
                f'<div>{html.escape(pose_text)}</div>'
                f'<div><i class="status {"active" if position < len(episodes) else ""}"></i>{status}</div></div>'
            )

    simulator_rows = []
    for simulator in simulators:
        if not isinstance(simulator, dict):
            continue
        sid = str(simulator.get("id", "unknown"))
        backend = backend_data.get(sid, {}) if isinstance(backend_data.get(sid), dict) else {}
        backend_summary = summary.get(sid, {}) if isinstance(summary.get(sid), dict) else {}
        completed = int(backend_summary.get("completed", backend.get("completed", 0)) or 0)
        status = str(backend.get("status", "not_run"))
        if sid == selected_sim and episodes:
            status = "pilot evaluated"
        elif status == "failed":
            status = "adapter blocked"
        else:
            status = "ready to schedule" if str(simulator.get("adapter")) == "native" else "connector required"
        simulator_rows.append('<div class="sim-row">'
            f'<div><b>{html.escape(str(simulator.get("label", sid)))}</b><span>{html.escape(str(simulator.get("adapter", "—")))}</span></div>'
            f'<div><b>{per_sim}</b><span>planned episodes</span></div><div><b>{completed}</b><span>pilot retained</span></div>'
            f'<div><b>{html.escape(str(simulator.get("contact_source", "—")))}</b><span>contact evidence</span></div>'
            f'<div><i class="status {"active" if completed else ""}"></i>{html.escape(status)}</div></div>')

    task_criteria = []
    for criterion in criteria.get("task", []) if isinstance(criteria.get("task"), list) else []:
        if isinstance(criterion, dict):
            label = str(criterion.get("id", "criterion")).replace("_", " ")
            task_criteria.append(f'<li><span>{html.escape(label)}</span><b>{html.escape(str(criterion.get("operator", "")))} {html.escape(_format_value(criterion.get("value")))} {html.escape(str(criterion.get("unit", "")))}</b></li>')
    shared_criteria = "".join(f'<li>{html.escape(str(item))}</li>' for item in criteria.get("shared", []) if isinstance(criteria.get("shared"), list))
    specific_rows = []
    simulator_specific = criteria.get("simulator_specific", {})
    if isinstance(simulator_specific, dict):
        labels = {str(item.get("id")): str(item.get("label")) for item in simulators if isinstance(item, dict)}
        for sid, items in simulator_specific.items():
            if str(sid) != selected_sim:
                continue
            values = items if isinstance(items, list) else []
            specific_rows.append(f'<li><span>{html.escape(labels.get(str(sid), str(sid)))}</span><b>{html.escape(" · ".join(map(str, values)))}</b></li>')

    seed_values = pairing.get("pilot_seeds", [])
    seed_text = ", ".join(str(seed) for seed in seed_values) if isinstance(seed_values, list) else "—"
    jitter = randomization.get("cube_position_jitter_m", [0, 0, 0])
    jitter_text = " × ".join(f"{float(value) * 1000:g}" for value in jitter) + " mm" if isinstance(jitter, list) else "—"
    yaw = float(randomization.get("cube_yaw_jitter_rad", 0.0) or 0.0)

    episode_nav, episode_rows, episode_media = [], [], []
    for position, episode in enumerate(episodes):
        index, report, manifest, analysis = int(episode["index"]), episode["report"], episode["manifest"], episode["analysis"]
        cohort_entry = episode.get("cohort", {}) if isinstance(episode.get("cohort"), dict) else {}
        seed = manifest.get("seed", "—")
        outcome = "pass" if report.get("success") is True else "fail"
        condition_label = str(cohort_entry.get("label", f"Episode {index + 1:02d}"))
        duration = float(report.get("sim_time_s", 0.0) or 0.0)
        changed_parameters = cohort_entry.get("changed_parameters", {})
        if isinstance(changed_parameters, dict):
            change_text = " · ".join(f"{key}={_format_value(value)}" for key, value in changed_parameters.items())
        else:
            change_text = ""
        diagnosis = str(analysis.get("failure_class", report.get("stop_reason", "unclassified"))).replace("_", " ")
        motion = analysis.get("motion", {}) if isinstance(analysis.get("motion"), dict) else {}
        telemetry = analysis.get("physics_contact_telemetry", {}) if isinstance(analysis.get("physics_contact_telemetry"), dict) else {}
        contact = telemetry.get("contact", {}) if isinstance(telemetry.get("contact"), dict) else {}
        displacement = float(motion.get("horizontal_displacement_m", 0.0) or 0.0) * 1000
        lift = float(motion.get("max_lift_m", 0.0) or 0.0) * 1000
        force = contact.get("peak_normal_force_n")
        force_text = "—" if force is None else f"{float(force):.1f} N"
        cohort_video = cohort_entry.get("video", {}) if isinstance(cohort_entry.get("video"), dict) else {}
        relative_video = str(cohort_video.get("path", f"{selected_sim}/episode-{index}/episode.mp4"))
        video_path = f"urdf-studio/{relative_video}"
        detail_text = f"{change_text} · {diagnosis}" if change_text else diagnosis
        episode_media.append({"index": index, "seed": seed, "label": condition_label, "duration": duration, "change": change_text, "outcome": outcome, "diagnosis": diagnosis, "detail": detail_text, "src": video_path})
        episode_nav.append(
            f'<button class="episode-option {"selected" if position == 0 else ""}" data-episode-position="{position}">'
            f'<span>{html.escape(condition_label)}</span><small>seed {html.escape(str(seed))} · {duration:.1f} s</small><b class="{outcome}">{outcome.upper()}</b></button>'
        )
        episode_rows.append('<div class="episode-row">'
            f'<div><b>{html.escape(condition_label)}</b><span>seed {html.escape(str(seed))} · {duration:.1f} s</span></div><div><b class="{outcome}">{outcome.upper()}</b><span>{html.escape(detail_text)}</span></div>'
            f'<div><b>{displacement:.1f} mm</b><span>horizontal displacement</span></div><div><b>{lift:.1f} mm</b><span>maximum lift</span></div>'
            f'<div><b>{html.escape(force_text)}</b><span>peak solver force</span></div><button data-artifact="episode_{index}">Evidence</button></div>')

    attempts = recovery.get("attempts", []) if isinstance(recovery.get("attempts"), list) else []
    effect = recovery.get("effect", {}) if isinstance(recovery.get("effect"), dict) else {}
    intervention = recovery.get("intervention", {}) if isinstance(recovery.get("intervention"), dict) else {}
    intervention_panel = ""
    if len(attempts) >= 2:
        force_effect = effect.get("peak_normal_force_n", {}) if isinstance(effect.get("peak_normal_force_n"), dict) else {}
        displacement_effect = effect.get("horizontal_displacement_m", {}) if isinstance(effect.get("horizontal_displacement_m"), dict) else {}
        intervention_panel = f'''<section class="panel intervention"><div class="section-head"><div><span class="eyebrow">PARAMETER EXPERIMENT</span><h2>Slower approach reduced impact, not failure</h2></div><button data-artifact="recovery">Evidence</button></div>
        <div class="change-grid"><div><span>CONTROLLED VARIABLE</span><b>{html.escape(str(intervention.get("parameter", "policy parameter")))}</b></div><div><span>BASELINE → INTERVENTION</span><b>{html.escape(_format_value(intervention.get("baseline_value")))} → {html.escape(_format_value(intervention.get("intervention_value")))} {html.escape(str(intervention.get("unit", "")))}</b></div><div><span>PEAK FORCE</span><b>{float(force_effect.get("baseline", 0) or 0):.1f} → {float(force_effect.get("intervention", 0) or 0):.1f} N</b></div><div><span>DISPLACEMENT</span><b>{float(displacement_effect.get("baseline", 0) or 0) * 1000:.1f} → {float(displacement_effect.get("intervention", 0) or 0) * 1000:.1f} mm</b></div></div>
        <p>Same seed, cube pose, simulator, checker, and geometry. Lift still failed, so the result narrows the cause without claiming recovery.</p></section>'''

    artifacts: dict[str, Any] = {"study": study, "study_manifest": study_manifest, "policy": policy, "simulators": simulator_debug, "recovery": recovery, "pilot_cohort": pilot_cohort, "preflight_gate": {"authorized": pilot_passes > 0, "checks": [{"name": label, "passed": passed, "detail": detail} for label, passed, detail in gate_checks]}}
    for episode in episodes:
        artifacts[f'episode_{episode["index"]}'] = episode
    artifacts_json = json.dumps(artifacts, separators=(",", ":")).replace("</", "<\\/")
    episode_media_json = json.dumps(episode_media, separators=(",", ":")).replace("</", "<\\/")
    initial_media = episode_media[0] if episode_media else {"index": 0, "seed": "—", "label": "No run", "duration": 0, "change": "", "outcome": "not run", "diagnosis": "No retained episode", "detail": "No retained episode", "src": ""}

    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#171717"><title>REVA — Study control room</title>
<style>
:root{{--bg:#171717;--surface:#1d1d1d;--raised:#232323;--line:#353535;--text:#ededed;--muted:#929292;--pink:#ff4fba;--warn:#d7b177;--ok:#a9d2c0}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 Inter,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}}button,code,.mono,.eyebrow{{font-family:"SFMono-Regular",Consolas,monospace}}button{{border:0;border-bottom:1px solid #555;background:none;color:#aaa;padding:3px 0;cursor:pointer}}button:hover{{color:#fff;border-color:var(--pink)}}
.shell{{width:min(1180px,calc(100% - 40px));margin:auto;padding:22px 0 50px}}header{{display:flex;justify-content:space-between;align-items:center;padding-bottom:18px;border-bottom:1px solid var(--line)}}.brand{{display:flex;align-items:center;gap:9px;font-weight:650}}.mark{{width:12px;height:12px;border-radius:3px;background:var(--pink)}}.brand em{{color:#777;font-style:normal;font-weight:400}}header>span{{color:#777;font-size:10px}}.identity{{display:flex;justify-content:space-between;gap:24px;align-items:end;padding:30px 0 22px}}.eyebrow{{display:block;color:#888;font-size:9px;letter-spacing:.09em}}h1{{margin:8px 0 4px;font-size:30px;line-height:1.15;letter-spacing:-.035em;font-weight:550}}h2{{margin:5px 0 0;font-size:19px;letter-spacing:-.02em;font-weight:550}}p{{color:var(--muted);margin:7px 0 0}}.identity-meta{{text-align:right;color:#888;font-size:10px;line-height:1.7}}
.scope{{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-bottom:16px}}.scope div{{padding:17px 18px;background:var(--surface);border-right:1px solid var(--line)}}.scope div:last-child{{border:0}}.scope span,.change-grid span{{display:block;color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace;letter-spacing:.06em}}.scope b{{display:block;margin-top:8px;font-size:23px;font-weight:520}}.scope small{{color:#777}}
.gate{{display:grid;grid-template-columns:1.05fr 1.45fr;border-color:#554934}}.gate-decision{{padding:24px;border-right:1px solid #554934;background:#211f1b}}.gate-decision h2{{font-size:25px}}.gate-decision p{{max-width:470px}}.gate-state{{display:inline-block;margin-top:18px;padding:7px 10px;border:1px solid #755f3d;border-radius:4px;color:var(--warn);font:600 10px/1 "SFMono-Regular",Consolas,monospace;letter-spacing:.06em}}.gate-actions{{display:flex;align-items:center;gap:18px;margin-top:18px}}.gate-actions button[disabled]{{padding:8px 10px;border:1px solid #393939;border-radius:4px;color:#666;cursor:not-allowed}}.gate-checks{{display:grid;grid-template-columns:1fr 1fr}}.gate-row{{display:flex;gap:12px;padding:15px 16px;border-right:1px solid var(--line);border-bottom:1px solid var(--line)}}.gate-row:nth-child(2n){{border-right:0}}.gate-row:nth-last-child(-n+2){{border-bottom:0}}.gate-icon{{min-width:34px;font:600 8px/1.5 "SFMono-Regular",Consolas,monospace}}.gate-icon.pass{{color:var(--ok)}}.gate-icon.fail{{color:var(--warn)}}.gate-row b,.gate-row small{{display:block}}.gate-row b{{font-size:11px;font-weight:520}}.gate-row small{{margin-top:3px;color:#777;font-size:9px}}
.panel{{border:1px solid var(--line);border-radius:8px;background:var(--surface);margin-bottom:16px;overflow:hidden}}.section-head{{display:flex;justify-content:space-between;gap:18px;align-items:start;padding:20px 22px;border-bottom:1px solid var(--line)}}.section-head p{{font-size:12px}}.setup-grid{{display:grid;grid-template-columns:1.1fr 1fr 1fr}}.setup-block{{padding:20px 22px;border-right:1px solid var(--line)}}.setup-block:last-child{{border:0}}.setup-block h3,.criteria h3{{margin:0 0 15px;font:600 10px/1.2 "SFMono-Regular",Consolas,monospace;letter-spacing:.06em;color:#bdbdbd}}dl{{display:grid;grid-template-columns:1fr auto;gap:9px 16px;margin:0}}dt{{color:#777;font-size:11px}}dd{{margin:0;text-align:right;color:#c9c9c9;font:10px/1.45 "SFMono-Regular",Consolas,monospace}}
.sim-head,.sim-row{{display:grid;grid-template-columns:1.2fr .65fr .65fr 1.3fr 1fr}}.sim-head{{background:var(--raised)}}.sim-head div{{padding:9px 14px;color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace}}.sim-row{{border-top:1px solid var(--line)}}.sim-row>div{{min-width:0;padding:13px 14px;border-right:1px solid var(--line);font-size:11px}}.sim-row>div:last-child{{border:0}}.sim-row b,.sim-row span{{display:block}}.sim-row b{{font-weight:520;color:#cfcfcf}}.sim-row span{{margin-top:3px;color:#777;font-size:9px}}.status{{display:inline-block;width:6px;height:6px;border-radius:50%;background:#666;margin-right:7px}}.status.active{{background:var(--pink)}}
.criteria-grid{{display:grid;grid-template-columns:repeat(3,1fr)}}.criteria{{padding:20px 22px;border-right:1px solid var(--line)}}.criteria:last-child{{border:0}}ul{{list-style:none;padding:0;margin:0}}li{{padding:8px 0;border-top:1px solid #2c2c2c;color:#999;font-size:11px}}li:first-child{{border:0}}li span,li b{{display:block}}li b{{margin-top:3px;color:#c4c4c4;font:500 10px/1.45 "SFMono-Regular",Consolas,monospace}}
.pilot-summary{{display:flex;gap:20px;align-items:center}}.pilot-summary b{{font-size:22px;font-weight:520}}.pilot-summary span{{color:#777;font-size:10px}}.episode-browser{{display:grid;grid-template-columns:minmax(0,1fr) 240px;background:#111;border-bottom:1px solid var(--line)}}.player{{min-width:0;border-right:1px solid var(--line)}}video{{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#090909}}.player-meta{{display:flex;justify-content:space-between;gap:16px;padding:11px 14px;border-top:1px solid #292929}}.player-meta span,.player-meta small{{display:block;color:#777;font:9px/1.5 "SFMono-Regular",Consolas,monospace}}.player-meta b{{font:500 10px/1.4 "SFMono-Regular",Consolas,monospace}}.episode-queue{{max-height:430px;overflow:auto;background:var(--surface)}}.queue-head{{position:sticky;top:0;z-index:1;padding:11px 13px;background:var(--raised);color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace;border-bottom:1px solid var(--line)}}.episode-option{{display:grid;grid-template-columns:1fr auto;gap:3px 10px;width:100%;padding:12px 13px;border:0;border-bottom:1px solid var(--line);text-align:left}}.episode-option:hover,.episode-option.selected{{background:#292929}}.episode-option.selected{{box-shadow:inset 2px 0 var(--pink)}}.episode-option span,.episode-option small{{display:block}}.episode-option span{{color:#ccc;font:500 10px/1.3 "SFMono-Regular",Consolas,monospace}}.episode-option small{{color:#777;font-size:9px}}.episode-option b{{grid-row:1/3;grid-column:2;align-self:center;font:500 9px/1 "SFMono-Regular",Consolas,monospace}}.pass{{color:var(--ok)!important}}.fail{{color:var(--warn)!important}}
.episode-table-head,.episode-row{{display:grid;grid-template-columns:.65fr 1.4fr 1fr .8fr .9fr .5fr;align-items:center}}.episode-table-head{{background:var(--raised)}}.episode-table-head div{{padding:9px 12px;color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace}}.episode-row{{border-top:1px solid var(--line)}}.episode-row>div,.episode-row>button{{margin:0;padding:11px 12px;border-right:1px solid var(--line)}}.episode-row b,.episode-row span{{display:block}}.episode-row b{{font:500 10px/1.4 "SFMono-Regular",Consolas,monospace;color:#c5c5c5}}.episode-row span{{color:#777;font-size:9px;margin-top:2px}}.episode-row button{{border-bottom:0;text-align:left}}.change-grid{{display:grid;grid-template-columns:repeat(4,1fr)}}.change-grid>div{{padding:16px 20px;border-right:1px solid var(--line)}}.change-grid>div:last-child{{border:0}}.change-grid b{{display:block;margin-top:8px;color:#ccc;font:500 11px/1.4 "SFMono-Regular",Consolas,monospace}}.intervention>p{{padding:0 20px 16px;font-size:11px}}
.manifest-table{{max-height:420px;overflow:auto}}.manifest-head,.manifest-row{{display:grid;grid-template-columns:1fr .75fr 1.1fr 1.2fr 1fr}}.manifest-head{{position:sticky;top:0;z-index:1;background:var(--raised)}}.manifest-head div{{padding:9px 13px;color:#777;font:9px/1.2 "SFMono-Regular",Consolas,monospace}}.manifest-row{{border-top:1px solid var(--line)}}.manifest-row>div{{min-width:0;padding:10px 13px;border-right:1px solid var(--line);color:#aaa;font:9px/1.4 "SFMono-Regular",Consolas,monospace}}.manifest-row>div:last-child{{border:0}}.manifest-row b,.manifest-row span{{display:block}}.manifest-row b{{color:#ccc;font-weight:520}}.manifest-row span{{color:#686868;margin-top:2px}}.manifest-foot{{display:flex;justify-content:space-between;gap:16px;padding:12px 16px;border-top:1px solid var(--line);color:#777;font:9px/1.4 "SFMono-Regular",Consolas,monospace}}
.readiness{{display:grid;grid-template-columns:1fr 1fr 1fr}}.readiness>div{{padding:18px 20px;border-right:1px solid var(--line)}}.readiness>div:last-child{{border:0}}.readiness b{{display:block;font-weight:520}}.readiness span{{display:block;color:#777;font-size:11px;margin-top:4px}}dialog{{width:min(840px,calc(100% - 32px));max-height:82vh;padding:0;background:var(--surface);color:var(--text);border:1px solid #444;border-radius:8px}}dialog::backdrop{{background:#000b}}.dialog-head{{display:flex;justify-content:space-between;padding:15px 18px;border-bottom:1px solid var(--line)}}pre{{padding:18px;margin:0;overflow:auto;font:10px/1.65 "SFMono-Regular",Consolas,monospace;color:#bbb;white-space:pre-wrap}}footer{{display:flex;justify-content:space-between;padding-top:16px;color:#666;font-size:10px;border-top:1px solid var(--line)}}
@media(max-width:850px){{.scope,.change-grid{{grid-template-columns:1fr 1fr}}.gate{{grid-template-columns:1fr}}.gate-decision{{border-right:0;border-bottom:1px solid #554934}}.setup-grid,.criteria-grid,.readiness{{grid-template-columns:1fr}}.setup-block,.criteria,.readiness>div{{border-right:0;border-bottom:1px solid var(--line)}}.sim-head,.sim-row{{grid-template-columns:1fr 1fr}}.sim-head div:nth-child(n+3),.sim-row>div:nth-child(n+3){{display:none}}.episode-table-head{{display:none}}.episode-row{{grid-template-columns:1fr 1fr}}.episode-row>div:nth-child(n+3){{display:none}}.manifest-head,.manifest-row{{grid-template-columns:1fr .8fr 1fr}}.manifest-head div:nth-child(4),.manifest-head div:nth-child(5),.manifest-row>div:nth-child(4),.manifest-row>div:nth-child(5){{display:none}}}}@media(max-width:620px){{.episode-browser{{grid-template-columns:1fr}}.player{{border-right:0;border-bottom:1px solid var(--line)}}.episode-queue{{display:grid;grid-template-columns:repeat(2,1fr);max-height:210px}}.queue-head{{grid-column:1/-1}}.gate-checks{{grid-template-columns:1fr}}.gate-row,.gate-row:nth-child(2n),.gate-row:nth-last-child(-n+2){{border-right:0;border-bottom:1px solid var(--line)}}}}@media(max-width:520px){{.shell{{width:calc(100% - 24px)}}header>span,.brand em{{display:none}}.identity{{align-items:start;flex-direction:column}}.identity-meta{{text-align:left}}.scope,.change-grid{{grid-template-columns:1fr}}footer{{flex-direction:column}}}}
</style></head><body><script>if(window.top===window.self&&location.pathname.endsWith('/scientific-report.html'))location.replace('./');</script><div class="shell"><header><div class="brand"><span class="mark"></span>REVA <em>/ Batch authorization</em></div><span class="mono">MUJOCO INDUSTRIAL PREFLIGHT</span></header><main>
<section class="identity"><div><span class="eyebrow">EVALUATION STUDY</span><h1>{study_title}</h1><p>Preflight evidence controls authorization of the 100-episode MuJoCo batch.</p></div><div class="identity-meta mono">{study_id}<br>POLICY {html.escape(policy_digest[:12])}</div></section>
<section class="scope" aria-label="Study scale"><div><span>TARGET BATCH</span><b>{per_sim}</b><small>frozen episode identities</small></div><div><span>PREFLIGHT EXECUTED</span><b>{len(episodes)}</b><small>controlled conditions</small></div><div><span>BATCH WITHHELD</span><b>{withheld_count}</b><small>not scheduled</small></div><div><span>VERIFIED BACKEND</span><b>1</b><small>MuJoCo</small></div></section>
<section class="panel gate" aria-label="Preflight authorization gate"><div class="gate-decision"><span class="eyebrow">BATCH AUTHORIZATION</span><h2>Production batch blocked</h2><p>The preflight found no successful lift and two distinct failure mechanisms. REVA withheld the remaining {withheld_count} executions before compute was committed.</p><span class="gate-state">BLOCKED · TASK SUCCESS REQUIRED</span><div class="gate-actions"><button data-artifact="preflight_gate">Inspect gate evidence</button><button disabled title="A successful production-candidate preflight is required">Approve 100 episodes</button></div></div><div class="gate-checks">{gate_rows_html}</div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">EXPERIMENT SETUP</span><h2>Frozen before execution</h2><p>Seed identities, object poses, acceptance criteria, policy, and runtime are bound before scheduling.</p></div><button data-artifact="study">Study definition</button></div><div class="setup-grid"><div class="setup-block"><h3>SEEDING & PAIRING</h3><dl><dt>Episode identities</dt><dd>{html.escape(str(pairing.get("seed_count", per_sim)))}</dd><dt>Seed derivation</dt><dd>{html.escape(str(pairing.get("seed_derivation", "—")))}</dd><dt>Manifest state</dt><dd>frozen</dd><dt>Retry behavior</dt><dd>{"preserve identity" if pairing.get("retry_preserves_manifest") else "new identity"}</dd><dt>Preflight seeds</dt><dd>{html.escape(seed_text)}</dd></dl></div><div class="setup-block"><h3>RANDOMIZATION</h3><dl><dt>Cube position jitter</dt><dd>{html.escape(jitter_text)}</dd><dt>Cube yaw jitter</dt><dd>±{yaw:g} rad</dd><dt>Robot initial state</dt><dd>{html.escape(str(randomization.get("robot_initial_state", "—")))}</dd><dt>Policy</dt><dd>{html.escape(str(randomization.get("policy", "—")))}</dd></dl></div><div class="setup-block"><h3>MUJOCO RUNTIME</h3><dl><dt>Physics step</dt><dd>{html.escape(_format_value(runtime.get("physics_timestep_s")))} s</dd><dt>Control rate</dt><dd>{html.escape(_format_value(runtime.get("control_hz")))} Hz</dd><dt>Checker interval</dt><dd>{html.escape(_format_value(runtime.get("checker_interval_steps")))} steps</dd><dt>Episode horizon</dt><dd>{html.escape(_format_value(runtime.get("max_episode_steps")))} steps</dd><dt>Grasp attach</dt><dd>{html.escape(str(runtime.get("grasp_attach", "—")))}</dd></dl></div></div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">100-EPISODE EXECUTION MANIFEST</span><h2>Every batch slot is accounted for</h2><p>Four preflight identities executed; {withheld_count} remain withheld pending authorization.</p></div><button data-artifact="study_manifest">Inspect frozen manifest</button></div><div class="manifest-table"><div class="manifest-head"><div>EPISODE</div><div>SEED</div><div>POLICY CONDITION</div><div>CUBE XYZ · M</div><div>STATUS</div></div>{''.join(manifest_rows_html)}</div><div class="manifest-foot"><span>MANIFEST {html.escape(str(study_manifest.get("manifest_sha256", "not generated"))[:16])}</span><span>{len(manifest_rows_html)} identities · {len(episodes)} executed · {withheld_count} withheld</span></div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">ACCEPTANCE CONTRACT</span><h2>Task, governance, and native solver evidence</h2></div></div><div class="criteria-grid"><div class="criteria"><h3>TASK-SPECIFIC</h3><ul>{''.join(task_criteria)}</ul></div><div class="criteria"><h3>STUDY GOVERNANCE</h3><ul>{shared_criteria}</ul></div><div class="criteria"><h3>MUJOCO EVIDENCE</h3><ul>{''.join(specific_rows)}</ul></div></div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">PARAMETER PILOT · MUJOCO</span><h2>{len(episodes)} controlled conditions · {pilot_failures} failures</h2><p>Policy and runtime probes validate sensitivity and instrumentation. No population-level rate is reported.</p></div><div class="pilot-summary"><div><b>{pilot_passes}</b><span>passes</span></div><div><b>{pilot_failures}</b><span>failures</span></div></div></div><div class="episode-browser"><div class="player"><video id="pilot-video" controls autoplay muted loop playsinline preload="metadata" aria-label="Selected pilot condition"><source id="pilot-video-source" src="{html.escape(str(initial_media['src']))}" type="video/mp4"></video><div class="player-meta"><div><span id="pilot-identity">{html.escape(str(initial_media['label']))} · SEED {html.escape(str(initial_media['seed']))} · {float(initial_media['duration']):.1f} s</span><small id="pilot-diagnosis">{html.escape(str(initial_media['detail']))}</small></div><b id="pilot-outcome" class="{html.escape(str(initial_media['outcome']))}">{html.escape(str(initial_media['outcome']).upper())}</b></div></div><aside class="episode-queue"><div class="queue-head">CONTROLLED CONDITIONS · SELECT TO INSPECT</div>{''.join(episode_nav)}</aside></div><div class="episode-table-head"><div>CONDITION</div><div>CONTROL / OUTCOME</div><div>DISPLACEMENT</div><div>LIFT</div><div>CONTACT</div><div></div></div>{''.join(episode_rows)}</section>{intervention_panel}
</main><footer><span>REVA · governed robot evaluation</span><span>Preflight evidence gates batch execution.</span></footer></div><dialog id="artifact-dialog"><div class="dialog-head"><strong id="artifact-title">Evidence</strong><button id="close-dialog">Close</button></div><pre id="artifact-content"></pre></dialog>
<script>const artifacts={artifacts_json};const episodeMedia={episode_media_json};const video=document.getElementById('pilot-video');const source=document.getElementById('pilot-video-source');document.querySelectorAll('[data-episode-position]').forEach(button=>button.addEventListener('click',()=>{{const item=episodeMedia[Number(button.dataset.episodePosition)];if(!item)return;document.querySelectorAll('[data-episode-position]').forEach(option=>option.classList.toggle('selected',option===button));source.src=item.src;video.load();video.play().catch(()=>{{}});document.getElementById('pilot-identity').textContent=`${{item.label}} · SEED ${{item.seed}} · ${{item.duration.toFixed(1)}} s`;document.getElementById('pilot-diagnosis').textContent=item.detail;const outcome=document.getElementById('pilot-outcome');outcome.textContent=item.outcome.toUpperCase();outcome.className=item.outcome;}}));const dialog=document.getElementById('artifact-dialog');document.querySelectorAll('[data-artifact]').forEach(button=>button.addEventListener('click',()=>{{const key=button.dataset.artifact;document.getElementById('artifact-title').textContent=key.replaceAll('_',' ').toUpperCase();document.getElementById('artifact-content').textContent=JSON.stringify(artifacts[key],null,2);dialog.showModal()}}));document.getElementById('close-dialog').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',event=>{{if(event.target===dialog)dialog.close()}});</script></body></html>'''
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = output_path.with_name("scientific-report.html")
    report_path.write_text(document, encoding="utf-8")
    workbench = _build_workbench_document(
        study=study,
        study_manifest=study_manifest,
        episodes=episodes,
        recovery=recovery,
        policy_digest=policy_digest,
        selected_sim=selected_sim,
    )
    output_path.write_text(workbench, encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = build_demo_dashboard(args.input, args.output)
    print(f"dashboard={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
