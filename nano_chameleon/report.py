"""Generate a standalone, interactive experiment report."""

from __future__ import annotations

import json
from pathlib import Path


def write_report(record, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['run_id']}.html"
    data = json.dumps(record, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__EXPERIMENT_JSON__", data)
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>纳米变色龙 | 实验报告</title>
<style>
:root { color-scheme: light; font-family: system-ui, "Microsoft YaHei", sans-serif; color: #1b2630; background: #f4f7f6; }
* { box-sizing: border-box; }
body { margin: 0; }
header { background: #153f45; color: white; padding: 26px max(24px, calc((100vw - 1160px)/2)); }
h1 { font-size: 27px; margin: 0 0 7px; font-weight: 700; }
header p { margin: 0; color: #d4e9e7; font-size: 14px; }
main { max-width: 1160px; margin: auto; padding: 28px 24px 50px; }
.summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 28px; }
.metric { background: white; border: 1px solid #dbe4e2; border-radius: 7px; padding: 17px; min-height: 90px; }
.metric small { display: block; color: #5b6d72; margin-bottom: 8px; }
.metric strong { font-size: 21px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
section { margin-top: 28px; }
h2 { font-size: 19px; margin: 0 0 14px; }
.plot { background: white; border: 1px solid #dbe4e2; border-radius: 7px; padding: 14px; }
svg { display: block; width: 100%; height: 380px; }
.legend { display: flex; gap: 20px; flex-wrap: wrap; margin: 9px 0 0 48px; font-size: 13px; color: #40565e; }
.legend span::before { content: ""; display: inline-block; width: 16px; height: 3px; vertical-align: middle; margin-right: 7px; background: var(--line); }
.controls { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
input[type=range] { width: min(420px, 55vw); accent-color: #0f7777; }
label, output { font-size: 14px; }
table { width: 100%; border-collapse: collapse; background: white; font-size: 13px; }
th, td { padding: 9px 12px; border-bottom: 1px solid #e6eceb; text-align: right; font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
th { background: #e9f0ef; color: #38565d; }
.table-wrap { overflow-x: auto; border: 1px solid #dbe4e2; border-radius: 7px; }
.note { color: #556c70; font-size: 13px; line-height: 1.6; }
@media (max-width: 700px) { .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } svg { height: 300px; } header { padding: 22px 24px; } .metric strong { font-size: 17px; } }
</style>
</head>
<body>
<header><h1>纳米变色龙</h1><p>球形颗粒反向设计 · Mie 散射试验记录 · 留出波长验证</p></header>
<main>
<div class="summary" id="summary"></div>
<section><h2>最佳参数与盲测</h2><div class="plot"><svg id="final-chart" role="img" aria-label="目标与拟合散射光谱"></svg><div class="legend"><span style="--line:#153f45">训练目标</span><span style="--line:#d06a43">留出目标</span><span style="--line:#0c8a83">最佳拟合</span></div></div></section>
<section><h2>逐次试验</h2><div class="controls"><label for="trial-select">试验序号</label><input id="trial-select" type="range" min="1"><output id="trial-label"></output></div><div class="plot"><svg id="trial-chart" role="img" aria-label="逐次试验散射曲线"></svg><div class="legend"><span style="--line:#153f45">训练目标</span><span style="--line:#869da2">当前试验</span><span style="--line:#0c8a83">截至当前最佳</span></div></div></section>
<section><h2>留出波长逐点结果</h2><div class="table-wrap"><table><thead><tr><th>波长 nm</th><th>目标 Qsca</th><th>预测 Qsca</th><th>绝对误差</th></tr></thead><tbody id="holdout-table"></tbody></table></div></section>
<p class="note">假设：均匀球形颗粒，复折射率 n - i k 在全部波长上恒定。Qsca 为无量纲散射效率。留出点在搜索期间不计入误差；盲测后本次实验锁定。</p>
</main>
<script>
const data = __EXPERIMENT_JSON__;
const hold = new Set(data.holdout_indices);
const train = data.target.filter((_, i) => !hold.has(i));
const held = data.target.filter((_, i) => hold.has(i));
const best = data.trials.find(t => t.trial === data.final.best_trial);
const format = x => Number(x).toFixed(4);
const formatError = x => x > 0 && x < 0.001 ? Number(x).toExponential(2) : format(x);
document.getElementById('summary').innerHTML = [
  ['粒径', `${format(best.diameter_nm)} nm`],
  ['复折射率', `${format(best.n_real)} - i ${format(best.k)}`],
  ['训练 RMSE', formatError(data.final.train_rmse)],
  ['留出 RMSE', formatError(data.final.holdout_rmse)]
].map(([label, value]) => `<div class="metric"><small>${label}</small><strong>${value}</strong></div>`).join('');
document.getElementById('holdout-table').innerHTML = data.final.holdout.map(p =>
  `<tr><td>${format(p.wavelength_nm)}</td><td>${format(p.observed_qsca)}</td><td>${format(p.predicted_qsca)}</td><td>${formatError(Math.abs(p.observed_qsca-p.predicted_qsca))}</td></tr>`
).join('');
function draw(id, series) {
  const svg = document.getElementById(id);
  const width = Math.round(svg.clientWidth), height = Math.round(svg.clientHeight);
  const mobile = width < 600, left = mobile ? 46 : 62, right = 14, top = 20, bottom = 48;
  const points = series.flatMap(s => s.points);
  const xmin = Math.min(...points.map(p => p[0])), xmax = Math.max(...points.map(p => p[0]));
  const ymin = 0, ymax = Math.max(0.1, ...points.map(p => p[1])) * 1.12;
  const x = v => left + (v-xmin)/(xmax-xmin)*(width-left-right);
  const y = v => height-bottom - (v-ymin)/(ymax-ymin)*(height-top-bottom);
  let content = `<rect width="${width}" height="${height}" fill="white"/>`;
  for (let i=0;i<=4;i++) {
    const v = ymin+(ymax-ymin)*i/4, yy=y(v);
    content += `<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" stroke="#e7eeec"/><text x="${left-10}" y="${yy+4}" text-anchor="end" fill="#63777b" font-size="12">${v.toFixed(2)}</text>`;
  }
  const ticks = mobile ? 3 : 5;
  for (let i=0;i<=ticks;i++) {
    const v=xmin+(xmax-xmin)*i/ticks, xx=x(v);
    content += `<text x="${xx}" y="${height-14}" text-anchor="middle" fill="#63777b" font-size="12">${v.toFixed(0)}</text>`;
  }
  content += `<text x="${width/2}" y="${height-1}" text-anchor="middle" fill="#40565e" font-size="12">波长 (nm)</text><text transform="translate(16 ${height/2}) rotate(-90)" text-anchor="middle" fill="#40565e" font-size="12">Qsca</text>`;
  for (const s of series) {
    if (s.line) content += `<polyline fill="none" stroke="${s.color}" stroke-width="2.5" points="${s.points.map(p => `${x(p[0])},${y(p[1])}`).join(' ')}"/>`;
    if (s.dots) content += s.points.map(p => `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="3.5" fill="${s.color}"/>`).join('');
  }
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.innerHTML = content;
}
const finalSeries = [
  {points: train, color:'#153f45', dots:true},
  {points: held, color:'#d06a43', dots:true},
  {points: data.target.map((p,i) => [p[0], data.final.predicted_full_curve[i]]), color:'#0c8a83', line:true}
];
draw('final-chart', finalSeries);
const select = document.getElementById('trial-select');
select.max = data.trials.length;
select.value = data.trials.length;
function showTrial() {
  const index = Number(select.value)-1, trial = data.trials[index];
  const bestSoFar = data.trials.slice(0,index+1).reduce((a,b) => a.train_rmse < b.train_rmse ? a : b);
  document.getElementById('trial-label').textContent = `${trial.trial} / ${data.trials.length} · 粒径 ${format(trial.diameter_nm)} nm · n ${format(trial.n_real)} · k ${format(trial.k)} · RMSE ${formatError(trial.train_rmse)}`;
  draw('trial-chart', [
    {points: train, color:'#153f45', dots:true},
    {points: train.map((p,i) => [p[0],trial.curve[i]]), color:'#869da2', line:true},
    {points: train.map((p,i) => [p[0],bestSoFar.curve[i]]), color:'#0c8a83', line:true}
  ]);
}
select.addEventListener('input', showTrial);
showTrial();
window.addEventListener('resize', () => { draw('final-chart', finalSeries); showTrial(); });
</script>
</body>
</html>"""
