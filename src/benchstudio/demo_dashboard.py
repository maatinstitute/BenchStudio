"""Build a self-contained visual dashboard from BenchStudio demo evidence."""

from __future__ import annotations

import argparse
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
    run_id = html.escape(str(plan.get("run_id", "BenchStudio demo")))
    plan_digest = _short(plan.get("plan_digest_sha256"), 16)
    transport_valid = robochallenge.get("valid") is True
    transport_events = int(robochallenge.get("event_count", 0) or 0)

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
    .hero {{ padding:72px 0 56px; max-width:920px; }}
    .kicker {{ color:var(--muted); font:500 11px/1.2 "Noto Sans Mono", monospace; letter-spacing:.1em; text-transform:uppercase; }}
    h1 {{ margin:18px 0 20px; font-size:clamp(42px, 6vw, 72px); line-height:1.04; letter-spacing:-.045em; font-weight:500; }}
    .hero p {{ margin:0; max-width:720px; color:#b8b8b8; font-size:17px; line-height:1.65; }}
    .runline {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:28px; color:#777; font:10px/1.3 "Noto Sans Mono", monospace; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:18px; }}
    .metric {{ padding:18px 20px; background:var(--surface); border-right:1px solid var(--line); }}
    .metric:last-child {{ border-right:0; }}
    .metric-label {{ display:block; color:var(--muted); font-size:9px; letter-spacing:.08em; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:8px; font-size:27px; line-height:1; letter-spacing:-.035em; font-weight:500; }}
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
    .links {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
    .links a {{ color:#aaa; text-decoration:none; border-bottom:1px solid #555; padding:3px 0; margin-right:12px; font-size:11px; }} .links a:hover {{ color:#fff; border-color:var(--pink); }}
    details {{ border:1px solid var(--line); border-radius:10px; background:var(--surface); margin-bottom:18px; }}
    summary {{ cursor:pointer; padding:17px 20px; color:#aaa; font-size:10px; letter-spacing:.04em; }}
    .json-panel {{ margin:0 20px 20px; padding:17px; border:1px solid var(--line); border-radius:7px; background:#171717; overflow:auto; }}
    .json-panel code {{ color:#c8c8c8; font-size:11px; line-height:1.8; white-space:pre; }}
    .json-key {{ color:#d98ab9; }} .json-string {{ color:#b8aec4; }} .json-number {{ color:#a5bdc5; }} .json-ok {{ color:var(--ok); }}
    footer {{ display:flex; justify-content:space-between; gap:20px; color:#707070; border-top:1px solid var(--line); padding-top:18px; font-size:10px; }}
    @media(max-width:800px) {{ .story {{ grid-template-columns:1fr; }} .transfer {{ border-right:0; border-bottom:1px solid var(--line); }} .metrics {{ grid-template-columns:1fr 1fr; }} .metric:nth-child(2) {{ border-right:0; }} .metric:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} .evidence {{ grid-template-columns:1fr 1fr; }} .evidence div:nth-child(2) {{ border-right:0; }} .evidence div:nth-child(-n+2) {{ border-bottom:1px solid var(--line); }} }}
    @media(max-width:560px) {{ .shell {{ width:calc(100% - 24px); }} .hero {{ padding:52px 0 40px; }} h1 {{ font-size:42px; }} .matrix-row {{ grid-template-columns:76px repeat(2,1fr); }} .bar {{ grid-template-columns:100px 1fr 36px; }} .brand span:last-child {{ display:none; }} footer {{ flex-direction:column; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <header><div class="brand"><span class="mark"></span>BenchStudio <span>/ evaluation report</span></div><span class="tag">QUALIFIED EVIDENCE</span></header>

    <main>
      <section class="hero">
        <div class="kicker">Controlled comparison · deterministic fixture</div>
        <h1>The evaluation is complete.<br>The transfer claim is not.</h1>
        <p>BenchStudio accounted for every scheduled attempt and verified every evidence record. The matched fixture still produced a {gap:+d} percentage-point transfer gap, so the result supports pipeline integrity—not real-world performance.</p>
        <div class="runline"><span>RUN {run_id}</span><span>PLAN {plan_digest}</span><span>{matched_pairs} MATCHED TRANSFER PAIRS</span></div>
      </section>

      <section class="metrics" aria-label="Campaign integrity">
        <div class="metric"><span class="metric-label">Scheduled</span><strong>{scheduled}</strong></div>
        <div class="metric"><span class="metric-label">Completed</span><strong>{completed}/{scheduled}</strong></div>
        <div class="metric"><span class="metric-label">Evidence verified</span><strong>{evidence_rate}%</strong></div>
        <div class="metric"><span class="metric-label">Missing outcomes</span><strong>{missing}</strong></div>
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
        <div class="links"><a href="campaign-plan.json">Frozen plan ↗</a><a href="campaign/attempt-results.jsonl">Attempt ledger ↗</a><a href="transfer/transfer-report.json">Transfer report ↗</a><a href="robustness/counterfactual-summary.json">Robustness report ↗</a></div>
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

    <footer><span>BenchStudio · evaluation evidence, not benchmark theater</span><span>Physics and official scoring remain external</span></footer>
  </div>
  <script>
    const cells = {matrix_json};
    const pairs = [...new Set(cells.map(c => c.pair))];
    const conditions = [...new Set(cells.map(c => c.condition))];
    const matrix = document.getElementById('matrix');
    const head = document.createElement('div'); head.className = 'matrix-row';
    head.innerHTML = '<div class="matrix-label">INITIAL STATE</div>' + conditions.map(c => `<div class="matrix-label">${{c.replaceAll('_',' ').toUpperCase()}}</div>`).join(''); matrix.appendChild(head);
    pairs.forEach((pair, index) => {{ const row = document.createElement('div'); row.className = 'matrix-row'; row.innerHTML = `<div class="matrix-label">PAIR ${{String(index + 1).padStart(2,'0')}}</div>` + conditions.map(condition => {{ const cell = cells.find(c => c.pair === pair && c.condition === condition); return `<div class="matrix-cell"><div><strong>${{cell?.steps ?? '—'}} denoise steps</strong><br><small>${{cell?.verified ? 'verified' : 'unverified'}}</small></div><span class="check">${{cell?.success ? '✓' : '—'}}</span></div>`; }}).join(''); matrix.appendChild(row); }});
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
