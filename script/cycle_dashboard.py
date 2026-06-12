#!/usr/bin/env python3

import argparse
import json
import re
from pathlib import Path

result_path = "/Users/bytedance/Desktop/Accel-sim/accel-sim-framework/regress_result/20260612_064245"


def resolve_result_dir(value):
    path = Path(value)
    if path.exists():
        return path.resolve()
    script_dir = Path(__file__).resolve().parent
    regress_result_path = script_dir.parent / "regress_result" / value
    if regress_result_path.exists():
        return regress_result_path.resolve()
    return path.resolve()


def short_case_label(name):
    return str(name).split("-", 1)[0]


def parse_last_gpu_cycle(log_path):
    pattern = re.compile(r"gpu_tot_sim_cycle\s*=\s*(\d+)")
    last_value = None
    with open(log_path, "r", errors="ignore") as f:
        for line in f:
            match = pattern.search(line)
            if match:
                last_value = int(match.group(1))
    return last_value


def find_case_logs(root):
    records = []
    for log_path in sorted(root.rglob("*.log")):
        if log_path.name == "inst_stage.log":
            continue
        case_dir = log_path.parent
        config_dir = case_dir.parent
        if config_dir == root or config_dir.name == "confluence":
            continue
        cycles = parse_last_gpu_cycle(log_path)
        if cycles is None:
            continue
        records.append({
            "config": config_dir.name,
            "case": case_dir.name,
            "case_label": short_case_label(case_dir.name),
            "cycles": cycles,
            "log_path": str(log_path),
        })
    return records


