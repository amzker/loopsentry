"""Standalone HTML report generator for LoopSentry."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import orjson

Block = dict[str, Any]


def _parse_location(trigger_str: str) -> str:
    if not trigger_str:
        return "Unknown"
    match = re.search(r'File "(.*?)", line (\d+)', trigger_str)
    if match:
        return f"{Path(match.group(1)).name}:{match.group(2)}"
    async_match = re.search(r"^(.*?) \(Task-", trigger_str)
    if async_match:
        return async_match.group(1)
    return trigger_str[:40]


def generate_html(blocks: list[Block], stats: dict[str, Any]) -> str:
    safe_blocks: list[Block] = []
    for i, block in enumerate(blocks):
        trig = block.get("trigger", "")
        inner_loc = _parse_location(trig)
        user_loc = (block.get("user_location") or "").strip()
        if not user_loc or user_loc == "Unknown":
            user_loc = inner_loc
        blk_loc = (block.get("blocking_location") or "").strip() or inner_loc
        safe_blocks.append(
            {
                "id": i + 1,
                "type": block.get("type", "unknown"),
                "timestamp": block.get("timestamp", ""),
                "pid": block.get("pid", 0),
                "total_duration": block.get("total_duration", 0),
                "hint": block.get("hint", ""),
                "trigger": trig,
                "location": user_loc,
                "blocking_location": blk_loc,
                "user_frames": block.get("user_frames") or [],
                "resolved": block.get("resolved", True),
                "task_name": block.get("task_name", ""),
                "coro": block.get("coro", ""),
                "sys": block.get("sys", {}),
                "stack": block.get("stack", []),
                "locals": block.get("locals", []),
                "exception": block.get("exception"),
            }
        )

    blocks_json = orjson.dumps(safe_blocks).decode()
    stats_json = orjson.dumps(stats).decode()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LoopSentry Report</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0b0e17;--surface:#131829;--surface2:#1a2035;--surface3:#202946;--border:#252d48;
  --text:#e2e8f0;--text-dim:#64748b;--accent:#6366f1;--accent2:#818cf8;
  --red:#ef4444;--orange:#f97316;--yellow:#eab308;--green:#22c55e;--cyan:#06b6d4;--pink:#ec4899;
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',sans-serif;
  --mono:'SF Mono','Fira Code',Consolas,monospace;
}}
body{{font-family:var(--font);background:var(--bg);color:var(--text);line-height:1.6;padding:0}}
.wrap{{width:100%;padding:24px 32px 64px}}
.header{{display:flex;align-items:center;justify-content:space-between;padding:24px 0;border-bottom:1px solid var(--border);margin-bottom:32px}}
.title h1{{font-size:28px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.title p{{color:var(--text-dim);font-size:13px;margin-top:2px}}
.badge{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;background:var(--accent);color:#fff}}

.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;text-align:center;transition:transform .15s,box-shadow .15s}}
.card:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3)}}
.card .val{{font-size:32px;font-weight:800;margin-bottom:4px}}
.card .lbl{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text-dim)}}
.card .hint{{font-size:10px;color:var(--text-dim);margin-top:6px;line-height:1.4;opacity:.7}}
.card.red .val{{color:var(--red)}}.card.yellow .val{{color:var(--yellow)}}
.card.cyan .val{{color:var(--cyan)}}.card.pink .val{{color:var(--pink)}}
.card.green .val{{color:var(--green)}}.card.orange .val{{color:var(--orange)}}

.charts{{display:grid;grid-template-columns:1.35fr 1fr;gap:16px;margin-bottom:24px}}
.chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px;overflow:hidden}}
.chart-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}}
.chart-head h3{{font-size:16px;font-weight:800}}
.chart-head p{{font-size:12px;color:var(--text-dim)}}
.chart-actions{{display:flex;gap:8px;flex-wrap:wrap}}
.mini-btn{{padding:7px 11px;border-radius:999px;border:1px solid var(--border);background:var(--surface2);color:var(--text);font-size:12px;cursor:pointer;font-weight:600;transition:all .15s}}
.mini-btn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
.legend{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px;color:var(--text-dim);font-size:12px}}
.legend span{{display:inline-flex;align-items:center;gap:6px}}
.legend i{{display:inline-block;width:12px;height:12px;border-radius:999px}}
.chart-shell{{position:relative;border:1px solid var(--border);background:var(--bg);border-radius:10px;padding:12px}}
.chart-shell svg{{width:100%;height:300px;display:block}}
.chart-meta{{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:var(--text-dim)}}
.chart-tip{{position:absolute;pointer-events:none;transform:translate(-50%,-100%);background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:8px 10px;font-size:12px;color:var(--text);box-shadow:0 12px 30px rgba(0,0,0,.28);opacity:0;transition:opacity .12s}}
.chart-tip.show{{opacity:1}}
.chart-tip strong{{display:block;margin-bottom:2px}}

.controls{{display:flex;gap:12px;margin-bottom:18px;flex-wrap:wrap;align-items:center}}
.search{{flex:1;min-width:220px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 16px;color:var(--text);font-size:14px;outline:none;transition:border .2s}}
.search:focus{{border-color:var(--accent)}}
.btn{{padding:8px 16px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:13px;cursor:pointer;transition:all .15s;font-weight:600}}
.btn:hover{{background:var(--surface2);border-color:var(--accent)}}
.btn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
select.btn{{appearance:none;padding-right:28px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2364748b' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center}}
.filter-pop{{position:relative}}
.filter-toggle{{display:flex;align-items:center;gap:8px}}
.filter-panel{{position:absolute;top:calc(100% + 8px);right:0;min-width:320px;max-height:320px;overflow:auto;padding:10px;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:0 14px 34px rgba(0,0,0,.32);display:none;z-index:30}}
.filter-panel.open{{display:block}}
.filter-row-actions{{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}}
.filter-panel-title{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--text-dim)}}
.filter-link{{background:none;border:none;color:var(--accent2);cursor:pointer;font-size:12px;padding:0}}
.filter-options{{display:grid;gap:6px}}
.filter-option{{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;background:var(--surface2);font-size:12px}}
.filter-option input{{accent-color:var(--accent)}}

.export-panel{{position:absolute;top:calc(100% + 8px);right:0;min-width:150px;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:0 14px 34px rgba(0,0,0,.32);display:none;z-index:30;padding:6px}}
.export-panel.open{{display:block}}
.export-btn{{display:block;width:100%;text-align:left;padding:8px 12px;background:transparent;border:none;color:var(--text);font-size:13px;cursor:pointer;border-radius:6px;transition:background .15s;font-weight:500}}
.export-btn:hover{{background:var(--surface2);color:var(--accent2)}}
.brush-active-btn{{background:rgba(239,68,68,.15);color:var(--red);border-color:var(--red)}}
.brush-active-btn:hover{{background:var(--red);color:#fff}}
.action-btn{{background:transparent;border:1px solid var(--border);color:var(--text-dim);font-size:11px;padding:5px 10px;border-radius:6px;cursor:pointer;transition:all .15s;font-weight:600;letter-spacing:.02em}}
.action-btn:hover{{background:var(--surface2);color:var(--accent2);border-color:var(--accent2)}}
.action-btn.copied{{background:var(--green);color:#fff;border-color:var(--green)}}

.tbl-wrap{{border-radius:12px;border:1px solid var(--border);overflow:hidden}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:var(--surface);padding:12px 16px;text-align:left;font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:.5px;color:var(--text-dim);cursor:pointer;user-select:none;border-bottom:2px solid var(--border)}}
th:hover{{color:var(--accent2)}}
th .arrow{{margin-left:4px;opacity:.5}}
.filter-row th{{padding:4px 6px;background:var(--surface2);border-bottom:1px solid var(--border)}}
.col-filter{{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:5px 8px;color:var(--text);font-size:11px;font-family:var(--mono);outline:none}}
td{{padding:10px 16px;border-bottom:1px solid var(--border);vertical-align:top}}
tr{{transition:background .1s}}
tr:hover{{background:var(--surface2)}}
tr.async-row{{border-left:3px solid var(--cyan)}}
tr.block-row{{border-left:3px solid var(--orange)}}
tr.crash-row{{border-left:3px solid var(--red)}}
tr.group-row{{background:var(--surface);cursor:pointer;border-left:3px solid var(--accent)}}
tr.group-row:hover{{background:var(--surface2)}}
tr.group-child{{display:none}}
tr.group-child.show{{display:table-row}}

.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.tag-block{{background:rgba(249,115,22,.15);color:var(--orange)}}
.tag-async{{background:rgba(6,182,212,.15);color:var(--cyan)}}
.tag-crash{{background:rgba(239,68,68,.15);color:var(--red)}}
.dur{{font-family:var(--mono);font-weight:600}}
.dur-high{{color:var(--red)}}.dur-med{{color:var(--orange)}}.dur-low{{color:var(--green)}}
.grp-count{{font-family:var(--mono);font-weight:800;color:var(--accent2);font-size:16px}}

.expand-toggle{{cursor:pointer;color:var(--accent2);font-size:18px;line-height:1;transition:transform .2s;display:inline-block}}
.expand-toggle.open{{transform:rotate(90deg)}}
.detail-row{{display:none}}
.detail-row.show{{display:table-row}}
.detail-cell{{padding:0 16px 16px;background:var(--surface)}}
.detail-inner{{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 0}}
.detail-section{{background:var(--bg);border-radius:8px;padding:16px;border:1px solid var(--border)}}
.detail-section h4{{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--accent2);margin-bottom:8px}}
pre.stack{{font-family:var(--mono);font-size:12px;line-height:1.7;white-space:pre-wrap;word-break:break-word;color:var(--text-dim);max-height:400px;overflow-y:auto}}
pre.stack .culprit{{color:var(--red);font-weight:700}}
pre.stack .user-code{{color:var(--cyan)}}
.var-list{{font-family:var(--mono);font-size:12px;line-height:1.8}}
.var-name{{color:var(--cyan)}}.var-val{{color:var(--text-dim)}}
.meta-grid{{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px}}
.meta-grid dt{{color:var(--text-dim);font-weight:600}}.meta-grid dd{{color:var(--text)}}

.pagination{{display:flex;align-items:center;justify-content:center;gap:12px;padding:16px 0}}
.page-info{{font-size:13px;color:var(--text-dim)}}

.footer{{text-align:center;padding:32px 0;color:var(--text-dim);font-size:12px;border-top:1px solid var(--border);margin-top:48px}}

/* CULPRIT SECTION */
.culprit-shell{{margin-bottom:28px;border-radius:16px;position:relative;background:var(--surface);box-shadow:0 8px 32px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.04);overflow:hidden}}
.culprit-shell::before{{content:'';position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,var(--accent),var(--cyan),var(--pink));opacity:.95}}
.culprit-details{{margin:0}}
.culprit-details>summary{{list-style:none;cursor:pointer;padding:0;border:0;outline:none}}
.culprit-details>summary::-webkit-details-marker{{display:none}}
.culprit-details>summary:focus-visible{{outline:2px solid var(--accent2);outline-offset:2px;border-radius:12px}}
.culprit-sum-wrap{{display:flex;align-items:stretch;gap:0;min-height:88px;transition:background .2s,box-shadow .2s}}
.culprit-details:not([open]) .culprit-sum-wrap{{background:linear-gradient(135deg,var(--surface2) 0%,var(--surface3) 55%,var(--surface2) 100%);box-shadow:inset 0 0 0 1px rgba(129,140,248,.22)}}
.culprit-details:not([open]) .culprit-sum-wrap:hover{{background:linear-gradient(135deg,var(--surface3) 0%,var(--surface2) 50%,var(--surface3) 100%);box-shadow:inset 0 0 0 1px rgba(129,140,248,.45),0 0 24px rgba(99,102,241,.12)}}
.culprit-details[open] .culprit-sum-wrap{{background:var(--surface2);box-shadow:inset 0 -1px 0 var(--border)}}
.culprit-sum-rail{{width:5px;flex-shrink:0;background:linear-gradient(180deg,var(--accent),var(--cyan));opacity:.85}}
.culprit-sum-main{{flex:1;min-width:0;padding:18px 16px 18px 14px;display:flex;flex-direction:column;justify-content:center;gap:6px}}
.culprit-kicker{{font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--accent2);opacity:.9}}
.culprit-sum-title{{font-size:17px;font-weight:800;letter-spacing:-.03em;color:var(--text);line-height:1.25;margin:0}}
.culprit-sum-hint{{font-size:12px;color:var(--text-dim);line-height:1.5;max-width:46rem;margin:0}}
.culprit-sum-aside{{flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;justify-content:center;gap:10px;padding:16px 18px 16px 8px}}
.culprit-cta{{display:inline-flex;align-items:center;gap:8px;padding:10px 16px;border-radius:999px;font-size:12px;font-weight:800;letter-spacing:.02em;background:linear-gradient(135deg,var(--accent),#4f46e5);color:#fff;border:none;box-shadow:0 4px 14px rgba(99,102,241,.4);pointer-events:none;user-select:none;white-space:nowrap}}
.culprit-details[open] .culprit-cta{{background:var(--surface3);color:var(--text-dim);box-shadow:none;border:1px solid var(--border)}}
.culprit-cta-ico{{font-size:14px;opacity:.95;transition:transform .25s ease}}
.culprit-details:not([open]) .culprit-cta-ico{{transform:rotate(0deg);animation:culpritPulse 2.4s ease-in-out infinite}}
.culprit-details[open] .culprit-cta-ico{{transform:rotate(180deg);animation:none}}
@keyframes culpritPulse{{0%,100%{{opacity:1}}50%{{opacity:.72}}}}
.culprit-sum-badge{{font-size:11px;font-weight:700;padding:6px 12px;border-radius:999px;background:rgba(239,68,68,.14);color:var(--red);border:1px solid rgba(239,68,68,.3);white-space:nowrap}}
.culprit-panel{{padding:20px;background:var(--bg)}}
.culprit-toolbar{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap}}
.culprit-intro{{font-size:12px;color:var(--text-dim);line-height:1.55;margin:0;padding:14px 16px;background:var(--surface);border-radius:12px;border:1px solid var(--border);border-left:4px solid var(--cyan);flex:1}}
.culprit-table-wrap{{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:var(--surface)}}
.culprit-table{{width:100%;border-collapse:collapse;font-size:13px}}
.culprit-table th{{background:var(--surface2);padding:10px 12px;text-align:left;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--text-dim);border-bottom:1px solid var(--border)}}
.culprit-table td{{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:top}}
.culprit-table tr:last-child td{{border-bottom:none}}
.culprit-table tr:hover{{background:var(--surface3)}}
.culprit-frame-cell{{
  font-family:var(--mono);font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;
  max-height:160px;overflow-y:auto;background:var(--bg);padding:10px;border-radius:8px;
  border:1px solid var(--border);position:relative;scrollbar-width:thin;scrollbar-color:var(--surface3) transparent;
}}
.culprit-frame-cell::-webkit-scrollbar{{width:6px}}
.culprit-frame-cell::-webkit-scrollbar-thumb{{background:var(--surface3);border-radius:3px}}
.culprit-frame-cell .lib-frame{{color:var(--text-dim);opacity:.55}}
.culprit-frame-cell .user-frame{{color:var(--cyan)}}
.culprit-frame-cell .culprit-frame{{color:var(--red);font-weight:700;background:rgba(239,68,68,.12);padding:2px 4px;border-radius:4px;display:inline-block}}
.section-empty{{color:var(--text-dim);font-size:13px;text-align:center;padding:24px}}

@media(max-width:1100px){{.charts{{grid-template-columns:1fr}}}}
@media(max-width:820px){{.detail-inner{{grid-template-columns:1fr}} .wrap{{padding:18px 14px 56px}} .header{{flex-direction:column;align-items:flex-start}} .culprit-toolbar{{flex-direction:column;align-items:stretch}}}}
</style>
</head>
<body>
<div class="wrap" id="app">
  <div class="header">
    <div class="title">
      <h1>LoopSentry Report</h1>
      <p>Asyncio event-loop analysis with filterable timelines.</p>
    </div>
    <div class="badge" id="gen-time"></div>
  </div>

  <div class="cards" id="cards"></div>

  <section class="culprit-shell">
    <details class="culprit-details" id="culprit-details">
      <summary class="culprit-summary-trigger" title="Click to expand or collapse the stack digest">
        <div class="culprit-sum-wrap">
          <div class="culprit-sum-rail" aria-hidden="true"></div>
          <div class="culprit-sum-main">
            <span class="culprit-kicker">Stack Digest</span>
            <p class="culprit-sum-title">Culprit Frames Summary</p>
            <p class="culprit-sum-hint">Aggregated unique blocking locations based on current filters. Expand to see hints, counts, and exact culprit frames.</p>
          </div>
          <div class="culprit-sum-aside">
            <span class="culprit-cta"><span class="culprit-cta-ico" aria-hidden="true">⌄</span><span class="culprit-cta-label">Expand</span></span>
            <span class="culprit-sum-badge" id="culprit-summary-badge">—</span>
          </div>
        </div>
      </summary>
      <div class="culprit-panel">
        <div class="culprit-toolbar">
          <p class="culprit-intro">Each row represents a unique culprit frame. Counts reflect matching events. Pre-scrolled to the blocking line.</p>
          <button class="mini-btn" id="copy-all-culprits-btn" onclick="copyAllCulpritStacks(this)">Copy Digest</button>
        </div>
        <div class="culprit-table-wrap">
          <table class="culprit-table">
            <thead>
              <tr>
                <th style="width:60px">Count</th>
                <th style="width:90px">Type</th>
                <th style="width:220px">Location / Hint</th>
                <th>Culprit Frame (±5 lines)</th>
                <th style="width:70px">Action</th>
              </tr>
            </thead>
            <tbody id="culprit-summary-body">
              <tr><td colspan="5" class="section-empty">Loading…</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </details>
  </section>

  <div class="charts">
    <section class="chart-card">
      <div class="chart-head">
        <div>
          <h3>CPU Timeline</h3>
          <p>Real event-time spacing. Average CPU stays primary, with optional per-core overlays.</p>
        </div>
        <div class="chart-actions">
          <button class="mini-btn active" id="cpu-mode-avg">Average</button>
          <button class="mini-btn" id="cpu-mode-cores">Per-Core Overlay</button>
        </div>
      </div>
      <div class="legend">
        <span><i style="background:var(--cyan)"></i> Average CPU</span>
        <span><i style="background:var(--accent2)"></i> Per-Core Lines</span>
      </div>
      <div class="chart-shell">
        <svg id="cpu-chart" viewBox="0 0 900 300" preserveAspectRatio="none"></svg>
        <div class="chart-tip" id="cpu-tip"></div>
      </div>
      <div class="chart-meta" id="cpu-meta"></div>
    </section>

    <section class="chart-card">
      <div class="chart-head">
        <div>
          <h3>Block Timeline</h3>
          <p>Actual event-time line chart for durations. Click a point to jump to that event.</p>
        </div>
        <div class="chart-actions">
          <button class="mini-btn active" id="focus-all">All Events</button>
          <button class="mini-btn" id="focus-block">Blocks</button>
          <button class="mini-btn" id="focus-async">Async</button>
        </div>
      </div>
      <div class="legend">
        <span><i style="background:var(--orange)"></i> Block</span>
        <span><i style="background:var(--cyan)"></i> Async</span>
        <span><i style="background:var(--red)"></i> Crash</span>
      </div>
      <div class="chart-shell">
        <svg id="duration-chart" viewBox="0 0 900 300" preserveAspectRatio="none"></svg>
        <div class="chart-tip" id="duration-tip"></div>
      </div>
      <div class="chart-meta" id="duration-meta"></div>
    </section>
  </div>

  <div class="controls">
    <input class="search" id="search" placeholder="Search stacks, hints, tasks, app location, blocking location..." autocomplete="off">
    <select class="btn" id="sort-select">
      <option value="time">Sort: Time</option>
      <option value="duration">Sort: Duration</option>
      <option value="cpu">Sort: CPU</option>
      <option value="memory">Sort: Memory</option>
      <option value="type">Sort: Type</option>
    </select>
    <div class="filter-pop">
      <button class="btn filter-toggle" id="exclude-toggle" type="button"><span id="exclude-summary">Exclude Locations</span></button>
      <div class="filter-panel" id="exclude-panel">
        <div class="filter-row-actions">
          <span class="filter-panel-title">Exclude Locations</span>
          <button class="filter-link" id="exclude-clear" type="button">Clear</button>
        </div>
        <div class="filter-options" id="exclude-location-options"></div>
      </div>
    </div>
    <div class="filter-pop">
      <button class="btn filter-toggle" id="export-toggle" type="button">Export</button>
      <div class="export-panel" id="export-panel">
        <button class="export-btn" id="export-csv">Download CSV</button>
        <button class="export-btn" id="export-json">Download JSON</button>
      </div>
    </div>
    <button class="btn brush-active-btn" id="clear-brush" style="display:none">Clear Zoom</button>
    <button class="btn active" id="filter-all">All</button>
    <button class="btn" id="filter-block">Blocks</button>
    <button class="btn" id="filter-async">Async</button>
    <button class="btn active" id="view-grouped">Grouped</button>
    <button class="btn" id="view-timeline">Timeline</button>
  </div>

  <div class="tbl-wrap">
    <table>
      <thead>
        <tr id="thead-row"></tr>
        <tr class="filter-row" id="filter-row">
          <th></th>
          <th><input class="col-filter" data-col="type" placeholder="block, async..."></th>
          <th><input class="col-filter" data-col="time" placeholder="HH:MM:SS..."></th>
          <th><input class="col-filter" data-col="duration" placeholder=">=0.5"></th>
          <th><input class="col-filter" data-col="cpu" placeholder=">=50"></th>
          <th><input class="col-filter" data-col="memory" placeholder=">=100"></th>
          <th><input class="col-filter" data-col="hint" placeholder="text..."></th>
          <th><input class="col-filter" data-col="location" placeholder="file:line..."></th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <div class="pagination" id="pagination"></div>
  <div class="footer">Generated by <strong>LoopSentry</strong> • Report v2</div>
</div>

<script>
const DATA={blocks_json};
const STATS={stats_json};
const PAGE_SIZE=1000;
const STACK_LIB_RE=/site-packages|dist-packages|lib[/\\\\]python\\d|[/\\\\]Python\\d+[/\\\\]Lib[/\\\\]|asyncio[/\\\\]|loopsentry[/\\\\]|File \"<string>\"|File \"<stdin>\"|File \"<frozen/i;

document.getElementById('gen-time').textContent=new Date().toLocaleString();

const chartState={{cpuMode:'avg',durationFilter:'all'}};

(function renderCards(){{
  const c=document.getElementById('cards');
  [
    {{v:STATS.count,l:'Blocking Events',cls:'orange',h:'Sync calls that blocked the event loop beyond the threshold'}},
    {{v:STATS.async_slow,l:'Slow Async Tasks',cls:'cyan',h:'Async tasks that took longer than the async threshold to complete'}},
    {{v:STATS.total_time.toFixed(2)+'s',l:'Block Time Lost',cls:'yellow',h:'Cumulative sum of all blocking durations. Concurrent overlap is not removed'}},
    {{v:(STATS.async_total_time||0).toFixed(2)+'s',l:'Async Time',cls:'cyan',h:'Cumulative slow-task duration, not wall-clock time'}},
    {{v:STATS.crashes,l:'Crashes',cls:'red',h:'Unresolved blocks where the event loop never recovered'}},
    {{v:STATS.cpu_core_count||0,l:'CPU Cores',cls:'pink',h:'Highest core count observed in captured per-core snapshots'}},
    {{v:(STATS.max_cpu_avg||0).toFixed(1)+'%',l:'Peak Avg CPU',cls:'pink',h:'Highest average CPU usage across all cores seen during any event'}},
    {{v:(((STATS.total_time||0)+((STATS.async_total_time)||0))/Math.max(1,(STATS.count||0)+(STATS.async_slow||0))).toFixed(4)+'s',l:'Avg Event Time',cls:'green',h:'Average duration across resolved block and async events'}},
  ].forEach(d=>{{c.innerHTML+=`<div class="card ${{d.cls}}"><div class="val">${{d.v}}</div><div class="lbl">${{d.l}}</div><div class="hint">${{d.h}}</div></div>`}});
}})();

let currentSort='time',currentDir=-1,currentFilter='all',searchTerm='',currentPage=1;
let viewMode='grouped';
let excludeLocations=new Set();
let timeRangeFilter=null;
let colFilters={{type:'',time:'',duration:'',cpu:'',memory:'',hint:'',location:''}};
let debounceTimer=null;

function escHtml(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}
function escAttr(s){{return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;')}}
function buildCulpritRows(list){{
  const acc=new Map();
  list.forEach(b=>{{
    const key=culpritSummaryKeyForEvent(b);
    if(!acc.has(key))acc.set(key,{{count:0,sample:b}});
    acc.get(key).count++;
  }});
  return[...acc.entries()].sort((a,b)=>b[1].count-a[1].count).map(([k,v])=>({{code:k,count:v.count,sample:v.sample}}));
}}
function durClass(d){{if(typeof d!=='number')return'';return d>2?'dur-high':d>0.5?'dur-med':'dur-low'}}
function parseNumericFilter(expr){{
  if(!expr)return null;expr=expr.trim();
  const m=expr.match(/^(>=|<=|!=|<>|>|<|=)\\s*(.+)$/);
  if(m){{const op=m[1]==='<>'?'!=':m[1];const val=parseFloat(m[2]);if(isNaN(val))return null;return{{op,val}};}}
  const val=parseFloat(expr);if(!isNaN(val))return{{op:'=',val}};return null;
}}
function matchNumeric(value,f){{if(!f)return true;switch(f.op){{case'>=':return value>=f.val;case'<=':return value<=f.val;case'>':return value>f.val;case'<':return value<f.val;case'!=':return value!==f.val;case'=':return value===f.val;default:return true;}}}}
function matchString(value,f){{if(!f)return true;return String(value).toLowerCase().includes(f.toLowerCase())}}
function parseTs(ts){{const d=new Date(ts);return Number.isNaN(d.getTime())?0:d.getTime()}}
function shortTime(ts){{const t=(ts.split('T')[1]||'');return t.slice(0,8)}}

function baseEventType(b){{
  if(b.total_duration==='CRASH')return'crash';
  return b.type==='async_bottleneck'?'async':'block';
}}

function initLocationSelectors(){{
  const locations=[...new Set(DATA.map(b=>b.location||'Unknown'))].sort((a,b)=>a.localeCompare(b));
  const container=document.getElementById('exclude-location-options');
  locations.forEach(loc=>{{
    const safe=escHtml(loc);
    container.innerHTML+=`<label class="filter-option"><input type="checkbox" value="${{safe}}" data-location-checkbox> <span>${{safe}}</span></label>`;
  }});
  container.querySelectorAll('[data-location-checkbox]').forEach(box=>{{
    box.addEventListener('change',()=>{{
      const selected=[...container.querySelectorAll('[data-location-checkbox]:checked')].map(node=>node.value);
      excludeLocations=new Set(selected);
      updateExcludeSummary();
      currentPage=1;
      render();
    }});
  }});
  updateExcludeSummary();
}}

function updateExcludeSummary(){{
  const label=document.getElementById('exclude-summary');
  if(excludeLocations.size===0){{label.textContent='Exclude Locations';return;}}
  if(excludeLocations.size===1){{label.textContent=`Exclude: ${{[...excludeLocations][0]}}`;return;}}
  label.textContent=`Exclude: ${{excludeLocations.size}} locations`;
}}

function applyColumnFilters(b){{
  if(colFilters.type&&!matchString(baseEventType(b),colFilters.type))return false;
  if(colFilters.time&&!matchString(b.timestamp,colFilters.time))return false;
  if(colFilters.duration){{const nf=parseNumericFilter(colFilters.duration);if(nf){{const dur=typeof b.total_duration==='number'?b.total_duration:-1;if(!matchNumeric(dur,nf))return false;}}else{{if(!matchString(typeof b.total_duration==='number'?b.total_duration.toFixed(4):String(b.total_duration),colFilters.duration))return false;}}}}
  if(colFilters.cpu){{const nf=parseNumericFilter(colFilters.cpu);if(nf){{if(!matchNumeric(b.sys?.cpu_percent||0,nf))return false;}}else{{if(!matchString(String(b.sys?.cpu_percent||0),colFilters.cpu))return false;}}}}
  if(colFilters.memory){{const nf=parseNumericFilter(colFilters.memory);if(nf){{if(!matchNumeric(b.sys?.memory_mb||0,nf))return false;}}else{{if(!matchString(String(b.sys?.memory_mb||0),colFilters.memory))return false;}}}}
  if(colFilters.hint&&!matchString(b.hint,colFilters.hint))return false;
  if(colFilters.location&&!matchString(b.location,colFilters.location))return false;
  return true;
}}

function getFiltered(){{
  let list=[...DATA];
  if(currentFilter==='block')list=list.filter(b=>b.type!=='async_bottleneck');
  if(currentFilter==='async')list=list.filter(b=>b.type==='async_bottleneck');
  if(excludeLocations.size)list=list.filter(b=>!excludeLocations.has(b.location||'Unknown'));
  if(timeRangeFilter)list=list.filter(b=>{{const ts=parseTs(b.timestamp);return ts>=timeRangeFilter.min && ts<=timeRangeFilter.max}});
  if(searchTerm){{const q=searchTerm.toLowerCase();list=list.filter(b=>{{const hay=(b.hint+b.location+(b.blocking_location||'')+b.coro+b.task_name+(b.stack||[]).join('')+b.timestamp+b.type+JSON.stringify(b.user_frames||[])).toLowerCase();return hay.includes(q)}})}}
  list=list.filter(applyColumnFilters);
  const key={{time:a=>a.timestamp,duration:a=>typeof a.total_duration==='number'?a.total_duration:-1,cpu:a=>(a.sys?.cpu_percent||0),memory:a=>(a.sys?.memory_mb||0),type:a=>a.type}}[currentSort]||(a=>a.timestamp);
  list.sort((a,b)=>{{const va=key(a),vb=key(b);return va<vb?currentDir:va>vb?-currentDir:0}});
  return list;
}}

function stackCulpritIndex(stack){{
  if(!stack||!stack.length)return -1;
  let culprit=-1;
  stack.forEach((f,i)=>{{if(!STACK_LIB_RE.test(f))culprit=i;}});
  if(culprit===-1&&stack.length)return stack.length-1;
  return culprit;
}}

function stackCulpritFrameText(stack){{
  const i=stackCulpritIndex(stack);
  if(i<0)return '';
  return (stack[i]||'').replace(/\\n$/,'').trim();
}}

function culpritSummaryKeyForEvent(b){{
  const k=stackCulpritFrameText(b.stack||[]);
  if(k)return k;
  return String(b.trigger||b.coro||b.location||'Unknown').trim();
}}

function renderStack(stack){{
  if(!stack||!stack.length)return'<em>No stack trace</em>';
  let culprit=-1;
  const lines=stack.map((f,i)=>{{const isLib=STACK_LIB_RE.test(f);if(!isLib)culprit=i;return{{text:f.replace(/\\n$/,''),isLib}}}});
  if(culprit===-1&&lines.length)culprit=lines.length-1;
  return lines.map((l,i)=>{{const cls=i===culprit?'culprit':l.isLib?'':'user-code';return`<span class="${{cls}}">${{i===culprit?'>>> ':''}}${{escHtml(l.text)}}</span>`}}).join('\\n');
}}

function renderSummaryStack(stack){{
  if(!stack||!stack.length)return'<em style="color:var(--text-dim)">No stack trace</em>';
  let culpritIdx=-1;
  const lines=stack.map((f,i)=>{{
    const isLib=STACK_LIB_RE.test(f);
    if(!isLib)culpritIdx=i;
    return{{text:f.replace(/\\n$/,''),isLib,idx:i}};
  }});
  if(culpritIdx===-1&&lines.length)culpritIdx=lines.length-1;

  const start=Math.max(0,culpritIdx-5);
  const end=Math.min(lines.length-1,culpritIdx+5);
  const visible=lines.slice(start,end+1);

  let html='';
  if(start>0)html+=`<span class="lib-frame" style="opacity:.5">... (${{start}} earlier frames)\\n</span>`;
  visible.forEach(l=>{{
    let cls='lib-frame';
    if(l.idx===culpritIdx)cls='culprit-frame';
    else if(!l.isLib)cls='user-frame';
    const prefix=l.idx===culpritIdx?'>>> ':'    ';
    html+=`<span class="${{cls}}">${{prefix}}${{escHtml(l.text)}}</span>\\n`;
  }});
  if(end<lines.length-1)html+=`<span class="lib-frame" style="opacity:.5">... (${{lines.length-1-end}} later frames) ...</span>`;
  return html;
}}

function renderUserFrames(frames){{
  if(!frames||!frames.length)return'<p class="section-empty" style="margin:0">No application frames detected in this stack (try <code>--project-root</code> if your package is installed editable under site-packages).</p>';
  return'<pre class="stack" style="max-height:220px">'+frames.map(fr=>{{const fn=fr.func?escHtml(fr.func)+' ':'';
    return`<span class="user-code">${{fn}}${{escHtml(fr.short||'')}}</span>\\n  ${{escHtml(fr.file||'')}}\\n`;}}).join('\\n')+'</pre>';
}}

function renderLocals(locals){{
  if(!locals||!locals.length)return'';
  return locals.map(fr=>{{const hdr=fr.file?`${{fr.func}} (${{fr.file}}:${{fr.line}})`:fr.func;const vars=fr.vars?Object.entries(fr.vars).map(([k,v])=>`  <span class="var-name">${{escHtml(k)}}</span> = <span class="var-val">${{escHtml(v)}}</span>`).join('\\n'):'';return`<strong>${{escHtml(hdr)}}</strong>\\n${{vars}}`}}).join('\\n\\n');
}}

function renderDetailRow(b){{
  const sys=b.sys||{{}};const gc=sys.gc_counts||[0,0,0];
  const excHtml=b.exception?`<div class="detail-section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h4>Exception</h4></div><pre class="stack"><span class="culprit">${{escHtml(b.exception.type)}}: ${{escHtml(b.exception.message)}}</span>\n${{(b.exception.traceback||[]).map(l=>escHtml(l)).join('')}}</pre></div>`:'';
  const localsHtml=b.locals&&b.locals.length?`<div class="detail-section"><h4>Captured Variables</h4><pre class="var-list">${{renderLocals(b.locals)}}</pre></div>`:'';
  const perCore=(sys.cpu_per_core&&sys.cpu_per_core.length)?`<dt>Total Cores</dt><dd>${{sys.cpu_per_core.length}}</dd><dt>Per Core</dt><dd style="font-family:var(--mono);font-size:11px">${{sys.cpu_per_core.map((c,i)=>{{const clr=c>80?'var(--red)':c>40?'var(--orange)':'var(--green)';return`<span style="display:inline-block;margin:1px 2px;padding:1px 4px;border-radius:999px;background:${{clr}}20;color:${{clr}}">${{i}}:${{c.toFixed(0)}}%</span>`}}).join('')}}</dd>`:'';
  return`<td colspan="8" class="detail-cell"><div class="detail-inner">
    <div><div class="detail-section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h4>Metadata</h4><button class="action-btn" onclick="copyEventJson(${{b.id}}, this)">Copy JSON</button></div><dl class="meta-grid">
      <dt>Event ID</dt><dd>#${{b.id}}</dd>
      <dt>Timestamp</dt><dd>${{b.timestamp}}</dd>
      <dt>PID</dt><dd>${{b.pid}}</dd>
      <dt>Your code</dt><dd style="font-family:var(--mono);color:var(--cyan)">${{escHtml(b.location||'Unknown')}}</dd>
      <dt>Blocking (innermost)</dt><dd style="font-family:var(--mono);color:var(--text-dim)">${{escHtml(b.blocking_location||'—')}}</dd>
      ${{b.task_name?`<dt>Task</dt><dd>${{escHtml(b.task_name)}}</dd>`:''}}
      ${{b.coro?`<dt>Coroutine</dt><dd>${{escHtml(b.coro)}}</dd>`:''}}
      <dt>CPU</dt><dd>${{(sys.cpu_percent||0)}}%</dd>
      <dt>Memory</dt><dd>${{(sys.memory_mb||0).toFixed(1)}} MB</dd>
      <dt>Threads</dt><dd>${{sys.thread_count||'?'}}</dd>
      <dt>GC</dt><dd>Gen0=${{gc[0]||0}} Gen1=${{gc[1]||0}} Gen2=${{gc[2]||0}}</dd>
      ${{perCore}}
    </dl></div>${{excHtml}}</div>
    <div><div class="detail-section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h4>Your code</h4></div>${{renderUserFrames(b.user_frames)}}</div>
    <div><div class="detail-section"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h4>Full stack trace</h4><button class="action-btn" onclick="copyStackTrace(${{b.id}}, this)">Copy Stack</button></div><pre class="stack">${{renderStack(b.stack)}}</pre></div>${{localsHtml}}</div>
  </div></td>`;
}}

window.copyEventJson=function(id,btn){{
  const ev=DATA.find(e=>e.id===id);if(!ev)return;
  navigator.clipboard.writeText(JSON.stringify(ev,null,2)).then(()=>{{const old=btn.textContent;btn.textContent='Copied';btn.classList.add('copied');setTimeout(()=>{{btn.textContent=old;btn.classList.remove('copied')}},2000)}});
}};
window.copyStackTrace=function(id,btn){{
  const ev=DATA.find(e=>e.id===id);if(!ev||!ev.stack)return;
  navigator.clipboard.writeText(ev.stack.join('')).then(()=>{{const old=btn.textContent;btn.textContent='Copied';btn.classList.add('copied');setTimeout(()=>{{btn.textContent=old;btn.classList.remove('copied')}},2000)}});
}};
window.copyAllCulpritStacks=function(btn){{
  const list=getFiltered();
  const rows=buildCulpritRows(list);
  if(!rows.length)return;
  const lines=['LoopSentry Culprit Digest',`Generated: ${{new Date().toISOString()}}`,`Total Events: ${{list.length}} | Unique Culprits: ${{rows.length}}`,'---'];
  rows.forEach((r,i)=>{{
    const b=r.sample;
    const evt=baseEventType(b).toUpperCase();
    lines.push(`#${{i+1}} [${{evt}}] Count: ${{r.count}}`);
    lines.push(`Hint: ${{b.hint||'—'}}`);
    lines.push(`Location: ${{b.location||'—'}}`);
    lines.push(`Blocking: ${{b.blocking_location||'—'}}`);
    lines.push('Culprit Frame:');
    const culpritLine=stackCulpritFrameText(b.stack||[]);
    lines.push(`  >>> ${{culpritLine||'N/A'}}`);
    lines.push('---');
  }});
  const text=lines.join('\\n');
  navigator.clipboard.writeText(text).then(()=>{{
    const old=btn.textContent;btn.textContent='Copied';btn.classList.add('copied');
    setTimeout(()=>{{btn.textContent=old;btn.classList.remove('copied')}},2000);
  }});
}};

function renderEventRow(b){{
  const dur=b.total_duration;const durFmt=typeof dur==='number'?dur.toFixed(4)+'s':String(dur);
  const evt=baseEventType(b);
  const cls=evt==='crash'?'crash-row':evt==='async'?'async-row':'block-row';
  const tagCls=evt==='crash'?'tag-crash':evt==='async'?'tag-async':'tag-block';
  const tagLbl=evt==='crash'?'CRASH':evt==='async'?'ASYNC':'BLOCK';
  const sys=b.sys||{{}};
  return`<tr class="${{cls}}" data-event-id="${{b.id}}">
    <td><span class="expand-toggle" data-i="${{b.id}}">▸</span> #${{b.id}}</td>
    <td><span class="tag ${{tagCls}}">${{tagLbl}}</span></td>
    <td style="font-family:var(--mono);font-size:12px">${{shortTime(b.timestamp)}}</td>
    <td><span class="dur ${{durClass(dur)}}">${{durFmt}}</span></td>
    <td>${{(sys.cpu_percent||0).toFixed(0)}}%</td>
    <td>${{(sys.memory_mb||0).toFixed(0)}}MB</td>
    <td>${{escHtml(b.hint)}}</td>
    <td style="font-family:var(--mono);font-size:12px">${{escHtml(b.location)}}</td>
  </tr><tr class="detail-row" id="detail-${{b.id}}">${{renderDetailRow(b)}}</tr>`;
}}

function buildGroups(list){{
  const map=new Map();
  list.forEach(b=>{{
    const key=b.location||'Unknown';
    if(!map.has(key))map.set(key,{{location:key,hint:b.hint,events:[],totalDur:0,count:0}});
    const g=map.get(key);
    g.events.push(b);g.count++;
    if(typeof b.total_duration==='number')g.totalDur+=b.total_duration;
  }});
  return [...map.values()].sort((a,b)=>b.totalDur-a.totalDur);
}}

function renderHeader(){{
  const cols=viewMode==='grouped'
    ? [['▸',''],['Location',''],['Hint',''],['Count',''],['Total',''],['Avg',''],['CPU Range',''],['Types','']]
    : [['#',''],['Type','type'],['Time','time'],['Duration','duration'],['CPU%','cpu'],['Mem','memory'],['Hint',''],['Location','']];
  document.getElementById('thead-row').innerHTML=cols.map(([lbl,key])=>{{const arrow=key===currentSort?(currentDir===-1?'▼':'▲'):'';return`<th${{key?` onclick="sortBy('${{key}}')"`:''}}>${{lbl}}<span class="arrow">${{arrow}}</span></th>`}}).join('');
  document.getElementById('filter-row').style.display=viewMode==='grouped'?'none':'';
}}

function renderPagination(totalItems){{
  const totalPages=Math.max(1,Math.ceil(totalItems/PAGE_SIZE));
  if(currentPage>totalPages)currentPage=totalPages;
  const pg=document.getElementById('pagination');
  if(totalPages<=1){{pg.innerHTML=`<span class="page-info">${{totalItems}} events</span>`;return;}}
  pg.innerHTML=`<button class="btn" id="pg-prev" ${{currentPage<=1?'disabled':''}}>← Prev</button><span class="page-info">Page ${{currentPage}} of ${{totalPages}} (${{totalItems}} events)</span><button class="btn" id="pg-next" ${{currentPage>=totalPages?'disabled':''}}>Next →</button>`;
  document.getElementById('pg-prev').addEventListener('click',()=>{{if(currentPage>1){{currentPage--;render()}}}});
  document.getElementById('pg-next').addEventListener('click',()=>{{if(currentPage<totalPages){{currentPage++;render()}}}});
}}

function renderGrouped(){{
  const list=getFiltered();
  const groups=buildGroups(list);
  const tbody=document.getElementById('tbody');
  let html='';
  groups.forEach((g,gi)=>{{
    const avg=g.count?g.totalDur/g.count:0;
    const types=[...new Set(g.events.map(e=>baseEventType(e).toUpperCase()))];
    const typeTags=types.map(t=>`<span class="tag ${{t==='ASYNC'?'tag-async':'tag-block'}}">${{t}}</span>`).join(' ');
    const cpuVals=g.events.map(e=>e.sys?.cpu_percent||0);
    const cpuMin=Math.min(...cpuVals).toFixed(0),cpuMax=Math.max(...cpuVals).toFixed(0);
    html+=`<tr class="group-row" data-grp="${{gi}}"><td><span class="expand-toggle" data-grp="${{gi}}">▸</span></td><td style="font-family:var(--mono);font-size:12px">${{escHtml(g.location)}}</td><td>${{escHtml(g.hint)}}</td><td><span class="grp-count">${{g.count}}</span></td><td><span class="dur ${{durClass(g.totalDur)}}">${{g.totalDur.toFixed(2)}}s</span></td><td><span class="dur ${{durClass(avg)}}">${{avg.toFixed(4)}}s</span></td><td>${{cpuMin}}-${{cpuMax}}%</td><td>${{typeTags}}</td></tr>`;
    const repEvent = g.events[0];
    if(repEvent && repEvent.stack) html+=`<tr class="group-child" data-grp="${{gi}}"><td colspan="8" class="detail-cell" style="padding:16px"><div class="detail-section" style="margin-bottom:0"><h4>Representative Culprit Stack</h4><pre class="stack">${{renderStack(repEvent.stack)}}</pre></div></td></tr>`;
    html+=`<tr class="group-child" data-grp="${{gi}}" style="background:var(--surface2)"><td style="font-weight:800;color:var(--text-dim);font-size:11px">#</td><td style="font-weight:800;color:var(--text-dim);font-size:11px">Type</td><td style="font-weight:800;color:var(--text-dim);font-size:11px">Time</td><td style="font-weight:800;color:var(--text-dim);font-size:11px">Duration</td><td style="font-weight:800;color:var(--text-dim);font-size:11px">CPU%</td><td style="font-weight:800;color:var(--text-dim);font-size:11px">Mem</td><td style="font-weight:800;color:var(--text-dim);font-size:11px">Hint</td><td style="font-weight:800;color:var(--text-dim);font-size:11px">Location</td></tr>`;
    g.events.forEach(b=>{{html+=`<tr class="group-child" data-grp="${{gi}}">${{renderEventRow(b).match(/<tr[^>]*>(.*?)<\\/tr>/s)?.[1]||''}}</tr>`;html+=`<tr class="group-child detail-row" data-grp="${{gi}}" id="detail-${{b.id}}">${{renderDetailRow(b)}}</tr>`;}});
  }});
  tbody.innerHTML=html;
  document.getElementById('pagination').innerHTML=`<span class="page-info">${{groups.length}} groups, ${{list.length}} events</span>`;
  tbody.querySelectorAll('tr.group-row').forEach(row=>{{row.addEventListener('click',()=>{{const gi=row.dataset.grp;const children=tbody.querySelectorAll(`tr.group-child[data-grp="${{gi}}"]`);const toggle=row.querySelector('.expand-toggle');const isOpen=toggle.classList.contains('open');children.forEach(c=>{{if(isOpen)c.classList.remove('show');else if(!c.classList.contains('detail-row'))c.classList.add('show');}});toggle.classList.toggle('open');toggle.textContent=toggle.classList.contains('open')?'▾':'▸';}})}}); 
  tbody.querySelectorAll('.group-child .expand-toggle').forEach(el=>{{el.addEventListener('click',e=>{{e.stopPropagation();toggleDetail(el.dataset.i,el)}})}})
}}

function renderTimeline(){{
  const list=getFiltered();
  const start=(currentPage-1)*PAGE_SIZE;
  const pageData=list.slice(start,start+PAGE_SIZE);
  const tbody=document.getElementById('tbody');
  tbody.innerHTML=pageData.map(renderEventRow).join('');
  tbody.querySelectorAll('.expand-toggle').forEach(el=>{{el.addEventListener('click',()=>toggleDetail(el.dataset.i,el))}});
  renderPagination(list.length);
}}

function toggleDetail(id, toggle){{const row=document.getElementById('detail-'+id);if(row){{row.classList.toggle('show');toggle.classList.toggle('open');toggle.textContent=toggle.classList.contains('open')?'▾':'▸';}}}}

function focusEvent(id){{
  viewMode='timeline';
  document.getElementById('view-timeline').classList.add('active');
  document.getElementById('view-grouped').classList.remove('active');
  const list=getFiltered();
  const index=list.findIndex(e=>e.id===id);
  if(index>=0)currentPage=Math.floor(index/PAGE_SIZE)+1;
  render();
  const row=document.querySelector(`tr[data-event-id="${{id}}"]`);
  if(row){{
    const toggle=row.querySelector('.expand-toggle');
    if(toggle&&!toggle.classList.contains('open'))toggleDetail(id,toggle);
    row.scrollIntoView({{behavior:'smooth',block:'center'}});
    row.style.outline='2px solid var(--accent)';
    setTimeout(()=>{{row.style.outline='';}},1400);
  }}
}}

function drawGrid(width,height,rows,cols,minTs,maxTs,maxY,yFmt){{
  let out='';
  for(let i=0;i<=rows;i++){{
    const y=(height/rows)*i;out+=`<line x1="0" y1="${{y}}" x2="${{width}}" y2="${{y}}" stroke="rgba(255,255,255,.08)" stroke-width="1"/>`;
    if(maxY!==undefined && i<rows){{const val=maxY-(i/rows)*maxY;out+=`<text x="4" y="${{y+12}}" fill="var(--text-dim)" font-size="10" font-family="var(--mono)">${{yFmt?yFmt(val):val.toFixed(1)}}</text>`;}}
  }}
  for(let i=0;i<=cols;i++){{
    const x=(width/cols)*i;out+=`<line x1="${{x}}" y1="0" x2="${{x}}" y2="${{height}}" stroke="rgba(255,255,255,.04)" stroke-width="1"/>`;
    if(minTs!==undefined && maxTs!==undefined && i>0 && i<cols){{const ts=minTs+(i/cols)*(maxTs-minTs);out+=`<text x="${{x+4}}" y="${{height-4}}" fill="var(--text-dim)" font-size="10" font-family="var(--mono)">${{shortTime(new Date(ts).toISOString())}}</text>`;}}
  }}
  return out;
}}

function attachBrush(svg,minTs,maxTs,width,pad){{
  let isDragging=false,startX=0,currentX=0;
  let brush=document.createElementNS("http://www.w3.org/2000/svg","rect");
  brush.setAttribute("fill","rgba(99,102,241,0.2)");brush.setAttribute("height","100%");brush.setAttribute("y","0");brush.style.display="none";
  svg.appendChild(brush);
  const oldDown=svg.onmousedown,oldMove=svg.onmousemove,oldUp=svg.onmouseup,oldLeave=svg.onmouseleave;
  svg.onmousedown=(e)=>{{if(oldDown)oldDown(e);isDragging=true;const r=svg.getBoundingClientRect();startX=e.clientX-r.left;brush.setAttribute("x",startX);brush.setAttribute("width","0");brush.style.display="block";}};
  svg.onmousemove=(e)=>{{if(oldMove)oldMove(e);if(!isDragging)return;const r=svg.getBoundingClientRect();currentX=e.clientX-r.left;brush.setAttribute("x",Math.min(startX,currentX));brush.setAttribute("width",Math.abs(currentX-startX));}};
  const finalize=(e)=>{{
    if(!isDragging)return;isDragging=false;
    const r=svg.getBoundingClientRect();currentX=e.clientX-r.left;
    if(Math.abs(currentX-startX)>10){{
      const innerW=width-pad*2;
      const t1=minTs+Math.max(0,Math.min(startX,currentX)-pad)/innerW*(maxTs-minTs);
      const t2=minTs+Math.min(innerW,Math.max(startX,currentX)-pad)/innerW*(maxTs-minTs);
      timeRangeFilter={{min:t1,max:t2}};currentPage=1;
      document.getElementById('clear-brush').style.display='inline-block';
      render();
    }}else{{brush.style.display="none";}}
  }};
  svg.onmouseup=(e)=>{{if(oldUp)oldUp(e);finalize(e);}};
  svg.onmouseleave=(e)=>{{if(oldLeave)oldLeave(e);if(isDragging)finalize(e);}};
}}

function xForTs(ts,minTs,maxTs,width){{
  if(maxTs<=minTs)return width/2;
  return ((ts-minTs)/(maxTs-minTs))*width;
}}

function linePathByTime(points,minTs,maxTs,width,height,maxY,getter){{
  if(!points.length)return'';
  return points.map((point,index)=>{{const x=xForTs(point.ts,minTs,maxTs,width);const y=height-((getter(point)/maxY)*height);return`${{index?'L':'M'}}${{x.toFixed(2)}},${{y.toFixed(2)}}`;}}).join(' ');
}}

function buildTimelineSeries(){{
  const list=getFiltered().slice().sort((a,b)=>parseTs(a.timestamp)-parseTs(b.timestamp));
  return list.map((b)=>{{
    const sys=b.sys||{{}};
    const per=(sys.cpu_per_core||[]).map(v=>Number(v||0));
    return {{
      id:b.id,
      ts:parseTs(b.timestamp),
      label:shortTime(b.timestamp),
      avgCpu:Number(sys.cpu_percent||0),
      perCore:per,
      mem:Number(sys.memory_mb||0),
      dur:typeof b.total_duration==='number'?b.total_duration:0,
      evt:baseEventType(b),
      hint:b.hint||'',
      location:b.location||'Unknown',
    }};
  }});
}}

function setupCpuChart(series){{
  const svg=document.getElementById('cpu-chart');const tip=document.getElementById('cpu-tip');const meta=document.getElementById('cpu-meta');
  const width=900,height=300,pad=28;const innerW=width-pad*2,innerH=height-pad*2;
  if(!series.length){{svg.innerHTML='';meta.textContent='No CPU data available for the current filters.';return;}}
  const minTs=Math.min(...series.map(s=>s.ts));const maxTs=Math.max(...series.map(s=>s.ts));
  const corePeak=series.reduce((max,s)=>Math.max(max,...s.perCore,0),0);
  const maxCpu=Math.max(100, ...series.map(s=>s.avgCpu), corePeak);
  let coreLines='';
  if(chartState.cpuMode==='cores'){{
    const coreCount=Math.max(...series.map(s=>s.perCore.length),0);
    for(let core=0;core<coreCount;core++){{const pts=series.map(s=>({{ts:s.ts,val:Number(s.perCore[core]||0)}}));coreLines+=`<path d="${{linePathByTime(pts,minTs,maxTs,innerW,innerH,maxCpu,p=>p.val)}}" transform="translate(${{pad}},${{pad}})" fill="none" stroke="rgba(129,140,248,.20)" stroke-width="1.2"/>`;}}
  }}
  const avgPath=linePathByTime(series,minTs,maxTs,innerW,innerH,maxCpu,s=>s.avgCpu);
  svg.innerHTML=`${{drawGrid(innerW,innerH,4,6,minTs,maxTs,maxCpu,v=>v.toFixed(0)+'%')}}<g transform="translate(${{pad}},${{pad}})">${{coreLines}}<path d="${{avgPath}}" fill="none" stroke="var(--cyan)" stroke-width="2.6"/></g>`;
  meta.innerHTML=`<span>Start: <strong>${{series[0].label}}</strong></span><span>End: <strong>${{series[series.length-1].label}}</strong></span><span>Events: <strong>${{series.length}}</strong></span><span>Core count: <strong>${{STATS.cpu_core_count||0}}</strong></span>`;
  svg.onmousedown=null;svg.onmouseup=null;svg.onmousemove=null;svg.onmouseleave=null;
  svg.onmousemove=(e)=>{{
    const rect=svg.getBoundingClientRect();
    const rawX=((e.clientX-rect.left)/rect.width)*width-pad;
    const targetTs=minTs+Math.max(0,Math.min(innerW,rawX))/innerW*(maxTs-minTs||1);
    let point=series[0];
    for(const candidate of series){{if(Math.abs(candidate.ts-targetTs)<Math.abs(point.ts-targetTs))point=candidate;}}
    tip.innerHTML=`<strong>${{point.label}}</strong>Avg CPU: ${{point.avgCpu.toFixed(1)}}%<br>Memory: ${{point.mem.toFixed(1)}} MB<br>${{escHtml(point.location)}}`;
    tip.style.left=`${{e.clientX-rect.left}}px`;tip.style.top=`${{e.clientY-rect.top-8}}px`;tip.classList.add('show');
  }};
  svg.onmouseleave=()=>tip.classList.remove('show');
  attachBrush(svg,minTs,maxTs,width,pad);
}}

function setupDurationChart(series){{
  const svg=document.getElementById('duration-chart');const tip=document.getElementById('duration-tip');const meta=document.getElementById('duration-meta');
  const width=900,height=300,pad=28;const innerW=width-pad*2,innerH=height-pad*2;
  const filtered=chartState.durationFilter==='all'?series:series.filter(s=>s.evt===chartState.durationFilter);
  if(!filtered.length){{svg.innerHTML='';meta.textContent='No duration data available for the current filters.';return;}}
  const minTs=Math.min(...filtered.map(s=>s.ts));const maxTs=Math.max(...filtered.map(s=>s.ts));
  const maxDur=Math.max(...filtered.map(s=>s.dur),0.01);
  const line=linePathByTime(filtered,minTs,maxTs,innerW,innerH,maxDur,s=>s.dur);
  let points='';
  filtered.forEach(point=>{{const x=xForTs(point.ts,minTs,maxTs,innerW);const y=innerH-((point.dur/maxDur)*innerH);const color=point.evt==='async'?'var(--cyan)':point.evt==='crash'?'var(--red)':'var(--orange)';points+=`<circle cx="${{x+pad}}" cy="${{y+pad}}" r="4" fill="${{color}}" data-id="${{point.id}}" data-label="${{point.label}}" data-dur="${{point.dur.toFixed(4)}}s" data-hint="${{escHtml(point.hint)}}" data-location="${{escHtml(point.location)}}" />`; }});
  svg.innerHTML=`${{drawGrid(innerW,innerH,4,6,minTs,maxTs,maxDur,v=>v.toFixed(2)+'s')}}<g transform="translate(${{pad}},${{pad}})"><path d="${{line}}" fill="none" stroke="var(--accent2)" stroke-width="2.2"/></g>${{points}}`;
  const maxShown=Math.max(...filtered.map(s=>s.dur));const avgShown=filtered.reduce((sum,s)=>sum+s.dur,0)/filtered.length;
  meta.innerHTML=`<span>Start: <strong>${{filtered[0].label}}</strong></span><span>End: <strong>${{filtered[filtered.length-1].label}}</strong></span><span>Avg duration: <strong>${{avgShown.toFixed(4)}}s</strong></span><span>Max duration: <strong>${{maxShown.toFixed(4)}}s</strong></span>`;
  svg.onmousedown=null;svg.onmouseup=null;svg.onmousemove=null;svg.onmouseleave=null;
  svg.querySelectorAll('circle').forEach(node=>{{
    node.addEventListener('mouseenter',e=>{{tip.innerHTML=`<strong>${{node.dataset.label}}</strong>Duration: ${{node.dataset.dur}}<br>${{node.dataset.hint}}<br><span style="color:var(--text-dim)">${{node.dataset.location}}</span>`;const rect=svg.getBoundingClientRect();tip.style.left=`${{e.clientX-rect.left}}px`;tip.style.top=`${{e.clientY-rect.top-8}}px`;tip.classList.add('show');}});
    node.addEventListener('mouseleave',()=>tip.classList.remove('show'));
    node.addEventListener('click',()=>focusEvent(Number(node.dataset.id)));
  }});
  attachBrush(svg,minTs,maxTs,width,pad);
}}

function renderCharts(){{
  const series=buildTimelineSeries();
  setupCpuChart(series);
  setupDurationChart(series);
}}

function scrollCulpritPreviews(){{
  requestAnimationFrame(()=>{{
    document.querySelectorAll('.culprit-frame-cell').forEach(cell=>{{
      const culprit=cell.querySelector('.culprit-frame');
      if(culprit){{
        cell.scrollTop=Math.max(0,culprit.offsetTop-30);
      }}
    }});
  }});
}}

function renderCulpritSummary(){{
  const tbody=document.getElementById('culprit-summary-body');
  const badge=document.getElementById('culprit-summary-badge');
  if(!tbody)return;
  const list=getFiltered();
  if(!list.length){{
    tbody.innerHTML='<tr><td colspan="5" class="section-empty">No events match current filters.</td></tr>';
    if(badge)badge.textContent='0';
    return;
  }}
  const rows=buildCulpritRows(list);
  if(badge)badge.textContent=rows.length+' unique · '+list.length+' events';

  tbody.innerHTML=rows.map(row=>{{
    const b=row.sample;
    const evt=baseEventType(b);
    const tCls=evt==='crash'?'tag-crash':evt==='async'?'tag-async':'tag-block';
    const tLbl=evt==='crash'?'CRASH':evt==='async'?'ASYNC':'BLOCK';
    const hint=escHtml(b.hint||'—');
    const loc=escHtml(b.location||'—');
    const blk=escHtml(b.blocking_location||'—');
    const frameHtml=renderSummaryStack(b.stack);
    return`<tr>
      <td style="text-align:center;font-weight:800;color:var(--accent2)">${{row.count}}</td>
      <td><span class="tag ${{tCls}}">${{tLbl}}</span></td>
      <td>
        <div style="font-family:var(--mono);font-size:12px;color:var(--cyan);margin-bottom:4px">${{loc}}</div>
        <div style="font-size:11px;color:var(--text-dim)">${{hint}}</div>
        <div style="font-family:var(--mono);font-size:10px;color:var(--text-dim);margin-top:2px;opacity:.7">Block: ${{blk}}</div>
      </td>
      <td><div class="culprit-frame-cell">${{frameHtml}}</div></td>
      <td style="text-align:center"><button class="action-btn" onclick="copyStackTrace(${{b.id}}, this)">Copy</button></td>
    </tr>`;
  }}).join('');
  scrollCulpritPreviews();
}}

function render(){{
  renderHeader();
  renderCulpritSummary();
  if(viewMode==='grouped')renderGrouped();else renderTimeline();
  renderCharts();
}}

window.sortBy=function(key){{if(currentSort===key)currentDir*=-1;else{{currentSort=key;currentDir=-1}}currentPage=1;render();}};

document.querySelectorAll('.col-filter').forEach(inp=>{{inp.addEventListener('input',e=>{{colFilters[e.target.dataset.col]=e.target.value;clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>{{currentPage=1;render()}},250)}});}});
document.getElementById('search').addEventListener('input',e=>{{searchTerm=e.target.value;clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>{{currentPage=1;render()}},250)}});
document.getElementById('sort-select').addEventListener('change',e=>{{currentSort=e.target.value;currentDir=-1;currentPage=1;render();}});
document.getElementById('exclude-toggle').addEventListener('click',()=>{{document.getElementById('exclude-panel').classList.toggle('open');}});
document.getElementById('exclude-clear').addEventListener('click',()=>{{
  excludeLocations.clear();
  document.querySelectorAll('[data-location-checkbox]').forEach(node=>{{node.checked=false;}});
  updateExcludeSummary();
  currentPage=1;
  render();
}});
function downloadBlob(content, type, fname){{
  const blob = new Blob([content], {{type}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = fname; a.click();
  URL.revokeObjectURL(url);
}}
document.getElementById('export-json').addEventListener('click',()=>{{
  downloadBlob(JSON.stringify(getFiltered(),null,2),'application/json','loopsentry_filtered.json');
  document.getElementById('export-panel').classList.remove('open');
}});
document.getElementById('export-csv').addEventListener('click',()=>{{
  const list = getFiltered();
  if(!list.length)return;
  const cols = ["id","type","timestamp","pid","total_duration","hint","trigger","location","blocking_location","task_name","coro","resolved","cpu_percent","memory_mb","thread_count","stack","user_frames","locals","exception"];
  const rows = [cols.join(',')];
  list.forEach(b => {{
    const sys = b.sys || {{}};
    const vals = cols.map(col => {{
      let v;
      if (col === 'cpu_percent') v = sys.cpu_percent ?? 0;
      else if (col === 'memory_mb') v = sys.memory_mb ?? 0;
      else if (col === 'thread_count') v = sys.thread_count ?? '';
      else v = b[col];
      if (typeof v === 'object' && v !== null) v = JSON.stringify(v);
      const str = String(v ?? '').replace(/"/g, '""').replace(/\\n/g, ' \\n ');
      return `"${{str}}"`;
    }});
    rows.push(vals.join(','));
  }});
  downloadBlob(rows.join('\\n'), 'text/csv', 'loopsentry_full_export.csv');
  document.getElementById('export-panel').classList.remove('open');
}});
document.getElementById('export-toggle').addEventListener('click',()=>{{document.getElementById('export-panel').classList.toggle('open');}});
document.getElementById('clear-brush').addEventListener('click',()=>{{
  timeRangeFilter=null;document.getElementById('clear-brush').style.display='none';
  currentPage=1;render();
}});
document.addEventListener('click',e=>{{
  const exclude=document.getElementById('exclude-panel');
  const exportP=document.getElementById('export-panel');
  const wrapper=e.target.closest('.filter-pop');
  if(!wrapper){{exclude.classList.remove('open');if(exportP)exportP.classList.remove('open');}}
}});
['all','block','async'].forEach(f=>{{document.getElementById('filter-'+f).addEventListener('click',()=>{{currentFilter=f;document.querySelectorAll('#filter-all,#filter-block,#filter-async').forEach(b=>b.classList.remove('active'));document.getElementById('filter-'+f).classList.add('active');currentPage=1;render();}});}});
document.getElementById('view-grouped').addEventListener('click',()=>{{viewMode='grouped';document.getElementById('view-grouped').classList.add('active');document.getElementById('view-timeline').classList.remove('active');currentPage=1;render();}});
document.getElementById('view-timeline').addEventListener('click',()=>{{viewMode='timeline';document.getElementById('view-timeline').classList.add('active');document.getElementById('view-grouped').classList.remove('active');currentPage=1;render();}});
document.getElementById('cpu-mode-avg').addEventListener('click',()=>{{chartState.cpuMode='avg';document.getElementById('cpu-mode-avg').classList.add('active');document.getElementById('cpu-mode-cores').classList.remove('active');renderCharts();}});
document.getElementById('cpu-mode-cores').addEventListener('click',()=>{{chartState.cpuMode='cores';document.getElementById('cpu-mode-cores').classList.add('active');document.getElementById('cpu-mode-avg').classList.remove('active');renderCharts();}});
document.getElementById('focus-all').addEventListener('click',()=>{{chartState.durationFilter='all';document.getElementById('focus-all').classList.add('active');document.getElementById('focus-block').classList.remove('active');document.getElementById('focus-async').classList.remove('active');renderCharts();}});
document.getElementById('focus-block').addEventListener('click',()=>{{chartState.durationFilter='block';document.getElementById('focus-block').classList.add('active');document.getElementById('focus-all').classList.remove('active');document.getElementById('focus-async').classList.remove('active');renderCharts();}});
document.getElementById('focus-async').addEventListener('click',()=>{{chartState.durationFilter='async';document.getElementById('focus-async').classList.add('active');document.getElementById('focus-all').classList.remove('active');document.getElementById('focus-block').classList.remove('active');renderCharts();}});

const _culpritDetails=document.getElementById('culprit-details');
if(_culpritDetails){{_culpritDetails.addEventListener('toggle',()=>{{
  const lbl=_culpritDetails.querySelector('.culprit-cta-label');
  if(lbl)lbl.textContent=_culpritDetails.open?'Collapse':'Expand';
}});}}
initLocationSelectors();
render();
</script>
</body>
</html>"""