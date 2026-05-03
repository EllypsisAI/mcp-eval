#!/usr/bin/env python3
"""
MCP Eval Report Generator

Reads an eval-workspace directory and generates a self-contained HTML report
with all data embedded as JSON.

Usage:
    python3 report.py <eval-workspace-dir>
    python3 report.py <eval-workspace-dir> --output report.html
    python3 report.py <eval-workspace-dir> --context-window 200000
"""

import json
import os
import sys
import html as html_mod


def load_eval_data(workspace_dir):
    """Load run_summary.json and per-test detail files."""
    summary_path = os.path.join(workspace_dir, "run_summary.json")
    if not os.path.exists(summary_path):
        print(f"Error: {summary_path} not found. Is this an eval-workspace?")
        sys.exit(1)

    with open(summary_path) as f:
        summary = json.load(f)

    tests_detail = []
    for result in summary["results"]:
        test_name = result["name"]
        test_dir = os.path.join(workspace_dir, test_name)

        detail = {"summary": result}

        timing_path = os.path.join(test_dir, "timing.json")
        if os.path.exists(timing_path):
            with open(timing_path) as f:
                detail["timing"] = json.load(f)

        meta_path = os.path.join(test_dir, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                detail["meta"] = json.load(f)

        grading_path = os.path.join(test_dir, "grading.json")
        if os.path.exists(grading_path):
            with open(grading_path) as f:
                detail["grading"] = json.load(f)

        response_path = os.path.join(test_dir, "response.json")
        if os.path.exists(response_path):
            size = os.path.getsize(response_path)
            if size > 50_000:
                detail["response_truncated"] = True
                detail["response_size"] = size
                with open(response_path) as f:
                    detail["response_preview"] = (
                        f.read(2000)
                        + f"\n\n... [truncated -- full response is {size:,} bytes]"
                    )
            else:
                with open(response_path) as f:
                    detail["response"] = json.load(f)

        tests_detail.append(detail)

    return summary, tests_detail


def generate_html(summary, tests_detail, context_window=128000):
    """Generate self-contained HTML report."""
    data_json = json.dumps(
        {
            "summary": summary,
            "tests": tests_detail,
            "context_window": context_window,
        },
        ensure_ascii=False,
        default=str,
    )

    server = html_mod.escape(summary.get("server", "unknown"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{server} -- eval report</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg: #0d1117;
  --surface: #161b22;
  --surface-2: #1c2129;
  --border: #30363d;
  --border-subtle: #21262d;
  --text: #c9d1d9;
  --text-muted: #8b949e;
  --text-bright: #e6edf3;
  --primary: #58a6ff;
  --primary-muted: rgba(88,166,255,0.1);
  --green: #3fb950;
  --green-muted: rgba(63,185,80,0.15);
  --red: #f85149;
  --red-muted: rgba(248,81,73,0.15);
  --yellow: #d29922;
  --yellow-muted: rgba(210,153,34,0.15);
  --accent: #f78166;
  --mono: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
}}

html {{ font-size: 14px; }}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  line-height: 1.5;
}}

.page {{
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 64px;
}}

/* -- Top bar -- */
.topbar {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 8px;
}}
.topbar h1 {{ font-size: 16px; font-weight: 600; color: var(--text-bright); }}
.topbar .meta {{
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}}

/* -- Stats row -- */
.stats {{
  display: flex;
  gap: 1px;
  background: var(--border);
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 20px;
}}
.stat {{
  flex: 1;
  background: var(--surface);
  padding: 10px 14px;
}}
.stat-val {{
  font-size: 18px;
  font-weight: 600;
  color: var(--text-bright);
  font-variant-numeric: tabular-nums;
}}
.stat-val.green {{ color: var(--green); }}
.stat-val.red {{ color: var(--red); }}
.stat-label {{ font-size: 11px; color: var(--text-muted); margin-top: 1px; }}

/* -- Budget bar -- */
.budget {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 20px;
}}
.budget-header {{
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}}
.budget-track {{
  height: 8px;
  background: var(--surface-2);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
}}
.budget-seg {{ height: 100%; }}
.budget-legend {{
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-muted);
}}
.budget-legend-item {{ display: flex; align-items: center; gap: 4px; }}
.budget-dot {{ width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }}