def render_dashboard(records, root):
    data_json = json.dumps(records, ensure_ascii=False)
    title = f"Cycle Dashboard - {root.name}"
    return f"""<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f7f7f7; color: #222; }}
header {{ background: #263238; color: white; padding: 14px 22px; }}
main {{ padding: 18px 22px; }}
.controls {{ display: grid; grid-template-columns: repeat(4, minmax(220px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.card {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.05); }}
label {{ display: block; font-size: 12px; color: #555; margin-bottom: 4px; }}
select, input {{ width: 100%; box-sizing: border-box; padding: 7px; border: 1px solid #bbb; border-radius: 4px; }}
button {{ padding: 8px 10px; border: 1px solid #999; background: #fff; border-radius: 4px; cursor: pointer; }}
button:hover {{ background: #eee; }}
.summary {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
.summary .card {{ min-width: 180px; }}
.chart {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 16px; overflow-x: auto; }}
svg {{ font-family: inherit; }}
.axis text {{ font-size: 11px; }}
.grid line {{ stroke: #ddd; stroke-dasharray: 3 3; }}
.row-guide:nth-child(even) {{ fill: #f2f2f2; }}
.tooltip {{ position: fixed; pointer-events: none; background: rgba(0,0,0,.85); color: white; padding: 7px 9px; border-radius: 4px; font-size: 12px; display: none; max-width: 520px; z-index: 10; }}
table {{ border-collapse: collapse; width: 100%; background: white; font-size: 12px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
th {{ background: #eceff1; position: sticky; top: 0; }}
.badge {{ display: inline-block; padding: 2px 6px; border-radius: 3px; background: #eceff1; }}
.positive {{ color: #c62828; font-weight: 600; }}
.negative {{ color: #2e7d32; font-weight: 600; }}
.baseline {{ color: #1565c0; font-weight: 700; }}
</style>
</head>
<body>
<header>
  <h2>{title}</h2>
  <div>{root}</div>
</header>
<main>
  <div class=\"controls\">
    <div class=\"card\"><label>Case filter</label><input id=\"caseFilter\" placeholder=\"substring, e.g. bfs\"></div>
    <div class=\"card\"><label>Primary config</label><select id=\"configA\"></select></div>
    <div class=\"card\"><label>Baseline config</label><select id=\"configB\"></select></div>
    <div class=\"card\"><label>Chart mode</label><select id=\"mode\">
      <option value=\"configCompare\">Config A vs Baseline</option>
      <option value=\"groupCompare\">Group A vs Group B by parameter filters</option>
      <option value=\"configTotals\">Config total cycles ranking</option>
      <option value=\"paramSummary\">Parameter value summary</option>
      <option value=\"caseAllConfigs\">Selected case across configs</option>
      <option value=\"bestRelative\">All configs vs best per case</option>
      <option value=\"selectedBaseline\">All configs vs selected baseline config</option>
      <option value=\"lrrBaseline\">All configs vs lrr/rfc0/ocu8</option>
      <option value=\"paramBaseline\">All configs vs selected parameter baseline</option>
    </select></div>
    <div class=\"card\"><label>Baseline parameter</label><select id=\"baselineParam\"></select></div>
    <div class=\"card\"><label>Baseline parameter value</label><select id=\"baselineParamValue\"></select></div>
    <div class=\"card\"><label>Group A filter</label><input id=\"groupAFilter\" placeholder=\"rfc=1,reuse=0,dp=0\"></div>
    <div class=\"card\"><label>Group B filter</label><input id=\"groupBFilter\" placeholder=\"rfc=1,reuse=1,dp=1\"></div>
    <div class=\"card\"><label>Selected case</label><select id=\"caseSelect\"></select></div>
    <div class=\"card\"><label>Sort</label><select id=\"sortMode\">
      <option value=\"case\">Case name</option>
      <option value=\"cyclesDesc\">Cycles desc</option>
      <option value=\"cyclesAsc\">Cycles asc</option>
      <option value=\"deltaDesc\">Delta desc</option>
      <option value=\"deltaAsc\">Delta asc</option>
    </select></div>
    <div class=\"card\"><label>Scale</label><select id=\"scaleMode\">
      <option value=\"linear\">Linear</option>
      <option value=\"log\">Log10</option>
    </select></div>
    <div class=\"card\"><label>Actions</label><button id=\"downloadCsv\">Download filtered CSV</button></div>
  </div>

  <div class=\"summary\" id=\"summary\"></div>
  <div class=\"chart\"><svg id=\"chart\"></svg></div>
  <div class=\"chart\"><h3>Filtered data</h3><div id=\"tableWrap\"></div></div>
</main>
<div id=\"tooltip\" class=\"tooltip\"></div>
<script>
const rawData = {data_json};
const configs = [...new Set(rawData.map(d => d.config))].sort();
const cases = [...new Set(rawData.map(d => d.case_label))].sort();
const byCaseConfig = new Map(rawData.map(d => [d.case_label + '\\u0000' + d.config, d]));
const paramNames = ['sched', 'rfc', 'bank', 'wbd', 'reuse', 'ocs', 'regb', 'ocu', 'dp'];
const configParams = new Map(configs.map(config => [config, parseConfigParams(config)]));

function el(id) {{ return document.getElementById(id); }}
function fmt(n) {{ return Math.round(n).toLocaleString(); }}
function pct(n) {{ return (n >= 0 ? '+' : '') + n.toFixed(1) + '%'; }}
function isLrrBaseline(config) {{ return config.includes('sched_lrr') && config.includes('rfc0') && config.includes('ocu8'); }}

function parseConfigParams(config) {{
  const match = config.match(/sched_([^_]+)_rfc(\\d+)_bank(\\d+)_wbd(\\d+)_reuse(\\d+)_ocs(\\d+)_regb(\\d+)_ocu(\\d+)(?:_dp(\\d+))?/);
  if (!match) return null;
  const [, sched, rfc, bank, wbd, reuse, ocs, regb, ocu, dp = ''] = match;
  return {{sched, rfc, bank, wbd, reuse, ocs, regb, ocu, dp}};
}}

function paramValues(param) {{
  return [...new Set([...configParams.values()].filter(Boolean).map(params => params[param]))].sort();
}}

function configWithParamValue(config, param, value) {{
  const params = configParams.get(config);
  if (!params) return null;
  for (const candidate of configs) {{
    const candidateParams = configParams.get(candidate);
    if (!candidateParams || candidateParams[param] !== value) continue;
    let matched = true;
    for (const name of paramNames) {{
      if (name !== param && candidateParams[name] !== params[name]) matched = false;
    }}
    if (matched) return candidate;
  }}
  return null;
}}

function updateBaselineParamValues() {{
  const param = el('baselineParam').value;
  const current = el('baselineParamValue').value;
  const values = paramValues(param);
  fillSelect(el('baselineParamValue'), values, values.includes(current) ? current : values[0]);
}}

function fillSelect(select, values, selected) {{
  select.innerHTML = '';
  values.forEach(v => {{
    const opt = document.createElement('option');
    opt.value = v; opt.textContent = v;
    if (v === selected) opt.selected = true;
    select.appendChild(opt);
  }});
}}

function init() {{
  fillSelect(el('configA'), configs, configs[0]);
  fillSelect(el('configB'), configs, configs.find(isLrrBaseline) || configs[0]);
  fillSelect(el('baselineParam'), paramNames, 'rfc');
  updateBaselineParamValues();
  fillSelect(el('caseSelect'), cases, cases[0]);
  document.querySelectorAll('select,input').forEach(node => {{
    if (node.id !== 'baselineParam') node.addEventListener('input', render);
  }});
  el('baselineParam').addEventListener('input', () => {{ updateBaselineParamValues(); render(); }});
  el('downloadCsv').addEventListener('click', downloadCsv);
  render();
}}

function filteredCases() {{
  const needle = el('caseFilter').value.trim().toLowerCase();
  return cases.filter(c => !needle || c.toLowerCase().includes(needle));
}}

function sumCycles(config, caseList) {{
  return caseList.reduce((total, caseLabel) => {{
    const item = byCaseConfig.get(caseLabel + '\\u0000' + config);
    return total + (item ? item.cycles : 0);
  }}, 0);
}}

function parseParamFilter(text) {{
  const filters = {{}};
  for (const part of text.split(',')) {{
    const trimmed = part.trim();
    if (!trimmed) continue;
    const [rawKey, rawValue] = trimmed.split('=').map(s => s && s.trim());
    if (!paramNames.includes(rawKey) || rawValue == null || rawValue === '') continue;
    filters[rawKey] = rawValue;
  }}
  return filters;
}}

function configMatchesFilters(config, filters) {{
  const params = configParams.get(config);
  if (!params) return false;
  return Object.entries(filters).every(([key, value]) => params[key] === value);
}}

function matchingConfigs(text) {{
  const filters = parseParamFilter(text);
  return configs.filter(config => configMatchesFilters(config, filters));
}}

function groupCompareRows(groupAText, groupBText, caseList) {{
  const groupA = matchingConfigs(groupAText);
  const groupB = matchingConfigs(groupBText);
  const rows = [];
  let totalA = 0, totalB = 0, totalSamplesA = 0, totalSamplesB = 0;
  for (const caseLabel of caseList) {{
    let cyclesA = 0, cyclesB = 0, samplesA = 0, samplesB = 0;
    for (const config of groupA) {{
      const item = byCaseConfig.get(caseLabel + '\\u0000' + config);
      if (!item) continue;
      cyclesA += item.cycles;
      samplesA += 1;
    }}
    for (const config of groupB) {{
      const item = byCaseConfig.get(caseLabel + '\\u0000' + config);
      if (!item) continue;
      cyclesB += item.cycles;
      samplesB += 1;
    }}
    if (!samplesA || !samplesB || !cyclesB) continue;
    totalA += cyclesA;
    totalB += cyclesB;
    totalSamplesA += samplesA;
    totalSamplesB += samplesB;
    rows.push({{caseLabel, config: groupAText || 'ALL', baselineConfig: groupBText || 'ALL', cycles: cyclesA, baseline: cyclesB,
      deltaCycles: cyclesA - cyclesB, deltaPct: (cyclesA - cyclesB) / cyclesB * 100, ratio: cyclesA / cyclesB,
      label: `${{caseLabel}} | A:${{samplesA}} configs vs B:${{samplesB}} configs`}});
  }}
  if (totalB) rows.unshift({{caseLabel: 'ALL', config: groupAText || 'ALL', baselineConfig: groupBText || 'ALL', cycles: totalA, baseline: totalB,
    deltaCycles: totalA - totalB, deltaPct: (totalA - totalB) / totalB * 100, ratio: totalA / totalB,
    label: `ALL cases | A:${{totalSamplesA}} samples vs B:${{totalSamplesB}} samples`}});
  return rows;
}}

function parameterSummaryRows(param, baselineValue, caseList) {{
  const groups = new Map();
  for (const config of configs) {{
    const params = configParams.get(config);
    if (!params) continue;
    const value = params[param];
    if (!groups.has(value)) groups.set(value, {{configs: [], cycles: 0, samples: 0}});
    const group = groups.get(value);
    group.configs.push(config);
    for (const caseLabel of caseList) {{
      const item = byCaseConfig.get(caseLabel + '\\u0000' + config);
      if (!item) continue;
      group.cycles += item.cycles;
      group.samples += 1;
    }}
  }}
  const baseline = groups.get(baselineValue);
  const baselineAvg = baseline && baseline.samples ? baseline.cycles / baseline.samples : null;
  return [...groups.entries()].map(([value, group]) => {{
    const avg = group.samples ? group.cycles / group.samples : 0;
    return {{caseLabel: param, config: `${{param}}=${{value}}`, baselineConfig: baseline ? `${{param}}=${{baselineValue}}` : '',
      cycles: avg, baseline: baselineAvg, deltaCycles: baselineAvg == null ? null : avg - baselineAvg,
      deltaPct: baselineAvg ? (avg - baselineAvg) / baselineAvg * 100 : null,
      ratio: baselineAvg ? avg / baselineAvg : null,
      label: `${{param}}=${{value}} (${{group.configs.length}} configs, ${{group.samples}} samples)`,
      isBaseline: value === baselineValue}};
  }});
}}

function currentRows() {{
  const mode = el('mode').value;
  const configA = el('configA').value;
  const configB = el('configB').value;
  const selectedCase = el('caseSelect').value;
  const baselineParam = el('baselineParam').value;
  const baselineParamValue = el('baselineParamValue').value;
  const groupAFilter = el('groupAFilter').value;
  const groupBFilter = el('groupBFilter').value;
  let rows = [];
  if (mode === 'configCompare') {{
    for (const caseLabel of filteredCases()) {{
      const a = byCaseConfig.get(caseLabel + '\\u0000' + configA);
      const b = byCaseConfig.get(caseLabel + '\\u0000' + configB);
      if (!a || !b) continue;
      rows.push({{caseLabel, config: configA, baselineConfig: configB, cycles: a.cycles, baseline: b.cycles,
                 deltaCycles: a.cycles - b.cycles, deltaPct: (a.cycles - b.cycles) / b.cycles * 100, ratio: a.cycles / b.cycles, label: caseLabel}});
    }}
  }} else if (mode === 'groupCompare') {{
    rows = groupCompareRows(groupAFilter, groupBFilter, filteredCases());
  }} else if (mode === 'configTotals') {{
    const caseList = filteredCases();
    const baselineTotal = sumCycles(configB, caseList);
    rows = configs.map(config => {{
      const total = sumCycles(config, caseList);
      return {{caseLabel: 'ALL', config, baselineConfig: configB, cycles: total, baseline: baselineTotal,
        deltaCycles: total - baselineTotal, deltaPct: baselineTotal ? (total - baselineTotal) / baselineTotal * 100 : null,
        ratio: baselineTotal ? total / baselineTotal : null, label: config, isBaseline: config === configB}};
    }});
  }} else if (mode === 'paramSummary') {{
    rows = parameterSummaryRows(baselineParam, baselineParamValue, filteredCases());
  }} else if (mode === 'caseAllConfigs') {{
    rows = rawData.filter(d => d.case_label === selectedCase).map(d => ({{caseLabel: d.case_label, config: d.config, cycles: d.cycles, baseline: null, deltaPct: null, label: d.config}}));
  }} else if (mode === 'bestRelative') {{
    for (const caseLabel of filteredCases()) {{
      const items = rawData.filter(d => d.case_label === caseLabel);
      if (!items.length) continue;
      const best = items.reduce((a, b) => a.cycles <= b.cycles ? a : b);
      for (const d of items) rows.push({{caseLabel, config: d.config, baselineConfig: best.config, cycles: d.cycles, baseline: best.cycles,
        deltaCycles: d.cycles - best.cycles, deltaPct: (d.cycles - best.cycles) / best.cycles * 100, ratio: d.cycles / best.cycles, label: caseLabel + ' | ' + d.config, isBaseline: d.config === best.config}});
    }}
  }} else if (mode === 'selectedBaseline') {{
    for (const caseLabel of filteredCases()) {{
      const base = byCaseConfig.get(caseLabel + '\\u0000' + configB);
      if (!base) continue;
      const items = rawData.filter(d => d.case_label === caseLabel);
      for (const d of items) rows.push({{caseLabel, config: d.config, baselineConfig: configB, cycles: d.cycles, baseline: base.cycles,
        deltaCycles: d.cycles - base.cycles, deltaPct: (d.cycles - base.cycles) / base.cycles * 100, ratio: d.cycles / base.cycles, label: caseLabel + ' | ' + d.config, isBaseline: d.config === configB}});
    }}
  }} else if (mode === 'lrrBaseline') {{
    for (const caseLabel of filteredCases()) {{
      const items = rawData.filter(d => d.case_label === caseLabel);
      const base = items.find(d => isLrrBaseline(d.config));
      if (!base) continue;
      for (const d of items) rows.push({{caseLabel, config: d.config, baselineConfig: base.config, cycles: d.cycles, baseline: base.cycles,
        deltaCycles: d.cycles - base.cycles, deltaPct: (d.cycles - base.cycles) / base.cycles * 100, ratio: d.cycles / base.cycles, label: caseLabel + ' | ' + d.config, isBaseline: d.config === base.config}});
    }}
  }} else if (mode === 'paramBaseline') {{
    for (const d of rawData.filter(d => filteredCases().includes(d.case_label))) {{
      const baselineConfig = configWithParamValue(d.config, baselineParam, baselineParamValue);
      if (!baselineConfig || d.config === baselineConfig) continue;
      const base = byCaseConfig.get(d.case_label + '\\u0000' + baselineConfig);
      if (!base) continue;
      rows.push({{caseLabel: d.case_label, config: d.config, baselineConfig, cycles: d.cycles, baseline: base.cycles,
        deltaCycles: d.cycles - base.cycles, deltaPct: (d.cycles - base.cycles) / base.cycles * 100, ratio: d.cycles / base.cycles, label: d.case_label + ' | ' + d.config}});
    }}
  }}
  return sortRows(rows);
}}

function sortRows(rows) {{
  const mode = el('sortMode').value;
  const copy = [...rows];
  if (mode === 'case') copy.sort((a, b) => a.label.localeCompare(b.label));
  if (mode === 'cyclesDesc') copy.sort((a, b) => b.cycles - a.cycles);
  if (mode === 'cyclesAsc') copy.sort((a, b) => a.cycles - b.cycles);
  if (mode === 'deltaDesc') copy.sort((a, b) => (b.deltaPct ?? 0) - (a.deltaPct ?? 0));
  if (mode === 'deltaAsc') copy.sort((a, b) => (a.deltaPct ?? 0) - (b.deltaPct ?? 0));
  return copy;
}}

function scaled(value) {{
  if (el('scaleMode').value === 'log') return Math.log10(Math.max(1, value));
  return value;
}}

function renderSummary(rows) {{
  const values = rows.map(r => r.cycles);
  const min = Math.min(...values), max = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const ratioRows = rows.filter(r => r.ratio != null);
  const ratioSummary = ratioRows.length ? [['Avg ratio', (ratioRows.reduce((a, b) => a + b.ratio, 0) / ratioRows.length).toFixed(4)]] : [];
  el('summary').innerHTML = [
    ['Rows', rows.length], ['Min cycles', fmt(min)], ['Max cycles', fmt(max)], ['Avg cycles', fmt(avg)], ...ratioSummary
  ].map(([k,v]) => `<div class=\"card\"><div class=\"badge\">${{k}}</div><h3>${{v}}</h3></div>`).join('');
}}

function renderChart(rows) {{
  const svg = el('chart');
  const margin = {{left: 360, right: 130, top: 20, bottom: 40}};
  const rowH = 24;
  const width = 1500;
  const height = Math.max(180, rows.length * rowH + margin.top + margin.bottom);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  svg.innerHTML = '';
  if (!rows.length) return;
  const values = rows.map(r => r.deltaPct == null ? scaled(r.cycles) : r.deltaPct);
  const isDelta = rows.some(r => r.deltaPct != null);
  const minVal = isDelta ? Math.min(0, ...values) : 0;
  const maxVal = Math.max(...values, 1);
  const chartW = width - margin.left - margin.right;
  const x = v => margin.left + (v - minVal) / (maxVal - minVal || 1) * chartW;
  const zeroX = x(0);
  for (let i = 0; i < rows.length; i++) {{
    const y = margin.top + i * rowH;
    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bg.setAttribute('x', 0); bg.setAttribute('y', y); bg.setAttribute('width', width); bg.setAttribute('height', rowH);
    bg.setAttribute('fill', i % 2 === 0 ? '#f2f2f2' : '#fff');
    svg.appendChild(bg);
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', 0); line.setAttribute('x2', width); line.setAttribute('y1', y + rowH); line.setAttribute('y2', y + rowH);
    line.setAttribute('stroke', '#ddd'); svg.appendChild(line);
  }}
  const axis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  axis.setAttribute('x1', zeroX); axis.setAttribute('x2', zeroX); axis.setAttribute('y1', margin.top); axis.setAttribute('y2', height - margin.bottom);
  axis.setAttribute('stroke', '#222'); svg.appendChild(axis);

  rows.forEach((r, i) => {{
    const y = margin.top + i * rowH + 4;
    const value = r.deltaPct == null ? scaled(r.cycles) : r.deltaPct;
    const x0 = isDelta ? zeroX : margin.left;
    const x1 = x(value);
    const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bar.setAttribute('x', Math.min(x0, x1)); bar.setAttribute('y', y); bar.setAttribute('width', Math.abs(x1 - x0)); bar.setAttribute('height', rowH - 8);
    bar.setAttribute('fill', r.isBaseline ? '#1f77b4' : (isDelta ? (value >= 0 ? '#d62728' : '#2ca02c') : '#607d8b'));
    bar.addEventListener('mousemove', e => showTip(e, r));
    bar.addEventListener('mouseleave', hideTip);
    svg.appendChild(bar);
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', 8); label.setAttribute('y', y + 13); label.setAttribute('font-size', '11');
    label.setAttribute('fill', r.isBaseline ? '#1565c0' : '#222');
    label.setAttribute('font-weight', r.isBaseline ? '700' : '400');
    label.textContent = r.label + (r.isBaseline ? ' [BASE]' : ''); svg.appendChild(label);
    const valText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    valText.setAttribute('x', value >= 0 ? Math.max(x0, x1) + 5 : Math.min(x0, x1) - 5);
    valText.setAttribute('y', y + 13); valText.setAttribute('font-size', '11');
    valText.setAttribute('text-anchor', value >= 0 ? 'start' : 'end');
    valText.textContent = isDelta ? pct(value) : fmt(r.cycles); svg.appendChild(valText);
  }});
}}

function showTip(e, r) {{
  const t = el('tooltip');
  t.style.display = 'block'; t.style.left = e.clientX + 12 + 'px'; t.style.top = e.clientY + 12 + 'px';
  t.innerHTML = `<b>${{r.caseLabel}}</b><br>${{r.config}}<br>cycles: ${{fmt(r.cycles)}}` +
    (r.baseline ? `<br>baseline: ${{r.baselineConfig}} (${{fmt(r.baseline)}})${{r.deltaCycles == null ? '' : `<br>delta cycles: ${{fmt(r.deltaCycles)}}`}}<br>delta: ${{pct(r.deltaPct)}}${{r.ratio == null ? '' : `<br>ratio: ${{r.ratio.toFixed(4)}}`}}` : '');
}}
function hideTip() {{ el('tooltip').style.display = 'none'; }}

function renderTable(rows) {{
  const html = ['<table><thead><tr><th>case</th><th>config</th><th>cycles</th><th>baseline config</th><th>baseline cycles</th><th>delta cycles</th><th>ratio</th><th>delta %</th></tr></thead><tbody>'];
  for (const r of rows) html.push(`<tr><td>${{r.caseLabel}}</td><td>${{r.config}}${{r.isBaseline ? ' <span class=\"baseline\">[BASE]</span>' : ''}}</td><td>${{fmt(r.cycles)}}</td><td>${{r.baselineConfig || ''}}</td><td>${{r.baseline ? fmt(r.baseline) : ''}}</td><td>${{r.deltaCycles == null ? '' : fmt(r.deltaCycles)}}</td><td>${{r.ratio == null ? '' : r.ratio.toFixed(4)}}</td><td class=\"${{(r.deltaPct ?? 0) >= 0 ? 'positive' : 'negative'}}\">${{r.deltaPct == null ? '' : pct(r.deltaPct)}}</td></tr>`);
  html.push('</tbody></table>');
  el('tableWrap').innerHTML = html.join('');
}}

function render() {{
  const rows = currentRows();
  renderSummary(rows);
  renderChart(rows);
  renderTable(rows);
}}

function downloadCsv() {{
  const rows = currentRows();
  const header = ['case','config','cycles','baseline_config','baseline_cycles','delta_cycles','ratio','delta_pct'];
  const lines = [header.join(',')];
  for (const r of rows) lines.push([r.caseLabel, r.config, r.cycles, r.baselineConfig || '', r.baseline || '', r.deltaCycles == null ? '' : r.deltaCycles, r.ratio == null ? '' : r.ratio.toFixed(6), r.deltaPct == null ? '' : r.deltaPct.toFixed(4)].map(v => '"' + String(v).replaceAll('"','""') + '"').join(','));
  const blob = new Blob([lines.join('\\n')], {{type: 'text/csv'}});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'cycle_dashboard_filtered.csv'; a.click();
}}

init();
</script>
</body>
</html>"""


def main(selected_result_path):
    root = resolve_result_dir(selected_result_path)
    if not root.exists():
        raise SystemExit(f"Result directory does not exist: {root}")
    records = find_case_logs(root)
    if not records:
        raise SystemExit(f"No case .log with gpu_tot_sim_cycle found under: {root}")
    output_dir = root / "confluence"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "cycle_dashboard.html"
    output_path.write_text(render_dashboard(records, root), encoding="utf-8")
    print(f"Wrote dashboard: {output_path}")
    print(f"Records: {len(records)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an interactive HTML dashboard for gpu_tot_sim_cycle analysis.")
    parser.add_argument("result_dir", nargs="?",
                        help="Completed result directory to scan. Overrides result_path when provided.")
    args = parser.parse_args()
    selected_result_path = args.result_dir or result_path
    if not selected_result_path:
        parser.error("set result_path in this script or pass result_dir on the command line")
    main(selected_result_path)
