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

    safe_blocks = []
    for i, b in enumerate(blocks):
        sb = {
            "id": i,
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

.wrap{{width:100%;padding:24px 32px 64px}}

.header{{display:flex;align-items:center;justify-content:space-between;padding:24px 0;border-bottom:1px solid var(--border);margin-bottom:32px}}
.header h1{{font-size:28px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header .sub{{color:var(--text-dim);font-size:13px;margin-top:2px}}
.badge{{display:inline-block;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;background:var(--accent);color:#fff}}

.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:32px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;text-align:center;transition:transform .15s,box-shadow .15s}}
.card:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3)}}
.card .val{{font-size:32px;font-weight:800;margin-bottom:4px}}
.card .lbl{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text-dim)}}
.card .hint{{font-size:10px;color:var(--text-dim);margin-top:6px;line-height:1.4;opacity:.7}}
.card.red .val{{color:var(--red)}}.card.yellow .val{{color:var(--yellow)}}
.card.cyan .val{{color:var(--cyan)}}.card.pink .val{{color:var(--pink)}}
.card.green .val{{color:var(--green)}}.card.orange .val{{color:var(--orange)}}

.controls{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;align-items:center}}
.search{{flex:1;min-width:200px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 16px;color:var(--text);font-size:14px;outline:none;transition:border .2s}}
.search:focus{{border-color:var(--accent)}}
.btn{{padding:8px 16px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:13px;cursor:pointer;transition:all .15s;font-weight:600}}
.btn:hover{{background:var(--surface2);border-color:var(--accent)}}
.btn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
.btn:disabled{{opacity:.4;cursor:not-allowed}}
select.btn{{appearance:none;padding-right:28px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2364748b' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center}}

.tbl-wrap{{border-radius:12px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:var(--surface);padding:12px 16px;text-align:left;font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:.5px;color:var(--text-dim);cursor:pointer;user-select:none;border-bottom:2px solid var(--border)}}
th:hover{{color:var(--accent2)}}
th .arrow{{margin-left:4px;opacity:.5}}
.filter-row th{{padding:4px 6px;background:var(--surface2);border-bottom:1px solid var(--border)}}
.col-filter{{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:5px 8px;color:var(--text);font-size:11px;font-family:var(--mono);outline:none;transition:border .2s}}
.col-filter:focus{{border-color:var(--accent)}}
.col-filter::placeholder{{color:var(--text-dim);opacity:.6}}
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
.tag-group{{background:rgba(99,102,241,.15);color:var(--accent2)}}
.dur{{font-family:var(--mono);font-weight:600}}
.dur-high{{color:var(--red)}}.dur-med{{color:var(--orange)}}.dur-low{{color:var(--green)}}
.grp-count{{font-family:var(--mono);font-weight:800;color:var(--accent2);font-size:16px}}

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

.pagination{{display:flex;align-items:center;justify-content:center;gap:12px;padding:16px 0}}
.page-info{{font-size:13px;color:var(--text-dim)}}

.footer{{text-align:center;padding:32px 0;color:var(--text-dim);font-size:12px;border-top:1px solid var(--border);margin-top:48px}}
</style>
</head>
<body>
<div class="wrap" id="app">
  <div class="header">
    <div><h1>\U0001f6e1 LoopSentry Report</h1><div class="sub">Asyncio Event Loop Performance Analysis</div></div>
    <div class="badge" id="gen-time"></div>
  </div>

  <div class="cards" id="cards"></div>

  <div class="controls">
    <input class="search" id="search" placeholder="Global search across all fields..." autocomplete="off">
    <select class="btn" id="sort-select">
      <option value="time">Sort: Time</option><option value="duration">Sort: Duration</option>
      <option value="cpu">Sort: CPU</option><option value="memory">Sort: Memory</option><option value="type">Sort: Type</option>
    </select>
    <button class="btn" id="filter-all">All</button>
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
  <div class="footer">Generated by <strong>LoopSentry</strong> &mdash; Asyncio Event Loop Monitor</div>
</div>

<script>
const DATA={blocks_json};
const STATS={stats_json};
const PAGE_SIZE=1000;

document.getElementById('gen-time').textContent=new Date().toLocaleString();

(function(){{
  const c=document.getElementById('cards');
  [
    {{v:STATS.count,l:'Blocking Events',cls:'orange',h:'Sync calls that blocked the event loop beyond the threshold'}},
    {{v:STATS.async_slow,l:'Slow Async Tasks',cls:'cyan',h:'Async tasks that took longer than the async threshold to complete'}},
    {{v:STATS.total_time.toFixed(2)+'s',l:'Block Time Lost',cls:'yellow',h:'Cumulative sum of all blocking durations. Does not account for concurrency — actual wall-clock impact may be lower'}},
    {{v:(STATS.async_total_time||0).toFixed(2)+'s',l:'Async Time',cls:'cyan',h:'Cumulative sum of slow async task durations. Concurrent tasks overlap — this is NOT wall-clock time'}},
    {{v:STATS.crashes,l:'Crashes',cls:'red',h:'Unresolved blocks where the event loop never recovered (possible crash or hang)'}},
    {{v:STATS.max_cpu.toFixed(1)+'%',l:'Peak CPU',cls:'pink',h:'Highest system-wide average CPU usage seen during any event (avg of all cores)'}},
    {{v:STATS.max_mem.toFixed(1)+'MB',l:'Peak Memory',cls:'green',h:'Highest process RSS memory usage seen during any event'}},
  ].forEach(d=>{{c.innerHTML+=`<div class="card ${{d.cls}}"><div class="val">${{d.v}}</div><div class="lbl">${{d.l}}</div><div class="hint">${{d.h}}</div></div>`}});
}})();

let currentSort='time',currentDir=-1,currentFilter='all',searchTerm='',currentPage=1;
let viewMode='grouped';
let colFilters={{type:'',time:'',duration:'',cpu:'',memory:'',hint:'',location:''}};
let debounceTimer=null;

function escHtml(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}
function durClass(d){{if(typeof d!=='number')return'';return d>2?'dur-high':d>0.5?'dur-med':'dur-low'}}
function parseNumericFilter(expr){{
  if(!expr)return null;expr=expr.trim();
  const m=expr.match(/^(>=|<=|!=|<>|>|<|=)\\s*(.+)$/);
  if(m){{const op=m[1]==='<>'?'!=':m[1];const val=parseFloat(m[2]);if(isNaN(val))return null;return{{op,val}};}}
  const val=parseFloat(expr);if(!isNaN(val))return{{op:'=',val}};return null;
}}
function matchNumeric(value,f){{
  if(!f)return true;
  switch(f.op){{case'>=':return value>=f.val;case'<=':return value<=f.val;case'>':return value>f.val;case'<':return value<f.val;case'!=':return value!==f.val;case'=':return value===f.val;default:return true;}}
}}
function matchString(value,f){{if(!f)return true;return String(value).toLowerCase().includes(f.toLowerCase())}}

function applyColumnFilters(b){{
  if(colFilters.type){{const t=b.type==='async_bottleneck'?'async':b.total_duration==='CRASH'?'crash':'block';if(!matchString(t,colFilters.type))return false;}}
  if(colFilters.time&&!matchString(b.timestamp,colFilters.time))return false;
  if(colFilters.duration){{const nf=parseNumericFilter(colFilters.duration);if(nf){{const dur=typeof b.total_duration==='number'?b.total_duration:-1;if(!matchNumeric(dur,nf))return false;}}else{{if(!matchString(typeof b.total_duration==='number'?b.total_duration.toFixed(4):String(b.total_duration),colFilters.duration))return false;}}}}
  if(colFilters.cpu){{const nf=parseNumericFilter(colFilters.cpu);if(nf){{if(!matchNumeric(b.sys?.cpu_percent||0,nf))return false;}}else{{if(!matchString(String(b.sys?.cpu_percent||0),colFilters.cpu))return false;}}}}
  if(colFilters.memory){{const nf=parseNumericFilter(colFilters.memory);if(nf){{if(!matchNumeric(b.sys?.memory_mb||0,nf))return false;}}else{{if(!matchString(String(b.sys?.memory_mb||0),colFilters.memory))return false;}}}}
  if(colFilters.hint&&!matchString(b.hint,colFilters.hint))return false;
  if(colFilters.location&&!matchString(b.location,colFilters.location))return false;
  return true;
}}

function renderStack(stack){{
  if(!stack||!stack.length)return'<em>No stack trace</em>';
  let culprit=-1;const lines=stack.map((f,i)=>{{const isLib=/site-packages|dist-packages|lib[/]python|asyncio[/]/.test(f);if(!isLib)culprit=i;return{{text:f.replace(/\\n$/,''),isLib}}}});
  if(culprit===-1&&lines.length)culprit=lines.length-1;
  return lines.map((l,i)=>{{const cls=i===culprit?'culprit':l.isLib?'':'user-code';return`<span class="${{cls}}">${{i===culprit?'>>> ':''}}${{escHtml(l.text)}}</span>`}}).join('\\n');
}}

function renderLocals(locals){{
  if(!locals||!locals.length)return'';
  return locals.map(fr=>{{const hdr=fr.file?`${{fr.func}} (${{fr.file}}:${{fr.line}})`:fr.func;const vars=fr.vars?Object.entries(fr.vars).map(([k,v])=>`  <span class="var-name">${{escHtml(k)}}</span> = <span class="var-val">${{escHtml(v)}}</span>`).join('\\n'):'';return`<strong>${{escHtml(hdr)}}</strong>\\n${{vars}}`}}).join('\\n\\n');
}}

function getFiltered(){{
  let list=[...DATA];
  if(currentFilter==='block')list=list.filter(b=>b.type!=='async_bottleneck');
  if(currentFilter==='async')list=list.filter(b=>b.type==='async_bottleneck');
  if(searchTerm){{const q=searchTerm.toLowerCase();list=list.filter(b=>{{const hay=(b.hint+b.location+b.coro+b.task_name+(b.stack||[]).join('')+b.timestamp+b.type).toLowerCase();return hay.includes(q)}})}}
  list=list.filter(applyColumnFilters);
  const key={{time:a=>a.timestamp,duration:a=>typeof a.total_duration==='number'?a.total_duration:-1,cpu:a=>(a.sys?.cpu_percent||0),memory:a=>(a.sys?.memory_mb||0),type:a=>a.type}}[currentSort]||(a=>a.timestamp);
  list.sort((a,b)=>{{const va=key(a),vb=key(b);return va<vb?currentDir:va>vb?-currentDir:0}});
  return list;
}}

function buildGroups(list){{
  const map=new Map();
  list.forEach(b=>{{
    const key=b.location||'Unknown';
    if(!map.has(key))map.set(key,{{location:key,hint:b.hint,events:[],totalDur:0,count:0}});
    const g=map.get(key);
    g.events.push(b);
    g.count++;
    if(typeof b.total_duration==='number')g.totalDur+=b.total_duration;
  }});
  const groups=[...map.values()];
  // Sort groups by total duration descending
  groups.sort((a,b)=>b.totalDur-a.totalDur);
  return groups;
}}

function renderDetailRow(b){{
  const sys=b.sys||{{}};const gc=sys.gc_counts||[0,0,0];
  const excHtml=b.exception?`<div class="detail-section"><h4>Exception</h4><pre class="stack"><span class="culprit">${{escHtml(b.exception.type)}}: ${{escHtml(b.exception.message)}}</span>\\n${{(b.exception.traceback||[]).map(l=>escHtml(l)).join('')}}</pre></div>`:'';
  const localsHtml=b.locals&&b.locals.length?`<div class="detail-section"><h4>Captured Variables</h4><pre class="var-list">${{renderLocals(b.locals)}}</pre></div>`:'';
  const perCore=(sys.cpu_per_core&&sys.cpu_per_core.length)?`<dt>Per Core</dt><dd style="font-family:var(--mono);font-size:11px">${{sys.cpu_per_core.map((c,i)=>{{const clr=c>80?'var(--red)':c>40?'var(--orange)':'var(--green)';return`<span style="display:inline-block;margin:1px 2px;padding:1px 4px;border-radius:3px;background:${{clr}}20;color:${{clr}}">${{i}}:${{c.toFixed(0)}}%</span>`}}).join('')}}</dd>`:'';
  return`<td colspan="8" class="detail-cell"><div class="detail-inner">
    <div><div class="detail-section"><h4>Metadata</h4><dl class="meta-grid">
      <dt>Event ID</dt><dd>#${{b.id}}</dd>
      <dt>Timestamp</dt><dd>${{b.timestamp}}</dd><dt>PID</dt><dd>${{b.pid}}</dd>
      ${{b.task_name?`<dt>Task</dt><dd>${{escHtml(b.task_name)}}</dd>`:''}}
      ${{b.coro?`<dt>Coroutine</dt><dd>${{escHtml(b.coro)}}</dd>`:''}}
      <dt>CPU</dt><dd>${{(sys.cpu_percent||0)}}%</dd>
      <dt>Memory</dt><dd>${{(sys.memory_mb||0).toFixed(1)}} MB</dd>
      <dt>Threads</dt><dd>${{sys.thread_count||'?'}}</dd>
      <dt>GC</dt><dd>Gen0=${{gc[0]||0}} Gen1=${{gc[1]||0}} Gen2=${{gc[2]||0}}</dd>
      ${{perCore}}
    </dl></div>${{excHtml}}</div>
    <div><div class="detail-section" style="grid-column:1/-1"><h4>Stack Trace</h4><pre class="stack">${{renderStack(b.stack)}}</pre></div>${{localsHtml}}</div>
  </div></td>`;
}}

function renderEventRow(b){{
  const dur=b.total_duration;const durFmt=typeof dur==='number'?dur.toFixed(4)+'s':String(dur);
  const cls=dur==='CRASH'?'crash-row':b.type==='async_bottleneck'?'async-row':'block-row';
  const tagCls=dur==='CRASH'?'tag-crash':b.type==='async_bottleneck'?'tag-async':'tag-block';
  const tagLbl=dur==='CRASH'?'CRASH':b.type==='async_bottleneck'?'ASYNC':'BLOCK';
  const sys=b.sys||{{}};
  return`<tr class="${{cls}}">
    <td><span class="expand-toggle" data-i="${{b.id}}">▸</span> #${{b.id}}</td>
    <td><span class="tag ${{tagCls}}">${{tagLbl}}</span></td>
    <td style="font-family:var(--mono);font-size:12px">${{(b.timestamp.split('T')[1]||'').slice(0,8)}}</td>
    <td><span class="dur ${{durClass(dur)}}">${{durFmt}}</span></td>
    <td>${{(sys.cpu_percent||0).toFixed(0)}}%</td>
    <td>${{(sys.memory_mb||0).toFixed(0)}}MB</td>
    <td>${{escHtml(b.hint)}}</td>
    <td style="font-family:var(--mono);font-size:12px">${{escHtml(b.location)}}</td>
  </tr><tr class="detail-row" id="detail-${{b.id}}">${{renderDetailRow(b)}}</tr>`;
}}

function renderHeader(){{
  const cols=viewMode==='grouped'?
    [['▸',''],['Location',''],['Hint',''],['Count',''],['Total',''],['Avg',''],['CPU Range',''],['Types','']]:
    [['#',''],['Type','type'],['Time','time'],['Duration','duration'],['CPU%','cpu'],['Mem','memory'],['Hint',''],['Location','']];
  document.getElementById('thead-row').innerHTML=cols.map(([lbl,key])=>{{
    const arrow=key===currentSort?(currentDir===-1?'▼':'▲'):'';
    return`<th${{key?` onclick="sortBy('${{key}}')"`:''}}>${{lbl}}<span class="arrow">${{arrow}}</span></th>`;
  }}).join('');
  document.getElementById('filter-row').style.display=viewMode==='grouped'?'none':'';
}}

function renderPagination(totalItems){{
  const totalPages=Math.max(1,Math.ceil(totalItems/PAGE_SIZE));
  if(currentPage>totalPages)currentPage=totalPages;
  const pg=document.getElementById('pagination');
  if(totalPages<=1){{pg.innerHTML='<span class="page-info">'+totalItems+' events</span>';return;}}
  pg.innerHTML=`<button class="btn" id="pg-prev" ${{currentPage<=1?'disabled':''}}>← Prev</button>
    <span class="page-info">Page ${{currentPage}} of ${{totalPages}} (${{totalItems}} events)</span>
    <button class="btn" id="pg-next" ${{currentPage>=totalPages?'disabled':''}}>Next →</button>`;
  document.getElementById('pg-prev').addEventListener('click',()=>{{if(currentPage>1){{currentPage--;render()}}}});
  document.getElementById('pg-next').addEventListener('click',()=>{{if(currentPage<totalPages){{currentPage++;render()}}}});
}}

function renderGrouped(){{
  const list=getFiltered();
  const groups=buildGroups(list);
  const tbody=document.getElementById('tbody');
  let html='';
  groups.forEach((g,gi)=>{{
    const avg=g.count>0?(g.totalDur/g.count):0;
    const types=new Set(g.events.map(e=>e.type==='async_bottleneck'?'ASYNC':'BLOCK'));
    const typeTags=[...types].map(t=>`<span class="tag ${{t==='ASYNC'?'tag-async':'tag-block'}}">${{t}}</span>`).join(' ');
    const cpuVals=g.events.map(e=>e.sys?.cpu_percent||0);
    const cpuMin=Math.min(...cpuVals).toFixed(0),cpuMax=Math.max(...cpuVals).toFixed(0);
    html+=`<tr class="group-row" data-grp="${{gi}}">
      <td><span class="expand-toggle" data-grp="${{gi}}">▸</span></td>
      <td style="font-family:var(--mono);font-size:12px">${{escHtml(g.location)}}</td>
      <td>${{escHtml(g.hint)}}</td>
      <td><span class="grp-count">${{g.count}}</span></td>
      <td><span class="dur ${{durClass(g.totalDur)}}">${{g.totalDur.toFixed(2)}}s</span></td>
      <td><span class="dur ${{durClass(avg)}}">${{avg.toFixed(4)}}s</span></td>
      <td>${{cpuMin}}-${{cpuMax}}%</td>
      <td>${{typeTags}}</td>
    </tr>`;
    // Sub-header for child events
    html+=`<tr class="group-child" data-grp="${{gi}}" style="background:var(--surface);border-bottom:2px solid var(--border)">
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">#</td>
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Type</td>
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Time</td>
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Duration</td>
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">CPU%</td>
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Mem</td>
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Hint</td>
      <td style="font-weight:700;color:var(--text-dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px">Location</td>
    </tr>`;
    g.events.forEach(b=>{{
      html+=`<tr class="group-child" data-grp="${{gi}}">${{renderEventRow(b).match(/<tr[^>]*>(.*?)<\\/tr>/s)?.[1]||''}}</tr>`;
      html+=`<tr class="group-child detail-row" data-grp="${{gi}}" id="detail-${{b.id}}">${{renderDetailRow(b)}}</tr>`;
    }});
  }});
  tbody.innerHTML=html;
  document.getElementById('pagination').innerHTML='<span class="page-info">'+groups.length+' groups, '+list.length+' events</span>';
  // Group expand toggles
  tbody.querySelectorAll('tr.group-row').forEach(row=>{{
    row.addEventListener('click',()=>{{
      const gi=row.dataset.grp;
      const children=tbody.querySelectorAll(`tr.group-child[data-grp="${{gi}}"]`);
      const toggle=row.querySelector('.expand-toggle');
      const isOpen=toggle.classList.contains('open');
      children.forEach(c=>{{
        if(isOpen){{c.classList.remove('show');}}
        else if(!c.classList.contains('detail-row')){{c.classList.add('show');}}
      }});
      toggle.classList.toggle('open');
      toggle.textContent=toggle.classList.contains('open')?'▾':'▸';
    }});
  }});
  // Event detail toggles inside groups
  tbody.querySelectorAll('.group-child .expand-toggle').forEach(el=>{{
    el.addEventListener('click',e=>{{
      e.stopPropagation();
      const row=document.getElementById('detail-'+el.dataset.i);
      if(row){{row.classList.toggle('show');el.classList.toggle('open');el.textContent=el.classList.contains('open')?'▾':'▸'}}
    }});
  }});
}}

function renderTimeline(){{
  const list=getFiltered();
  const start=(currentPage-1)*PAGE_SIZE;
  const pageData=list.slice(start,start+PAGE_SIZE);
  const tbody=document.getElementById('tbody');
  let html='';
  pageData.forEach(b=>{{html+=renderEventRow(b)}});
  tbody.innerHTML=html;
  tbody.querySelectorAll('.expand-toggle').forEach(el=>{{
    el.addEventListener('click',()=>{{
      const row=document.getElementById('detail-'+el.dataset.i);
      if(row){{row.classList.toggle('show');el.classList.toggle('open');el.textContent=el.classList.contains('open')?'▾':'▸'}}
    }});
  }});
  renderPagination(list.length);
}}

function render(){{
  renderHeader();
  if(viewMode==='grouped')renderGrouped();else renderTimeline();
}}

window.sortBy=function(key){{
  if(currentSort===key)currentDir*=-1;else{{currentSort=key;currentDir=-1}};currentPage=1;render();
}};

document.querySelectorAll('.col-filter').forEach(inp=>{{
  inp.addEventListener('input',e=>{{colFilters[e.target.dataset.col]=e.target.value;clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>{{currentPage=1;render()}},300)}});
}});
document.getElementById('search').addEventListener('input',e=>{{searchTerm=e.target.value;clearTimeout(debounceTimer);debounceTimer=setTimeout(()=>{{currentPage=1;render()}},300)}});
['all','block','async'].forEach(f=>{{
  document.getElementById('filter-'+f).addEventListener('click',()=>{{
    currentFilter=f;document.querySelectorAll('#filter-all,#filter-block,#filter-async').forEach(b=>b.classList.remove('active'));
    document.getElementById('filter-'+f).classList.add('active');currentPage=1;render();
  }});
}});
document.getElementById('sort-select').addEventListener('change',e=>{{currentSort=e.target.value;currentDir=-1;currentPage=1;render()}});
document.getElementById('view-grouped').addEventListener('click',()=>{{viewMode='grouped';document.getElementById('view-grouped').classList.add('active');document.getElementById('view-timeline').classList.remove('active');currentPage=1;render()}});
document.getElementById('view-timeline').addEventListener('click',()=>{{viewMode='timeline';document.getElementById('view-timeline').classList.add('active');document.getElementById('view-grouped').classList.remove('active');currentPage=1;render()}});

render();
</script>
</body>
</html>'''
