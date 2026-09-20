const fmtPct = (value, digits = 1) => value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
const fmtUsd = (value, lowerBound = false) => `${lowerBound ? "≥" : ""}$${value.toFixed(3)}`;
const fmtMs = value => value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
const modelColor = id => id === "jev" ? "var(--cyan)" : "var(--amber)";

function renderModels(models, caseCount) {
  const grid = document.querySelector("#model-grid");
  const template = document.querySelector("#model-card-template");
  grid.replaceChildren();
  models.forEach(model => {
    const card = template.content.firstElementChild.cloneNode(true);
    card.dataset.model = model.id;
    card.querySelector(".model-kicker").textContent = model.id === "jev" ? "DECISION MODEL" : "GENERAL LLM";
    card.querySelector("h3").textContent = model.name;
    card.querySelector(".coverage-badge").textContent = `${model.completed}/${caseCount}`;
    card.querySelector(".primary-score strong").textContent = model.overall?.f1?.toFixed(3) ?? "—";
    card.querySelector(".recall").textContent = fmtPct(model.overall?.recall);
    card.querySelector(".precision").textContent = fmtPct(model.overall?.precision);
    card.querySelector(".latency").textContent = `P50 ${fmtMs(model.latency.p50)}`;
    card.querySelector(".cost").textContent = `${fmtUsd(model.costPerThousandUsd, model.costIsLowerBound)} / 1k`;
    grid.append(card);
  });
}

function renderTradeoffs(models) {
  const byId = Object.fromEntries(models.map(model => [model.id, model]));
  const jev = byId.jev;
  const deepseek = byId.deepseek;
  const f1Lead = (jev.overall.f1 - deepseek.overall.f1) * 100;
  const speedup = deepseek.latency.p50 / jev.latency.p50;
  const costRatio = deepseek.costPerThousandUsd / jev.costPerThousandUsd;
  document.querySelector("#headline-insight").textContent = `Jev 的总体 F1 高 ${f1Lead.toFixed(1)} 个百分点，响应快 ${speedup.toFixed(1)}×`;
  document.querySelector("#insight-copy").textContent = `Jev 的每千条已知成本也更低，约为 DeepSeek 的 ${(1 / costRatio).toFixed(1)}×。DeepSeek 的精确率更高，Jev 的召回率更高：两者适合不同的漏审与误杀约束。`;
  document.querySelector("#legend").innerHTML = models.map(model => `<span style="--legend:${modelColor(model.id)}">${model.name}</span>`).join("");

  const metrics = [
    { label: "总体 F1", values: models.map(model => model.overall.f1), format: value => value.toFixed(3), higher: true },
    { label: "P50 延迟", values: models.map(model => model.latency.p50), format: fmtMs, higher: false },
    { label: "每千条成本", values: models.map(model => model.costPerThousandUsd), format: value => `$${value.toFixed(3)}`, higher: false },
  ];
  const root = document.querySelector("#metric-rows");
  root.innerHTML = metrics.map(metric => {
    const max = Math.max(...metric.values);
    return `<div class="metric-row"><header><span>${metric.label}</span><b>${models.map((model, i) => `${model.name} ${metric.format(metric.values[i])}`).join(" · ")}</b></header><div class="metric-bars">${models.map((model, i) => `<div class="metric-bar" style="--bar:${modelColor(model.id)}"><i style="width:${Math.max(5, metric.values[i] / max * 100)}%"></i><span>${model.name}</span></div>`).join("")}</div></div>`;
  }).join("");
}

function renderCategories(benchmark, metric = "f1") {
  const [first, second] = benchmark.models;
  const rows = benchmark.directions
    .filter(direction => direction.id !== "unsafe_overall")
    .sort((a, b) => b.support - a.support);
  document.querySelector("#category-chart").innerHTML = rows.map(direction => {
    const a = direction.metrics[first.id]?.[metric];
    const b = direction.metrics[second.id]?.[metric];
    const delta = (a ?? 0) - (b ?? 0);
    const deltaClass = Math.abs(delta) < .0005 ? "neutral" : delta > 0 ? "positive" : "negative";
    const deltaText = a == null || b == null ? "N/A" : `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)} pp`;
    return `<div class="category-row"><div class="category-name"><strong>${direction.name}</strong><small>n+ ${direction.support}</small></div><div class="dual-bars"><div class="thin-bar" title="${first.name}: ${fmtPct(a)}"><i style="width:${(a ?? 0) * 100}%;--bar:${modelColor(first.id)}"></i></div><div class="thin-bar" title="${second.name}: ${fmtPct(b)}"><i style="width:${(b ?? 0) * 100}%;--bar:${modelColor(second.id)}"></i></div></div><div class="category-result"><span>${fmtPct(a)} · ${fmtPct(b)}</span><b class="category-delta ${deltaClass}" title="${first.name} 减 ${second.name}">${deltaText}</b></div></div>`;
  }).join("");
}

async function init() {
  try {
    const response = await fetch("data/benchmarks.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const benchmark = payload.benchmarks[0];
    const coverage = benchmark.pairedCoverage;
    document.querySelector("#header-status").textContent = benchmark.status === "complete" ? "批次完整" : "批次已结束 · 有缺失";
    document.querySelector("#dataset-name").textContent = benchmark.datasetName;
    document.querySelector("#coverage-value").textContent = fmtPct(coverage, 2);
    document.querySelector("#coverage-bar").style.width = `${coverage * 100}%`;
    const missing = benchmark.caseCount - benchmark.pairedCompleted;
    document.querySelector("#coverage-note").textContent = `${benchmark.pairedCompleted.toLocaleString()} / ${benchmark.caseCount.toLocaleString()} 条完成双模型配对${missing ? `，${missing} 条存在结构化输出缺失` : ""}。`;
    document.querySelector("#run-id").textContent = benchmark.runId;
    document.querySelector("#taxonomy").textContent = benchmark.taxonomyVersion;
    document.querySelector("#updated-at").textContent = new Date(benchmark.updatedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
    renderModels(benchmark.models, benchmark.caseCount);
    renderTradeoffs(benchmark.models);
    renderCategories(benchmark);
    document.querySelector("#metric-select").addEventListener("change", event => renderCategories(benchmark, event.target.value));
  } catch (error) {
    document.querySelector("#model-grid").innerHTML = `<div class="error-state">数据载入失败：${error.message}</div>`;
    document.querySelector("#header-status").textContent = "数据不可用";
  }
}

init();
