"""Standalone HTML report generator for LoopSentry."""
import json
import re
from pathlib import Path


def _escape(s):
    """Escape HTML entities."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _parse_location(trigger_str):
    if not trigger_str:
        return "Unknown"
    match = re.search(r'File "(.*?)", line (\d+)', trigger_str)
    if match:
        return f"{Path(match.group(1)).name}:{match.group(2)}"
    async_match = re.search(r'^(.*?) \(Task-', trigger_str)
    if async_match:
        return async_match.group(1)
    return trigger_str[:40]


def generate_html(blocks, stats):
    """Generate a fully standalone HTML report string."""

    # Prepare JSON data for embedding
    safe_blocks = []
    for b in blocks:
        sb = {
            "type": b.get("type", "unknown"),
            "timestamp": b.get("timestamp", ""),
            "pid": b.get("pid", 0),
            "total_duration": b.get("total_duration", 0),
            "hint": b.get("hint", ""),
            "trigger": b.get("trigger", ""),
            "location": _parse_location(b.get("trigger", "")),
            "resolved": b.get("resolved", True),
            "task_name": b.get("task_name", ""),
            "coro": b.get("coro", ""),
            "sys": b.get("sys", {}),
            "stack": b.get("stack", []),
            "locals": b.get("locals", []),
            "exception": b.get("exception"),
        }
        safe_blocks.append(sb)

    blocks_json = json.dumps(safe_blocks)
    stats_json = json.dumps(stats)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LoopSentry Report</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0b0e17;--surface:#131829;--surface2:#1a2035;--border:#252d48;
  --text:#e2e8f0;--text-dim:#64748b;--accent:#6366f1;--accent2:#818cf8;
  --red:#ef4444;--orange:#f97316;--yellow:#eab308;--green:#22c55e;--cyan:#06b6d4;
  --pink:#ec4899;
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',sans-serif;
  --mono:'SF Mono','Fira Code',Consolas,monospace;
}}
body{{font-family:var(--font);background:var(--bg);color:var(--text);line-height:1.6;padding:0}}
a{{color:var(--accent2);text-decoration:none}}

/* ── Layout ─────────────────────── */
.wrap{{max-width:1400px;margin:0 auto;padding:24px 32px 64px}}

/* ── Header ─────────────────────── */
.header{{display:flex;align-items:center;justify-content:space-between;padding:24px 0;border-bottom:1px solid var(--border);margin-bottom:32px}}
.header h1{{font-size:28px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header .sub{{color:var(--text-dim);font-size:13px;margin-top:2px}}
.badge{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;background:var(--accent);color:#fff}}

/* ── Stat Cards ─────────────────── */
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:32px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;text-align:center;transition:transform .15s,box-shadow .15s}}
.card:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3)}}
.card .val{{font-size:32px;font-weight:800;margin-bottom:4px}}
.card .lbl{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text-dim)}}
.card.red .val{{color:var(--red)}}.card.yellow .val{{color:var(--yellow)}}
.card.cyan .val{{color:var(--cyan)}}.card.pink .val{{color:var(--pink)}}
.card.green .val{{color:var(--green)}}.card.orange .val{{color:var(--orange)}}

/* ── Controls ───────────────────── */
.controls{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;align-items:center}}
.search{{flex:1;min-width:200px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 16px;color:var(--text);font-size:14px;outline:none;transition:border .2s}}
.search:focus{{border-color:var(--accent)}}
.btn{{padding:8px 16px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:13px;cursor:pointer;transition:all .15s;font-weight:600}}
.btn:hover{{background:var(--surface2);border-color:var(--accent)}}
.btn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
select.btn{{appearance:none;padding-right:28px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2364748b' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center}}

/* ── Table ──────────────────────── */
.tbl-wrap{{overflow-x:auto;border-radius:12px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:var(--surface);padding:12px 16px;text-align:left;font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:.5px;color:var(--text-dim);cursor:pointer;user-select:none;border-bottom:2px solid var(--border);position:sticky;top:0}}
th:hover{{color:var(--accent2)}}
th .arrow{{margin-left:4px;opacity:.5}}
td{{padding:10px 16px;border-bottom:1px solid var(--border);vertical-align:top}}
tr{{transition:background .1s}}
tr:hover{{background:var(--surface2)}}
tr.async-row{{border-left:3px solid var(--cyan)}}
tr.block-row{{border-left:3px solid var(--orange)}}
tr.crash-row{{border-left:3px solid var(--red)}}

.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.tag-block{{background:rgba(249,115,22,.15);color:var(--orange)}}
.tag-async{{background:rgba(6,182,212,.15);color:var(--cyan)}}
.tag-crash{{background:rgba(239,68,68,.15);color:var(--red)}}
.dur{{font-family:var(--mono);font-weight:600}}
.dur-high{{color:var(--red)}}.dur-med{{color:var(--orange)}}.dur-low{{color:var(--green)}}

/* ── Expandable Row ─────────────── */
.expand-toggle{{cursor:pointer;color:var(--accent2);font-size:18px;line-height:1;transition:transform .2s;display:inline-block}}
.expand-toggle.open{{transform:rotate(90deg)}}
.detail-row{{display:none}}
.detail-row.show{{display:table-row}}
.detail-cell{{padding:0 16px 16px;background:var(--surface)}}
.detail-inner{{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 0}}
@media(max-width:800px){{.detail-inner{{grid-template-columns:1fr}}}}
.detail-section{{background:var(--bg);border-radius:8px;padding:16px;border:1px solid var(--border)}}
.detail-section h4{{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--accent2);margin-bottom:8px}}
pre.stack{{font-family:var(--mono);font-size:12px;line-height:1.7;white-space:pre-wrap;word-break:break-all;color:var(--text-dim);max-height:400px;overflow-y:auto}}
pre.stack .culprit{{color:var(--red);font-weight:700}}
pre.stack .user-code{{color:var(--cyan)}}
.var-list{{font-family:var(--mono);font-size:12px;line-height:1.8}}
.var-name{{color:var(--cyan)}}.var-val{{color:var(--text-dim)}}
.meta-grid{{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px}}
.meta-grid dt{{color:var(--text-dim);font-weight:600}}.meta-grid dd{{color:var(--text)}}

/* ── Timeline Chart ─────────────── */
.timeline{{margin-bottom:32px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px}}
.timeline h3{{font-size:14px;font-weight:700;margin-bottom:12px;color:var(--text-dim)}}
.tl-bars{{display:flex;align-items:flex-end;gap:2px;height:120px}}
.tl-bar{{flex:1;min-width:4px;border-radius:3px 3px 0 0;transition:opacity .15s;position:relative}}
.tl-bar:hover{{opacity:.8}}
.tl-bar.block{{background:linear-gradient(to top,var(--orange),var(--yellow))}}.tl-bar.async{{background:linear-gradient(to top,var(--cyan),var(--accent2))}}
.tl-bar.crash{{background:var(--red)}}
.tl-bar .tip{{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:#000;color:#fff;padding:6px 10px;border-radius:6px;font-size:11px;white-space:nowrap;z-index:10}}
.tl-bar:hover .tip{{display:block}}

/* ── Footer ─────────────────────── */
.footer{{text-align:center;padding:32px 0;color:var(--text-dim);font-size:12px;border-top:1px solid var(--border);margin-top:48px}}
</style>
</head>
<body>
<div class="wrap" id="app">
  <div class="header">
    <div><h1>🛡 LoopSentry Report</h1><div class="sub">Asyncio Event Loop Performance Analysis</div></div>
    <div class="badge" id="gen-time"></div>
  </div>

  <div class="cards" id="cards"></div>
  <div class="timeline" id="timeline-section"><h3>Event Timeline</h3><div class="tl-bars" id="timeline"></div></div>

  <div class="controls">
    <input class="search" id="search" placeholder="Search by location, hint, coroutine..." autocomplete="off">
    <select class="btn" id="sort-select">
      <option value="time">Sort: Time</option><option value="duration">Sort: Duration</option>
      <option value="cpu">Sort: CPU</option><option value="memory">Sort: Memory</option><option value="type">Sort: Type</option>
    </select>
    <button class="btn" id="filter-all">All</button>
    <button class="btn" id="filter-block">Blocks</button>
    <button class="btn" id="filter-async">Async</button>
  </div>

  <div class="tbl-wrap"><table><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>
  <div class="footer">Generated by <strong>LoopSentry</strong> — Asyncio Event Loop Monitor</div>
</div>

<script>
const DATA={blocks_json};
const STATS={stats_json};

document.getElementById('gen-time').textContent=new Date().toLocaleString();

// ── Stats Cards ──
(function(){{
  const c=document.getElementById('cards');
  const cards=[
    {{v:STATS.count,l:'Blocking Events',cls:'orange'}},
    {{v:STATS.async_slow,l:'Slow Async Tasks',cls:'cyan'}},
    {{v:STATS.total_time.toFixed(2)+'s',l:'Total Time Lost',cls:'yellow'}},
    {{v:STATS.crashes,l:'Crashes',cls:'red'}},
    {{v:STATS.max_cpu.toFixed(1)+'%',l:'Peak CPU',cls:'pink'}},
    {{v:STATS.max_mem.toFixed(1)+'MB',l:'Peak Memory',cls:'green'}},
  ];
  cards.forEach(d=>{{c.innerHTML+=`<div class="card ${{d.cls}}"><div class="val">${{d.v}}</div><div class="lbl">${{d.l}}</div></div>`}});
}})();

// ── Timeline ──
(function(){{
  const tl=document.getElementById('timeline');
  const maxDur=Math.max(...DATA.map(b=>typeof b.total_duration==='number'?b.total_duration:0),0.01);
  DATA.forEach((b,i)=>{{
    const dur=typeof b.total_duration==='number'?b.total_duration:0;
    const pct=Math.max((dur/maxDur)*100,2);
    const cls=b.total_duration==='CRASH'?'crash':b.type==='async_bottleneck'?'async':'block';
    const tip=`${{b.timestamp.split('T')[1]?.slice(0,8)||''}} — ${{typeof b.total_duration==='number'?b.total_duration.toFixed(4)+'s':b.total_duration}} — ${{b.hint}}`;
    tl.innerHTML+=`<div class="tl-bar ${{cls}}" style="height:${{pct}}%" data-idx="${{i}}"><div class="tip">${{tip}}</div></div>`;
  }});
}})();

// ── Table ──
let currentSort='time',currentDir=-1,currentFilter='all',searchTerm='';

function escHtml(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}

function durClass(d){{if(typeof d!=='number')return'';return d>2?'dur-high':d>0.5?'dur-med':'dur-low'}}

function renderStack(stack){{
  if(!stack||!stack.length)return'<em>No stack trace</em>';
  let culprit=-1;const lines=stack.map((f,i)=>{{
    const isLib=/site-packages|dist-packages|lib[/]python|asyncio[/]/.test(f);
    if(!isLib)culprit=i;
    return{{text:f.replace(/\\n$/,''),isLib}};
  }});
  if(culprit===-1&&lines.length)culprit=lines.length-1;
  return lines.map((l,i)=>{{
    const cls=i===culprit?'culprit':l.isLib?'':'user-code';
    const prefix=i===culprit?'>>> ':'';
    return`<span class="${{cls}}">${{prefix}}${{escHtml(l.text)}}</span>`;
  }}).join('\\n');
}}

function renderLocals(locals){{
  if(!locals||!locals.length)return'';
  return locals.map(fr=>{{
    const hdr=fr.file?`${{fr.func}} (${{fr.file}}:${{fr.line}})`:fr.func;
    const vars=fr.vars?Object.entries(fr.vars).map(([k,v])=>`  <span class="var-name">${{escHtml(k)}}</span> = <span class="var-val">${{escHtml(v)}}</span>`).join('\\n'):'';
    return`<strong>${{escHtml(hdr)}}</strong>\\n${{vars}}`;
  }}).join('\\n\\n');
}}

function getFiltered(){{
  let list=[...DATA];
  if(currentFilter==='block')list=list.filter(b=>b.type!=='async_bottleneck');
  if(currentFilter==='async')list=list.filter(b=>b.type==='async_bottleneck');
  if(searchTerm){{
    const q=searchTerm.toLowerCase();
    list=list.filter(b=>{{
      const hay=(b.hint+b.location+b.coro+b.task_name+(b.stack||[]).join('')).toLowerCase();
      return hay.includes(q);
    }});
  }}
  const key={{time:(a)=>a.timestamp,duration:(a)=>typeof a.total_duration==='number'?a.total_duration:-1,
    cpu:(a)=>(a.sys?.cpu_percent||0),memory:(a)=>(a.sys?.memory_mb||0),type:(a)=>a.type}}[currentSort]||(a=>a.timestamp);
  list.sort((a,b)=>{{const va=key(a),vb=key(b);return va<vb?currentDir:va>vb?-currentDir:0}});
  return list;
}}

function render(){{
  const list=getFiltered();
  const thead=document.getElementById('thead');
  const cols=[['#',''],['Type','type'],['Time','time'],['Duration','duration'],['CPU%','cpu'],['Mem','memory'],['Hint',''],['Location','']];
  thead.innerHTML='<tr>'+cols.map(([lbl,key])=>{{
    const arrow=key===currentSort?(currentDir===-1?'▼':'▲'):'';
    return`<th${{key?` onclick="sortBy('${{key}}')"`:''}}>${{lbl}}<span class="arrow">${{arrow}}</span></th>`;
  }}).join('')+'</tr>';
  const tbody=document.getElementById('tbody');
  let html='';
  list.forEach((b,i)=>{{
    const dur=b.total_duration;const durFmt=typeof dur==='number'?dur.toFixed(4)+'s':String(dur);
    const cls=dur==='CRASH'?'crash-row':b.type==='async_bottleneck'?'async-row':'block-row';
    const tagCls=dur==='CRASH'?'tag-crash':b.type==='async_bottleneck'?'tag-async':'tag-block';
    const tagLbl=dur==='CRASH'?'CRASH':b.type==='async_bottleneck'?'ASYNC':'BLOCK';
    const sys=b.sys||{{}};const gc=sys.gc_counts||[0,0,0];
    html+=`<tr class="${{cls}}">
      <td><span class="expand-toggle" data-i="${{i}}">▸</span> ${{i+1}}</td>
      <td><span class="tag ${{tagCls}}">${{tagLbl}}</span></td>
      <td style="font-family:var(--mono);font-size:12px">${{(b.timestamp.split('T')[1]||'').slice(0,8)}}</td>
      <td><span class="dur ${{durClass(dur)}}">${{durFmt}}</span></td>
      <td>${{(sys.cpu_percent||0).toFixed(0)}}%</td>
      <td>${{(sys.memory_mb||0).toFixed(0)}}MB</td>
      <td>${{escHtml(b.hint)}}</td>
      <td style="font-family:var(--mono);font-size:12px">${{escHtml(b.location)}}</td>
    </tr>`;
    // detail row
    const excHtml=b.exception?`<div class="detail-section"><h4>Exception</h4><pre class="stack"><span class="culprit">${{escHtml(b.exception.type)}}: ${{escHtml(b.exception.message)}}</span>\\n${{(b.exception.traceback||[]).map(l=>escHtml(l)).join('')}}</pre></div>`:'';
    const localsHtml=b.locals&&b.locals.length?`<div class="detail-section"><h4>Captured Variables</h4><pre class="var-list">${{renderLocals(b.locals)}}</pre></div>`:'';
    html+=`<tr class="detail-row" id="detail-${{i}}"><td colspan="8" class="detail-cell"><div class="detail-inner">
      <div><div class="detail-section"><h4>Metadata</h4><dl class="meta-grid">
        <dt>Timestamp</dt><dd>${{b.timestamp}}</dd>
        <dt>PID</dt><dd>${{b.pid}}</dd>
        ${{b.task_name?`<dt>Task</dt><dd>${{escHtml(b.task_name)}}</dd>`:''}}
        ${{b.coro?`<dt>Coroutine</dt><dd>${{escHtml(b.coro)}}</dd>`:''}}
        <dt>CPU</dt><dd>${{(sys.cpu_percent||0)}}%</dd>
        <dt>Memory</dt><dd>${{(sys.memory_mb||0).toFixed(1)}} MB</dd>
        <dt>Threads</dt><dd>${{sys.thread_count||'?'}}</dd>
        <dt>GC</dt><dd>Gen0=${{gc[0]||0}} Gen1=${{gc[1]||0}} Gen2=${{gc[2]||0}}</dd>
      </dl></div>${{excHtml}}</div>
      <div><div class="detail-section" style="grid-column:1/-1"><h4>Stack Trace</h4><pre class="stack">${{renderStack(b.stack)}}</pre></div>${{localsHtml}}</div>
    </div></td></tr>`;
  }});
  tbody.innerHTML=html;
  // toggle listeners
  tbody.querySelectorAll('.expand-toggle').forEach(el=>{{
    el.addEventListener('click',()=>{{
      const row=document.getElementById('detail-'+el.dataset.i);
      if(row){{row.classList.toggle('show');el.classList.toggle('open');el.textContent=el.classList.contains('open')?'▾':'▸'}}
    }});
  }});
}}

window.sortBy=function(key){{
  if(currentSort===key)currentDir*=-1;else{{currentSort=key;currentDir=-1}};render();
}};

document.getElementById('search').addEventListener('input',e=>{{searchTerm=e.target.value;render()}});
['all','block','async'].forEach(f=>{{
  document.getElementById('filter-'+f).addEventListener('click',()=>{{
    currentFilter=f;
    document.querySelectorAll('.controls .btn').forEach(b=>b.classList.remove('active'));
    document.getElementById('filter-'+f).classList.add('active');
    render();
  }});
}});
document.getElementById('sort-select').addEventListener('change',e=>{{currentSort=e.target.value;currentDir=-1;render()}});
document.getElementById('filter-all').classList.add('active');

render();
</script>
</body>
</html>'''