/* -- Token bars -- */
.bars-section {{ margin-bottom: 24px; }}
.bars-title {{
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 8px;
}}
.bar-row {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  cursor: pointer;
  height: 26px;
}}
.bar-row:hover {{ background: var(--surface); }}
.bar-row.active {{ background: var(--surface-2); }}
.bar-name {{
  width: 160px;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.bar-track {{
  flex: 1;
  height: 6px;
  background: var(--surface);
  border-radius: 3px;
  overflow: hidden;
}}
.bar-fill {{
  height: 100%;
  border-radius: 3px;
  background: var(--green);
  opacity: 0.5;
}}
.bar-fill.warn {{ background: var(--yellow); opacity: 0.6; }}
.bar-fill.bad {{ background: var(--red); opacity: 0.6; }}
.bar-fill.err {{ background: var(--red); opacity: 0.2; }}
.bar-num {{
  width: 72px;
  flex-shrink: 0;
  text-align: right;
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
}}

/* -- Tool catalog -- */
.tool-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 8px;
  margin-bottom: 24px;
}}
.tool-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
}}
.tool-card-head {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}}
.tool-card-name {{
  font-family: var(--mono);
  font-size: 13px;
  color: var(--text-bright);
  font-weight: 500;
}}
.tool-card-desc {{
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}}
.tool-card-params {{
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--mono);
}}
.tool-card-params span {{ color: var(--primary); }}

/* -- Comparisons -- */
.comparison {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 8px;
}}
.comp-title {{ font-size: 13px; font-weight: 600; color: var(--text-bright); margin-bottom: 4px; }}
.comp-desc {{ font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }}
.comp-row {{ display: flex; gap: 12px; }}
.comp-item {{
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  padding: 8px 10px;
}}
.comp-item-label {{ font-weight: 600; color: var(--text-muted); font-size: 11px; margin-bottom: 4px; }}
.comp-metric {{ display: flex; justify-content: space-between; padding: 2px 0; color: var(--text); font-size: 12px; }}
.comp-metric span:last-child {{ font-family: var(--mono); font-size: 12px; }}
.savings {{ color: var(--green); font-weight: 600; }}

/* -- Section titles -- */
.section-title {{
  font-size: 13px;
  font-weight: 600;
  color: var(--text-bright);
  margin: 24px 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}}

/* -- Table -- */
.tbl {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.tbl th {{
  text-align: left;
  padding: 8px 10px;
  font-weight: 600;
  font-size: 12px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}}
.tbl th:hover {{ color: var(--text); }}
.tbl th.sorted::after {{ content: ' \\2191'; }}
.tbl th.sorted.desc::after {{ content: ' \\2193'; }}
.tbl td {{
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: top;
  font-variant-numeric: tabular-nums;
}}
.tbl tbody tr {{
  cursor: pointer;
  transition: background 0.08s;
}}
.tbl tbody tr:hover {{ background: var(--surface); }}
.tbl tbody tr.active {{ background: var(--surface-2); }}
.tbl td.num {{ text-align: right; font-family: var(--mono); font-size: 12px; white-space: nowrap; }}

.badge {{
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
}}
.badge-pass {{ background: var(--green-muted); color: var(--green); }}
.badge-fail {{ background: var(--red-muted); color: var(--red); }}
.badge-skip {{ color: var(--text-muted); }}
.badge-graded {{ background: var(--primary-muted); color: var(--primary); font-size: 10px; margin-left: 4px; }}
.badge-ungraded {{ color: var(--text-muted); font-size: 10px; margin-left: 4px; }}
.token-warn {{ color: var(--red); font-weight: 600; }}
.token-caution {{ color: var(--yellow); }}

/* -- Detail panel -- */
.detail-panel {{
  display: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  margin: 4px 0 8px;
  padding: 12px 16px;
}}
.detail-panel.open {{ display: block; }}
.detail-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}}
.detail-head h3 {{ font-size: 14px; font-weight: 600; color: var(--text-bright); }}
.detail-head .sub {{ font-size: 12px; color: var(--text-muted); margin-left: 8px; font-weight: 400; }}
.detail-head button {{
  background: none;
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
}}
.detail-head button:hover {{ border-color: var(--text-muted); color: var(--text); }}
.detail-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
}}
.detail-cell {{
  padding: 10px 12px;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}}
