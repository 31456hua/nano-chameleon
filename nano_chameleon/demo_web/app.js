"use strict";
const $ = id => document.getElementById(id);
let token, mode = "manual", state, busy = false, selected = -1, live = null;
let revision = 0, timer, playing, loadRevision = 0, targetTitle = "", uploaded = false;
const controls = [["diameter", "diameter_nm"], ["index", "n_real"], ["absorption", "k"]];
const labels = {inspect_experiment: "检查目标", simulate_candidate: "试算候选", search_candidates: "搜索候选", validate_unseen_wavelengths: "锁定并验证", export_experiment_report: "导出报告", mcp_manage: "工具发现"};
const fmt = value => value == null ? "—" : Number(value).toExponential(3);
const percent = value => (value && value < 1e-4 ? value.toExponential(3) : value.toFixed(4)) + "%";
const icons = () => lucide.createIcons();
function error(message = "") { $("error").textContent = message; }
function parameters() {
  return Object.fromEntries(controls.map(([id, field]) => [field, Number($(id + "-number").value)]));
}
function setParameters(trial) {
  if (!trial) return;
  controls.forEach(([id, field]) => { $(id).value = trial[field]; $(id + "-number").value = Number(trial[field].toFixed(6)); });
}
async function request(operation, data = {}) {
  const response = await fetch("/api/" + operation, {method: "POST", headers: {"Content-Type": "application/json", "X-Demo-Token": token}, body: JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "请求失败");
  return result;
}
function stop() {
  clearInterval(playing); playing = null;
  $("play").innerHTML = '<i data-lucide="play"></i>'; icons();
}
function disable() {
  const locked = !state || mode === "agh" || state.sealed || busy;
  controls.forEach(([id]) => { $(id).disabled = locked; $(id + "-number").disabled = locked; });
  $("record").disabled = locked;
  $("search").disabled = locked;
  $("validate").disabled = locked || !state?.trial_count;
  $("export").disabled = busy || !state?.sealed;
  ["new-run", "upload", "target", "manual-tab", "agh-tab"].forEach(id => $(id).disabled = busy);
  ["previous", "next", "play", "trial-slider"].forEach(id => $(id).disabled = busy || !state?.trial_count);
  $("search").innerHTML = `<i data-lucide="locate-fixed"></i>${busy ? "处理中…" : "数值搜索 · 5 代"}`;
  icons();
}
const plotConfig = {responsive: true, displayModeBar: false, scrollZoom: false};
function drawSpectrum() {
  if (!state) return;
  const training = state.training;
  const traces = [{x: training.map(p => p.wavelength_nm), y: training.map(p => p.qsca), mode: "markers", name: "训练目标", marker: {color: "#b74368", size: 6}}];
  const trial = state.trials[selected];
  let x = training.map(p => p.wavelength_nm), y = live?.curve || trial?.curve;
  if (!live && trial && state.final?.best_trial === trial.trial) {
    x = [...training.map(p => p.wavelength_nm), ...state.final.holdout.map(p => p.wavelength_nm)].sort((a, b) => a - b);
    y = state.final.predicted_full_curve;
  }
  if (y) traces.push({x, y, mode: "lines", name: "候选曲线", line: {color: "#13887d", width: 2.5}});
  if (state.final) traces.push({x: state.final.holdout.map(p => p.wavelength_nm), y: state.final.holdout.map(p => p.observed_qsca), mode: "markers", name: "留出目标", marker: {color: "#cc7735", symbol: "diamond", size: 8}});
  Plotly.react("spectrum", traces, {margin: {l: 52, r: 12, t: 12, b: 46}, showlegend: false, paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: {family: "Arial, Microsoft YaHei, sans-serif", size: 12, color: "#616e6c"}, xaxis: {title: {text: "波长 / nm"}, gridcolor: "#edf0ef", zeroline: false}, yaxis: {title: {text: "Qsca"}, gridcolor: "#edf0ef", rangemode: "tozero", zeroline: false}}, plotConfig);
}
function drawConvergence() {
  let best = Infinity;
  const values = state.trials.map(t => { best = Math.min(best, t.train_rmse); return Math.max(best, 1e-12); });
  Plotly.react("convergence", [{x: state.trials.map(t => t.trial), y: values, mode: "lines", line: {color: "#13887d", width: 2}, fill: "none"}], {margin: {l: 60, r: 12, t: 12, b: 34}, showlegend: false, paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: {family: "Arial, Microsoft YaHei, sans-serif", size: 11, color: "#616e6c"}, xaxis: {title: {text: "候选序号"}, gridcolor: "#edf0ef", zeroline: false}, yaxis: {type: "log", gridcolor: "#edf0ef", title: {text: "RMSE"}}}, plotConfig);
}
function colour(result) {
  $("colour-patch").style.background = result.hex;
  $("colour-patch").style.color = result.relative_luminance > .35 ? "#1d3330" : "#fff";
  $("colour-hex").textContent = result.hex.toUpperCase();
  $("colour-state").textContent = result.gamut_clipped ? "超出 sRGB（屏幕色域）· 已裁剪" : "D65（标准日光）透射示意";
}
async function preview() {
  const rev = ++revision;
  if (!state) return;
  const data = {run_id: state.run_id, ...parameters(), n_env: state.n_env, optical_depth: Number($("optical-depth").value)};
  try {
    if (mode === "manual" && !state.sealed) {
      const result = await request("preview", data);
      if (rev !== revision) return;
      live = result; selected = -1; colour(result.colour);
      $("parameter-state").textContent = "未记录";
      $("trial-label").textContent = "实时预览";
      drawSpectrum();
    } else {
      const result = await request("colour", data);
      if (rev === revision) colour(result);
    }
  } catch (e) { if (rev === revision) error(e.message); }
}
function schedulePreview() { clearTimeout(timer); timer = setTimeout(preview, 180); }
function choose(index, updateColour = true) {
  if (!state?.trials.length) return;
  ++revision; clearTimeout(timer); selected = Math.max(0, Math.min(index, state.trials.length - 1)); live = null;
  const trial = state.trials[selected]; setParameters(trial);
  $("trial-slider").value = selected;
  $("trial-label").textContent = `#${trial.trial} / ${state.trial_count}`;
  $("parameter-state").textContent = `候选 #${trial.trial}`;
  drawSpectrum();
  if (updateColour) {
    const rev = revision;
    request("colour", {...parameters(), n_env: state.n_env, optical_depth: Number($("optical-depth").value)}).then(c => { if (rev === revision) colour(c); }).catch(e => error(e.message));
  }
}
function proof() {
  $("events").replaceChildren();
  if (mode !== "agh") return;
  const ev = state.evidence;
  $("session-link").href = ev.session_url;
  $("evidence-status").textContent = `${ev.verified ? "执行链核验通过" : "执行链未通过核验"} · ${ev.models.join(", ")} · ${ev.recoveries.length} 次会话恢复。原记录只读；不代表当前实时运行。`;
  $("validation-note").textContent = `留出 NRMSE（归一化均方根误差）${percent(ev.holdout_nrmse * 100)} / 预设标准 ${(ev.limit_nrmse * 100).toFixed(0)}%：${ev.criterion_met ? "达到光谱标准" : "未达标准，保留模型失配结果"}。NRMSE = 留出 RMSE（均方根误差）/ 训练目标 RMS（均方根幅值）。`;
  ev.events.filter(e => e.type === "tool/call").forEach(call => {
    const result = ev.events.find(e => e.type === "tool/result" && e.tool_use_id === call.tool_use_id);
    const details = document.createElement("details"), summary = document.createElement("summary"), pre = document.createElement("pre");
    summary.textContent = `${String(call.seq).padStart(3, "0")} · ${labels[call.tool] || call.tool} · ${result && !result.is_error ? "完成" : "需检查"}`;
    pre.textContent = JSON.stringify({arguments: call.args, result: result?.result, error: result?.is_error}, null, 2);
    details.append(summary, pre); $("events").append(details);
  });
}
function render() {
  const agh = mode === "agh";
  $("manual-tab").classList.toggle("active", !agh); $("agh-tab").classList.toggle("active", agh);
  $("manual-tab").setAttribute("aria-selected", String(!agh)); $("agh-tab").setAttribute("aria-selected", String(agh));
  $("manual-target-tools").hidden = agh; $("evidence-section").hidden = !agh;
  $("source-badge").textContent = agh ? "真实记录" : "手动仿真";
  $("executor").textContent = agh ? "AGH / Agnes 历史执行" : "手动仿真 / MiePython";
  $("execution-source").textContent = agh ? "Agnes" : "手动";
  $("run-title").textContent = targetTitle;
  document.querySelector(".sidebar section .scientific-note").textContent = `${uploaded ? "用户光谱" : "合成目标"} · 均匀球体拟合 · 波段内恒定 n、k`;
  $("run-id").textContent = state.run_id;
  $("run-state").textContent = state.sealed ? "已锁定验证" : "仅训练波长";
  $("train-count").textContent = state.training.length;
  $("holdout-count").textContent = state.holdout_count;
  $("n-env").textContent = state.n_env.toFixed(2);
  $("trial-count").textContent = state.trial_count;
  $("train-error").textContent = fmt(state.best_trial?.train_rmse);
  $("holdout-error").textContent = state.final ? fmt(state.final.holdout_rmse) : "未揭盲";
  $("validation-note").textContent = state.sealed ? "已锁定最佳训练候选；已揭盲的波长只用于最终验证。" : "最终验证锁定最佳训练候选，才公开留出目标。";
  $("trial-slider").max = Math.max(0, state.trial_count - 1);
  $("candidates").replaceChildren();
  if (!state.candidates.length) $("candidates").innerHTML = '<tr><td colspan="4" class="empty">尚无已记录候选</td></tr>';
  state.candidates.forEach(t => {
    const row = document.createElement("tr"), cell = document.createElement("td"), button = document.createElement("button");
    button.textContent = `#${t.trial}`; button.title = "查看此候选曲线"; button.onclick = () => { stop(); choose(t.trial - 1); };
    cell.append(button); row.append(cell);
    [t.diameter_nm.toFixed(2), `${t.n_real.toFixed(4)} / ${t.k.toFixed(5)}`, fmt(t.train_rmse)].forEach(text => { const td = document.createElement("td"); td.textContent = text; row.append(td); });
    $("candidates").append(row);
  });
  drawConvergence(); proof(); disable();
  if (state.trial_count) choose(state.best_trial.trial - 1); else { selected = -1; live = null; drawSpectrum(); preview(); }
}
async function run(task) {
  if (busy) return;
  stop(); ++revision; clearTimeout(timer); busy = true; error(); disable();
  try { await task(); } catch (e) { error(e.message); }
  finally { busy = false; disable(); }
}
async function load(csv, filename, desiredMode = mode) {
  const rev = ++loadRevision;
  await run(async () => {
    const result = desiredMode === "agh" ? await fetch("/api/evidence/" + $("target").value).then(async r => { const d = await r.json(); if (!r.ok) throw new Error(d.error); return d; }) : await request("create", csv == null ? {case: $("target").value} : {csv});
    if (rev !== loadRevision) return;
    mode = desiredMode; state = result; targetTitle = filename || $("target").selectedOptions[0].textContent; uploaded = Boolean(filename); render();
  });
}
controls.forEach(([id]) => {
  [id, id + "-number"].forEach(input => $(input).addEventListener("input", () => {
    stop(); error(); $(input === id ? id + "-number" : id).value = $(input).value; schedulePreview();
  }));
});
$("optical-depth").addEventListener("input", () => { $("depth-value").textContent = Number($("optical-depth").value).toFixed(2); schedulePreview(); });
$("target").onchange = () => load(); $("new-run").onclick = () => load();
$("upload").onchange = async () => {
  const file = $("upload").files[0]; if (!file) return;
  if (file.size > 110000) { error("CSV 文件过大"); return; }
  await load(await file.text(), file.name); $("upload").value = "";
};
$("manual-tab").onclick = () => { if (mode !== "manual") load(undefined, undefined, "manual"); };
$("agh-tab").onclick = () => { if (mode !== "agh") load(undefined, undefined, "agh"); };
$("record").onclick = () => run(async () => { state = await request("trial", {run_id: state.run_id, ...parameters()}); render(); choose(state.trial_count - 1); });
$("search").onclick = () => run(async () => { state = await request("search", {run_id: state.run_id}); render(); });
$("validate").onclick = () => $("validation-dialog").showModal();
$("cancel-validation").onclick = () => $("validation-dialog").close();
$("confirm-validation").onclick = () => { $("validation-dialog").close(); run(async () => { state = await request("validate", {run_id: state.run_id}); render(); }); };
$("export").onclick = () => {
  const view = window.open("about:blank", "_blank"); if (view) view.opener = null;
  run(async () => { const url = mode === "agh" ? "/evidence-report/" + $("target").value : (await request("report", {run_id: state.run_id})).url; if (view) view.location = url; else error("浏览器阻止了报告窗口，请允许本页打开窗口。"); });
};
$("previous").onclick = () => { stop(); choose(selected - 1); }; $("next").onclick = () => { stop(); choose(selected + 1); };
$("trial-slider").oninput = () => { stop(); choose(Number($("trial-slider").value)); };
$("play").onclick = () => {
  if (playing) { stop(); choose(selected); return; }
  if (selected >= state.trial_count - 1) choose(0, false);
  $("play").innerHTML = '<i data-lucide="pause"></i>'; icons();
  playing = setInterval(() => {
    choose(selected + Math.max(1, Math.ceil(state.trial_count / 80)), false);
    if (selected === state.trial_count - 1) { stop(); choose(selected); }
  }, 180);
};
async function init() {
  icons(); disable();
  try { const config = await fetch("/api/config").then(r => r.json()); token = config.token; await load(); } catch (e) { error(e.message); }
}
init();
