"""Build a self-contained BenchStudio study control room."""

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
        "schema": "benchstudio.study_definition.v1",
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
    planned = per_sim * len(simulators)
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
        and isinstance(analysis["physics_contact_telemetry"].get("equivalence"), dict)
        and analysis["physics_contact_telemetry"]["equivalence"].get("verified") is True
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

    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#171717"><title>BenchStudio — Study control room</title>
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
</style></head><body><div class="shell"><header><div class="brand"><span class="mark"></span>BenchStudio <em>/ Batch authorization</em></div><span class="mono">MUJOCO INDUSTRIAL PREFLIGHT</span></header><main>
<section class="identity"><div><span class="eyebrow">EVALUATION STUDY</span><h1>{study_title}</h1><p>Preflight evidence controls authorization of the 100-episode MuJoCo batch.</p></div><div class="identity-meta mono">{study_id}<br>POLICY {html.escape(policy_digest[:12])}</div></section>
<section class="scope" aria-label="Study scale"><div><span>TARGET BATCH</span><b>{per_sim}</b><small>frozen episode identities</small></div><div><span>PREFLIGHT EXECUTED</span><b>{len(episodes)}</b><small>controlled conditions</small></div><div><span>BATCH WITHHELD</span><b>{withheld_count}</b><small>not scheduled</small></div><div><span>VERIFIED BACKEND</span><b>1</b><small>MuJoCo</small></div></section>
<section class="panel gate" aria-label="Preflight authorization gate"><div class="gate-decision"><span class="eyebrow">BATCH AUTHORIZATION</span><h2>Production batch blocked</h2><p>The preflight found no successful lift and two distinct failure mechanisms. BenchStudio withheld the remaining {withheld_count} executions before compute was committed.</p><span class="gate-state">BLOCKED · TASK SUCCESS REQUIRED</span><div class="gate-actions"><button data-artifact="preflight_gate">Inspect gate evidence</button><button disabled title="A successful production-candidate preflight is required">Approve 100 episodes</button></div></div><div class="gate-checks">{gate_rows_html}</div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">EXPERIMENT SETUP</span><h2>Frozen before execution</h2><p>Seed identities, object poses, acceptance criteria, policy, and runtime are bound before scheduling.</p></div><button data-artifact="study">Study definition</button></div><div class="setup-grid"><div class="setup-block"><h3>SEEDING & PAIRING</h3><dl><dt>Episode identities</dt><dd>{html.escape(str(pairing.get("seed_count", per_sim)))}</dd><dt>Seed derivation</dt><dd>{html.escape(str(pairing.get("seed_derivation", "—")))}</dd><dt>Manifest state</dt><dd>frozen</dd><dt>Retry behavior</dt><dd>{"preserve identity" if pairing.get("retry_preserves_manifest") else "new identity"}</dd><dt>Preflight seeds</dt><dd>{html.escape(seed_text)}</dd></dl></div><div class="setup-block"><h3>RANDOMIZATION</h3><dl><dt>Cube position jitter</dt><dd>{html.escape(jitter_text)}</dd><dt>Cube yaw jitter</dt><dd>±{yaw:g} rad</dd><dt>Robot initial state</dt><dd>{html.escape(str(randomization.get("robot_initial_state", "—")))}</dd><dt>Policy</dt><dd>{html.escape(str(randomization.get("policy", "—")))}</dd></dl></div><div class="setup-block"><h3>MUJOCO RUNTIME</h3><dl><dt>Physics step</dt><dd>{html.escape(_format_value(runtime.get("physics_timestep_s")))} s</dd><dt>Control rate</dt><dd>{html.escape(_format_value(runtime.get("control_hz")))} Hz</dd><dt>Checker interval</dt><dd>{html.escape(_format_value(runtime.get("checker_interval_steps")))} steps</dd><dt>Episode horizon</dt><dd>{html.escape(_format_value(runtime.get("max_episode_steps")))} steps</dd><dt>Grasp attach</dt><dd>{html.escape(str(runtime.get("grasp_attach", "—")))}</dd></dl></div></div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">100-EPISODE EXECUTION MANIFEST</span><h2>Every batch slot is accounted for</h2><p>Four preflight identities executed; {withheld_count} remain withheld pending authorization.</p></div><button data-artifact="study_manifest">Inspect frozen manifest</button></div><div class="manifest-table"><div class="manifest-head"><div>EPISODE</div><div>SEED</div><div>POLICY CONDITION</div><div>CUBE XYZ · M</div><div>STATUS</div></div>{''.join(manifest_rows_html)}</div><div class="manifest-foot"><span>MANIFEST {html.escape(str(study_manifest.get("manifest_sha256", "not generated"))[:16])}</span><span>{len(manifest_rows_html)} identities · {len(episodes)} executed · {withheld_count} withheld</span></div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">ACCEPTANCE CONTRACT</span><h2>Task, governance, and native solver evidence</h2></div></div><div class="criteria-grid"><div class="criteria"><h3>TASK-SPECIFIC</h3><ul>{''.join(task_criteria)}</ul></div><div class="criteria"><h3>STUDY GOVERNANCE</h3><ul>{shared_criteria}</ul></div><div class="criteria"><h3>MUJOCO EVIDENCE</h3><ul>{''.join(specific_rows)}</ul></div></div></section>
<section class="panel"><div class="section-head"><div><span class="eyebrow">PARAMETER PILOT · MUJOCO</span><h2>{len(episodes)} controlled conditions · {pilot_failures} failures</h2><p>Policy and runtime probes validate sensitivity and instrumentation. No population-level rate is reported.</p></div><div class="pilot-summary"><div><b>{pilot_passes}</b><span>passes</span></div><div><b>{pilot_failures}</b><span>failures</span></div></div></div><div class="episode-browser"><div class="player"><video id="pilot-video" controls autoplay muted loop playsinline preload="metadata" aria-label="Selected pilot condition"><source id="pilot-video-source" src="{html.escape(str(initial_media['src']))}" type="video/mp4"></video><div class="player-meta"><div><span id="pilot-identity">{html.escape(str(initial_media['label']))} · SEED {html.escape(str(initial_media['seed']))} · {float(initial_media['duration']):.1f} s</span><small id="pilot-diagnosis">{html.escape(str(initial_media['detail']))}</small></div><b id="pilot-outcome" class="{html.escape(str(initial_media['outcome']))}">{html.escape(str(initial_media['outcome']).upper())}</b></div></div><aside class="episode-queue"><div class="queue-head">CONTROLLED CONDITIONS · SELECT TO INSPECT</div>{''.join(episode_nav)}</aside></div><div class="episode-table-head"><div>CONDITION</div><div>CONTROL / OUTCOME</div><div>DISPLACEMENT</div><div>LIFT</div><div>CONTACT</div><div></div></div>{''.join(episode_rows)}</section>{intervention_panel}
</main><footer><span>BenchStudio · governed robot evaluation</span><span>Preflight evidence gates batch execution.</span></footer></div><dialog id="artifact-dialog"><div class="dialog-head"><strong id="artifact-title">Evidence</strong><button id="close-dialog">Close</button></div><pre id="artifact-content"></pre></dialog>
<script>const artifacts={artifacts_json};const episodeMedia={episode_media_json};const video=document.getElementById('pilot-video');const source=document.getElementById('pilot-video-source');document.querySelectorAll('[data-episode-position]').forEach(button=>button.addEventListener('click',()=>{{const item=episodeMedia[Number(button.dataset.episodePosition)];if(!item)return;document.querySelectorAll('[data-episode-position]').forEach(option=>option.classList.toggle('selected',option===button));source.src=item.src;video.load();video.play().catch(()=>{{}});document.getElementById('pilot-identity').textContent=`${{item.label}} · SEED ${{item.seed}} · ${{item.duration.toFixed(1)}} s`;document.getElementById('pilot-diagnosis').textContent=item.detail;const outcome=document.getElementById('pilot-outcome');outcome.textContent=item.outcome.toUpperCase();outcome.className=item.outcome;}}));const dialog=document.getElementById('artifact-dialog');document.querySelectorAll('[data-artifact]').forEach(button=>button.addEventListener('click',()=>{{const key=button.dataset.artifact;document.getElementById('artifact-title').textContent=key.replaceAll('_',' ').toUpperCase();document.getElementById('artifact-content').textContent=JSON.stringify(artifacts[key],null,2);dialog.showModal()}}));document.getElementById('close-dialog').addEventListener('click',()=>dialog.close());dialog.addEventListener('click',event=>{{if(event.target===dialog)dialog.close()}});</script></body></html>'''
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
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