.detail-cell:nth-child(2n) {{ border-right: none; }}
.detail-cell.full {{ grid-column: 1 / -1; border-right: none; }}
.detail-cell h4 {{ font-size: 11px; font-weight: 600; color: var(--text-muted); margin-bottom: 4px; }}
.detail-cell pre {{
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  white-space: pre-wrap;
  word-break: break-word;
}}
.kv {{ display: flex; justify-content: space-between; padding: 2px 0; font-size: 12px; }}
.kv .k {{ color: var(--text-muted); }}
.kv .v {{ color: var(--text); font-weight: 500; }}
.err-msg {{ color: var(--red); font-weight: 500; font-size: 12px; }}
.fields-wrap {{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}}
.fields-wrap span {{
  font-family: var(--mono);
  font-size: 10px;
  padding: 2px 6px;
  background: var(--bg);
  border-radius: 3px;
  color: var(--text-muted);
}}
.resp-box {{
  background: var(--bg);
  border-radius: 4px;
  padding: 10px;
  max-height: 220px;
  overflow-y: auto;
  margin-top: 6px;
}}
.resp-box pre {{ font-size: 11px; color: var(--text-muted); }}

/* -- Grading in detail -- */
.assertion-list {{ list-style: none; }}
.assertion-item {{
  padding: 5px 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 12px;
}}
.assertion-item:last-child {{ border-bottom: none; }}
.assertion-status {{ font-weight: 600; margin-right: 6px; }}
.assertion-status.pass {{ color: var(--green); }}
.assertion-status.fail {{ color: var(--red); }}
.assertion-evidence {{
  color: var(--text-muted);
  font-size: 11px;
  margin-top: 2px;
  padding-left: 20px;
}}

/* -- Expand icon -- */
.expand-icon {{
  display: inline-block;
  width: 14px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
  margin-right: 4px;
  transition: transform 0.1s;
}}
.expandable.expanded .expand-icon {{ transform: rotate(90deg); }}

/* -- Footer -- */
.foot {{
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  justify-content: space-between;
}}

@media (max-width: 768px) {{
  body {{ padding: 16px 12px; }}
  .stats {{ flex-direction: column; }}
  .detail-grid {{ grid-template-columns: 1fr; }}
  .comp-row {{ flex-direction: column; }}
  .tool-grid {{ grid-template-columns: 1fr; }}
  .bar-name {{ width: 100px; }}
}}
</style>
</head>
<body>
<div class="page">
  <div class="topbar">
    <h1 id="title"></h1>
    <div class="meta" id="meta"></div>
  </div>
  <div id="stats"></div>
  <div id="budget"></div>
  <div class="bars-section">
    <div class="bars-title">Token cost per call</div>
    <div id="bars"></div>
  </div>
  <div id="tool-catalog"></div>
  <div id="comparisons"></div>
  <div id="results-section"></div>
  <div class="foot">
    <span>mcp-eval</span>
    <span id="foot-ts"></span>
  </div>
</div>

<script>
const D = {data_json};
const S = D.summary;
const T = D.tests;
const CTX = D.context_window;

function fB(b) {{
  if (b >= 1048576) return (b / 1048576).toFixed(1) + ' MB';
  if (b >= 1024) return (b / 1024).toFixed(1) + ' KB';
  return b + ' B';
}}
function fT(t) {{
  if (t >= 1000000) return (t / 1000000).toFixed(1) + 'M';
  if (t >= 1000) return (t / 1000).toFixed(1) + 'k';
  return String(t);
}}
function fM(ms) {{
  if (ms >= 1000) return (ms / 1000).toFixed(1) + 's';
  return Math.round(ms) + 'ms';
}}
function tC(t) {{
  if (t > 10000) return 'token-warn';
  if (t > 3000) return 'token-caution';
  return '';
}}
function esc(s) {{
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}}

// --- Header ---
document.getElementById('title').textContent = S.server;
var host = S.url ? S.url.replace(/https?:\\/\\//, '').split('/')[0] : '';
var ts = S.timestamp || '';
document.getElementById('meta').innerHTML =
  (host ? '<span>' + esc(host) + '</span>' : '') +
  (ts ? '<span>' + esc(ts) + '</span>' : '');

// --- Stats ---
var res = S.results;
var passed = res.filter(function(t) {{ return t.status === 'success'; }}).length;
var failed = res.filter(function(t) {{ return t.status !== 'success' && t.status !== 'skipped'; }}).length;
var skipped = res.filter(function(t) {{ return t.status === 'skipped'; }}).length;
var sorted = res.filter(function(t) {{ return t.duration_ms; }}).slice().sort(function(a, b) {{ return a.duration_ms - b.duration_ms; }});
var medMs = sorted.length > 0 ? sorted[Math.floor(sorted.length / 2)].duration_ms : 0;
var bombTh = 10000;
var bombs = res.filter(function(t) {{ return t.estimated_tokens > bombTh && t.status === 'success'; }});
var tokExcl = res.filter(function(t) {{ return t.estimated_tokens <= bombTh; }}).reduce(function(s, t) {{ return s + t.estimated_tokens; }}, 0);
var uniqueTools = {{}};
res.forEach(function(t) {{ uniqueTools[t.tool] = true; }});

document.getElementById('stats').innerHTML = '<div class="stats">' +
  '<div class="stat"><div class="stat-val green">' + passed + ' / ' + res.length + '</div><div class="stat-label">passed</div></div>' +
  '<div class="stat"><div class="stat-val' + (failed > 0 ? ' red' : '') + '">' + failed + '</div><div class="stat-label">failed</div></div>' +
  '<div class="stat"><div class="stat-val">' + fM(medMs) + '</div><div class="stat-label">median latency</div></div>' +
  '<div class="stat"><div class="stat-val">' + fT(S.total_estimated_tokens) + '</div><div class="stat-label">total tokens</div></div>' +
  '<div class="stat"><div class="stat-val">' + fT(tokExcl) + '</div><div class="stat-label">excl. outliers</div></div>' +
  '<div class="stat"><div class="stat-val">' + Object.keys(uniqueTools).length + '</div><div class="stat-label">unique tools</div></div>' +
  '</div>';

// --- Budget bar ---
var totT = S.total_estimated_tokens;
var bomT = bombs.reduce(function(s, t) {{ return s + t.estimated_tokens; }}, 0);
var errT = res.filter(function(t) {{ return t.status !== 'success'; }}).reduce(function(s, t) {{ return s + t.estimated_tokens; }}, 0);
var useT = totT - bomT - errT;

document.getElementById('budget').innerHTML = '<div class="budget">' +
  '<div class="budget-header"><span>All ' + res.length + ' tool calls combined</span><span>' + fT(totT) + ' / ' + fT(CTX) + ' tokens (' + (totT / CTX * 100).toFixed(0) + '%)</span></div>' +
  '<div class="budget-track">' +
    '<div class="budget-seg" style="width:' + (useT / CTX * 100).toFixed(1) + '%;background:var(--green)"></div>' +
    '<div class="budget-seg" style="width:' + (bomT / CTX * 100).toFixed(1) + '%;background:var(--red)"></div>' +
    '<div class="budget-seg" style="width:' + (errT / CTX * 100).toFixed(1) + '%;background:var(--yellow)"></div>' +
  '</div>' +
  '<div class="budget-legend">' +
    '<div class="budget-legend-item"><div class="budget-dot" style="background:var(--green)"></div>Useful (' + fT(useT) + ')</div>' +
    '<div class="budget-legend-item"><div class="budget-dot" style="background:var(--red)"></div>Outliers (' + fT(bomT) + ')</div>' +
    '<div class="budget-legend-item"><div class="budget-dot" style="background:var(--yellow)"></div>Errors (' + fT(errT) + ')</div>' +
  '</div></div>';

// --- Token cost bars ---
var maxTok = Math.max.apply(null, T.map(function(t) {{ return t.summary.estimated_tokens || 0; }}).concat([1]));
document.getElementById('bars').innerHTML = T.map(function(t, i) {{
  var tok = t.summary.estimated_tokens || 0;
  var pct = Math.max((tok / maxTok) * 100, 0.3);
  var isErr = t.summary.status !== 'success';
  var cls = 'bar-fill';
  if (isErr) cls += ' err';
  else if (tok > 10000) cls += ' bad';
  else if (tok > 2000) cls += ' warn';
  var label = isErr ? t.summary.status.replace('mcp_', '') : '~' + fT(tok);
  return '<div class="bar-row" data-i="' + i + '">' +
    '<span class="bar-name">' + esc(t.summary.name) + '</span>' +
    '<div class="bar-track"><div class="' + cls + '" style="width:' + pct + '%"></div></div>' +
    '<span class="bar-num">' + label + '</span>' +
    '</div>';
}}).join('');

// --- Tool catalog (auto-computed) ---
var toolMap = {{}};
res.forEach(function(r) {{
  if (!toolMap[r.tool]) {{
    toolMap[r.tool] = {{ name: r.tool, desc: '', schema: null, tests: [], ok: true }};
  }}
  toolMap[r.tool].tests.push(r);
  if (r.status !== 'success') toolMap[r.tool].ok = false;
}});
T.forEach(function(t) {{
  var m = t.meta;
  if (m && m.tool_definition && toolMap[m.tool_definition.name]) {{
    var entry = toolMap[m.tool_definition.name];
    if (!entry.desc && m.tool_definition.description) entry.desc = m.tool_definition.description;
    if (!entry.schema && m.tool_definition.inputSchema) entry.schema = m.tool_definition.inputSchema;
  }}
}});

var toolKeys = Object.keys(toolMap);
var toolHtml = '<div class="section-title">Tool catalog (' + toolKeys.length + ' tools)</div><div class="tool-grid">';
toolKeys.forEach(function(key) {{
  var tool = toolMap[key];
  var rq = tool.schema && tool.schema.required ? tool.schema.required : [];
  var tc = tool.tests.length;
  var pc = tool.tests.filter(function(t) {{ return t.status === 'success'; }}).length;
  toolHtml += '<div class="tool-card"><div class="tool-card-head">' +
    '<span class="tool-card-name">' + esc(tool.name) + '</span>' +
    '<span class="badge ' + (tool.ok ? 'badge-pass' : 'badge-fail') + '">' + pc + '/' + tc + '</span>' +
    '</div>' +
    '<div class="tool-card-desc">' + esc(tool.desc) + '</div>' +
    (rq.length > 0
      ? '<div class="tool-card-params">required: <span>' + rq.map(esc).join(', ') + '</span></div>'
      : '<div class="tool-card-params">no required params</div>') +
    '</div>';
}});
toolHtml += '</div>';
document.getElementById('tool-catalog').innerHTML = toolHtml;

// --- Cost comparisons (auto-detect test pairs sharing same tool) ---
var toolTests = {{}};
T.forEach(function(t, i) {{
  var tool = t.summary.tool;
  if (!toolTests[tool]) toolTests[tool] = [];
  toolTests[tool].push({{ idx: i, test: t }});
}});

var compHtml = '';
var hasComps = false;
Object.keys(toolTests).forEach(function(tool) {{
  var tests = toolTests[tool];
  if (tests.length < 2) return;
  hasComps = true;
  for (var i = 0; i < tests.length - 1; i++) {{
    for (var j = i + 1; j < tests.length; j++) {{
      var a = tests[i].test, b = tests[j].test;
      var aTok = a.timing ? a.timing.estimated_tokens : a.summary.estimated_tokens;
      var bTok = b.timing ? b.timing.estimated_tokens : b.summary.estimated_tokens;
      var aBytes = a.timing ? a.timing.response_bytes : a.summary.response_bytes;
      var bBytes = b.timing ? b.timing.response_bytes : b.summary.response_bytes;
      var aFields = a.timing ? a.timing.field_count : '-';
      var bFields = b.timing ? b.timing.field_count : '-';
      var aMs = a.summary.duration_ms, bMs = b.summary.duration_ms;
      var diff = aTok - bTok;
      var higher = diff >= 0 ? a : b;
      var lower = diff >= 0 ? b : a;
      var absDiff = Math.abs(diff);
      var pct = Math.max(aTok, bTok) > 0 ? ((absDiff / Math.max(aTok, bTok)) * 100).toFixed(0) : 0;

      compHtml += '<div class="comparison"><div class="comp-title">' + esc(tool) + ': ' + esc(a.summary.name) + ' vs ' + esc(b.summary.name) + '</div>';

      var stepA = a.meta && a.meta.test ? a.meta.test.workflow_step : '';
      var stepB = b.meta && b.meta.test ? b.meta.test.workflow_step : '';
      if (stepA || stepB) {{
        compHtml += '<div class="comp-desc">' + esc(stepA || '') + ' vs ' + esc(stepB || '') + '</div>';
      }}

      compHtml += '<div class="comp-row">' +
        '<div class="comp-item"><div class="comp-item-label">' + esc(a.summary.name) + '</div>' +
          '<div class="comp-metric"><span>Tokens</span><span>' + fT(aTok) + '</span></div>' +
          '<div class="comp-metric"><span>Size</span><span>' + fB(aBytes) + '</span></div>' +
          '<div class="comp-metric"><span>Fields</span><span>' + aFields + '</span></div>' +
          '<div class="comp-metric"><span>Latency</span><span>' + fM(aMs) + '</span></div>' +
        '</div>' +
        '<div class="comp-item"><div class="comp-item-label">' + esc(b.summary.name) + '</div>' +
          '<div class="comp-metric"><span>Tokens</span><span>' + fT(bTok) + '</span></div>' +
          '<div class="comp-metric"><span>Size</span><span>' + fB(bBytes) + '</span></div>' +
          '<div class="comp-metric"><span>Fields</span><span>' + bFields + '</span></div>' +
          '<div class="comp-metric"><span>Latency</span><span>' + fM(bMs) + '</span></div>' +
        '</div></div>';

      if (absDiff > 0) {{
        compHtml += '<div style="font-size:12px;color:var(--text-muted);margin-top:6px">' +
          esc(lower.summary.name) + ' saves <span class="savings">' + fT(absDiff) + ' tokens (' + pct + '%)</span></div>';
      }}
      compHtml += '</div>';
    }}
  }}
}});

if (hasComps) {{
  document.getElementById('comparisons').innerHTML = '<div class="section-title">Cost comparisons</div>' + compHtml;
}}

// --- Results table ---
var tblHtml = '<div class="section-title">All test results</div>';
tblHtml += '<table class="tbl"><thead><tr id="thead">';
var cols = [
  {{ key: 'status', label: '', w: '50px' }},
  {{ key: 'name', label: 'Test', w: '' }},
  {{ key: 'tool', label: 'Tool', w: '' }},
  {{ key: 'duration_ms', label: 'Latency', w: '70px' }},
  {{ key: 'response_bytes', label: 'Size', w: '70px' }},
  {{ key: 'estimated_tokens', label: 'Tokens', w: '80px' }},
];
cols.forEach(function(c) {{
  tblHtml += '<th data-col="' + c.key + '"' + (c.w ? ' style="width:' + c.w + '"' : '') + '>' + c.label + '</th>';
}});
tblHtml += '</tr></thead><tbody>';

T.forEach(function(t, i) {{
  var s = t.summary;
  var isErr = s.status !== 'success' && s.status !== 'skipped';
  var isSkip = s.status === 'skipped';
  var badgeCls = isErr ? 'badge-fail' : (isSkip ? 'badge-skip' : 'badge-pass');
  var badgeTxt = s.status === 'success' ? 'pass' : (s.status === 'mcp_error' ? 'error' : s.status);
  var hasGrading = !!(t.grading && t.grading.expectations);
  var gradingBadge = '';
  if (hasGrading) {{
    var gRes = t.grading.expectations;
    var gPass = gRes.filter(function(g) {{ return g.passed; }}).length;
    var gTotal = gRes.length;
    gradingBadge = '<span class="badge badge-graded">' + gPass + '/' + gTotal + '</span>';
  }}

  tblHtml += '<tr class="expandable' + (isErr ? ' row-error' : '') + '" data-i="' + i + '" id="row-' + i + '">' +
    '<td><span class="badge ' + badgeCls + '">' + badgeTxt + '</span>' + gradingBadge + '</td>' +
    '<td><span class="expand-icon">&#9654;</span>' + esc(s.name) + '</td>' +
    '<td style="font-family:var(--mono);font-size:12px;color:var(--primary)">' + esc(s.tool) + '</td>' +
    '<td class="num">' + (s.duration_ms ? fM(s.duration_ms) : '-') + '</td>' +
    '<td class="num">' + (s.response_bytes ? fB(s.response_bytes) : '-') + '</td>' +
    '<td class="num ' + tC(s.estimated_tokens || 0) + '">' + (s.estimated_tokens ? '~' + fT(s.estimated_tokens) : '-') + '</td>' +
    '</tr>';
  tblHtml += '<tr><td colspan="6" style="padding:0;border:none"><div class="detail-panel" id="det-' + i + '"></div></td></tr>';
}});

tblHtml += '</tbody></table>';
document.getElementById('results-section').innerHTML = tblHtml;

// --- Sorting ---
var sortCol = null, sortAsc = true;
var thead = document.getElementById('thead');
thead.addEventListener('click', function(e) {{
  var th = e.target.closest('th');
  if (!th) return;
  var col = th.dataset.col;
  if (sortCol === col) sortAsc = !sortAsc;
  else {{ sortCol = col; sortAsc = true; }}
  thead.querySelectorAll('th').forEach(function(h) {{ h.className = ''; }});
  th.className = 'sorted' + (sortAsc ? '' : ' desc');
  var indices = T.map(function(_, i) {{ return i; }});
  indices.sort(function(a, b) {{
    var va = T[a].summary[col], vb = T[b].summary[col];
    if (va == null) va = '';
    if (vb == null) vb = '';
    if (typeof va === 'number' && typeof vb === 'number')
      return sortAsc ? va - vb : vb - va;
    return sortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  }});
  var tbody = document.querySelector('.tbl tbody');
  var rows = Array.from(tbody.children);
  var rowPairs = {{}};
  for (var r = 0; r < rows.length; r += 2) {{
    var idx = rows[r].dataset.i;
    rowPairs[idx] = [rows[r], rows[r + 1]];
  }}
  tbody.innerHTML = '';
  indices.forEach(function(idx) {{
    if (rowPairs[idx]) {{
      tbody.appendChild(rowPairs[idx][0]);
      tbody.appendChild(rowPairs[idx][1]);
    }}
  }});
}});

// --- Detail panel open/close ---
function openDetail(idx) {{
  var t = T[idx];
  if (!t) return;
  var s = t.summary;
  var timing = t.timing || {{}};
  var meta = t.meta || {{}};
  var test = meta.test || {{}};
  var toolDef = meta.tool_definition || {{}};
  var grading = t.grading || null;

  // close all
  document.querySelectorAll('.detail-panel.open').forEach(function(p) {{ p.classList.remove('open'); }});
  document.querySelectorAll('.expandable.expanded').forEach(function(r) {{ r.classList.remove('expanded'); }});
  document.querySelectorAll('.bar-row.active, .tbl tbody tr.active').forEach(function(el) {{ el.classList.remove('active'); }});

  var panel = document.getElementById('det-' + idx);
  var row = document.getElementById('row-' + idx);
  if (!panel) return;

  // highlight
  row.classList.add('active', 'expanded');
  document.querySelectorAll('.bar-row[data-i="' + idx + '"]').forEach(function(el) {{ el.classList.add('active'); }});

  var h = '<div class="detail-head"><h3>' + esc(s.name) + '<span class="sub">' + esc(s.tool) + '</span></h3>' +
    '<button onclick="closeDetail()">Close</button></div>';
  h += '<div class="detail-grid">';

  // Params
  h += '<div class="detail-cell"><h4>Parameters</h4>';
  var params = test.params || {{}};
  var pk = Object.keys(params);
  if (pk.length > 0) {{
    h += '<pre>' + esc(JSON.stringify(params, null, 2)) + '</pre>';
  }} else {{
    h += '<pre style="color:var(--text-muted)">No parameters</pre>';
  }}
  h += '</div>';

  // Metrics
  h += '<div class="detail-cell"><h4>Metrics</h4>' +
    '<div class="kv"><span class="k">Duration</span><span class="v">' + (s.duration_ms ? fM(s.duration_ms) : '-') + '</span></div>' +
    '<div class="kv"><span class="k">Response</span><span class="v">' + (s.response_bytes ? fB(s.response_bytes) : '-') + '</span></div>' +
    '<div class="kv"><span class="k">Payload</span><span class="v">' + (timing.response_payload_bytes ? fB(timing.response_payload_bytes) : '-') + '</span></div>' +
    '<div class="kv"><span class="k">Tokens</span><span class="v">' + (s.estimated_tokens ? '~' + fT(s.estimated_tokens) : '-') + '</span></div>' +
    '<div class="kv"><span class="k">Fields</span><span class="v">' + (timing.field_count != null ? timing.field_count : '-') + '</span></div>' +
    '</div>';

  // Error
  if (s.error) {{
    h += '<div class="detail-cell full"><h4>Error</h4><div class="err-msg">' + esc(s.error) + '</div></div>';
  }}

  // Assertions + grading
  var assertions = test.assertions || [];
  if (grading && grading.expectations && grading.expectations.length > 0) {{
    // Graded assertions
    var gRes = grading.expectations;
    var gPass = gRes.filter(function(g) {{ return g.passed; }}).length;
    h += '<div class="detail-cell"><h4>Assertions (graded: ' + gPass + '/' + gRes.length + ')</h4>';
    h += '<ul class="assertion-list">';
    gRes.forEach(function(g) {{
      var st = g.passed ? 'pass' : 'fail';
      h += '<li class="assertion-item">' +
        '<span class="assertion-status ' + st + '">' + (g.passed ? 'PASS' : 'FAIL') + '</span>' +
        esc(g.text || '') +
        (g.evidence ? '<div class="assertion-evidence">' + esc(g.evidence) + '</div>' : '') +
        '</li>';
    }});
    h += '</ul></div>';
  }} else if (assertions.length > 0) {{
    // Ungraded assertions
    h += '<div class="detail-cell"><h4>Assertions (ungraded)</h4>';
    h += '<ul class="assertion-list">';
    assertions.forEach(function(a) {{
      h += '<li class="assertion-item" style="color:var(--text-muted)">' + esc(a) + '</li>';
    }});
    h += '</ul></div>';
  }}

  // Tool definition + workflow step
  h += '<div class="detail-cell"><h4>Tool definition</h4>' +
    '<pre>' + esc(toolDef.description || '-') + '</pre>';
  if (test.workflow_step) {{
    h += '<h4 style="margin-top:8px">Workflow step</h4><pre>' + esc(test.workflow_step) + '</pre>';
  }}

  // Schema required params
  var sc = toolDef.inputSchema;
  if (sc && sc.required && sc.required.length > 0) {{
    h += '<h4 style="margin-top:8px">Required params</h4>';
    h += '<pre style="font-size:11px">';
    sc.required.forEach(function(f) {{
      var tp = sc.properties && sc.properties[f] ? sc.properties[f].type : '?';
      h += esc(f) + ': ' + esc(tp) + '\\n';
    }});
    h += '</pre>';
  }}
  h += '</div>';

  // Response fields
  if (timing.fields && timing.fields.length > 0) {{
    var extra = timing.field_count > timing.fields.length
      ? '<span style="color:var(--text-muted)">+' + (timing.field_count - timing.fields.length) + ' more</span>' : '';
    h += '<div class="detail-cell full"><h4>Response fields (' + timing.field_count + ')</h4>' +
      '<div class="fields-wrap">' + timing.fields.map(function(f) {{ return '<span>' + esc(f) + '</span>'; }}).join('') + extra + '</div></div>';
  }}

  // Response preview
  if (t.response) {{
    var preview = JSON.stringify(t.response, null, 2);
    if (preview.length > 3000) preview = preview.substring(0, 3000) + '\\n...';
    h += '<div class="detail-cell full"><h4>Response preview</h4><div class="resp-box"><pre>' + esc(preview) + '</pre></div></div>';
  }} else if (t.response_preview) {{
    h += '<div class="detail-cell full"><h4>Response preview (truncated, ' + fB(t.response_size) + ' total)</h4>' +
      '<div class="resp-box"><pre>' + esc(t.response_preview) + '</pre></div></div>';
  }}

  h += '</div>';
  panel.innerHTML = h;
  panel.classList.add('open');
  panel.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
}}

function closeDetail() {{
  document.querySelectorAll('.detail-panel.open').forEach(function(p) {{ p.classList.remove('open'); }});
  document.querySelectorAll('.expandable.expanded').forEach(function(r) {{ r.classList.remove('expanded'); }});
  document.querySelectorAll('.bar-row.active, .tbl tbody tr.active').forEach(function(el) {{ el.classList.remove('active'); }});
}}

document.addEventListener('click', function(e) {{
  var bar = e.target.closest('.bar-row');
  if (bar) {{ openDetail(+bar.dataset.i); return; }}
  var tr = e.target.closest('.tbl tbody tr.expandable');
  if (tr) {{ openDetail(+tr.dataset.i); return; }}
}});

document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeDetail();
}});

document.getElementById('foot-ts').textContent = new Date().toISOString().replace('T', ' ').substring(0, 19);
</script>
</body>
</html>"""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 report.py <eval-workspace-dir> [--output <file.html>] [--context-window <int>]")
        sys.exit(1)

    workspace_dir = sys.argv[1]
    output_file = os.path.join(workspace_dir, "eval-report.html")
    context_window = 128000

    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]

    if "--context-window" in sys.argv:
        idx = sys.argv.index("--context-window")
        if idx + 1 < len(sys.argv):
            context_window = int(sys.argv[idx + 1])

    summary, tests_detail = load_eval_data(workspace_dir)
    html_content = generate_html(summary, tests_detail, context_window)

    with open(output_file, "w") as f:
        f.write(html_content)

    print(f"Report: {output_file}")
    print(f"  {summary['tests_run']}/{summary['tests_total']} passed | {summary.get('tests_error', 0)} errors | ~{summary['total_estimated_tokens']:,} tokens")
