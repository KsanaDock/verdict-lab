const fmtPct = (value, digits = 1) => value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
const fmtUsd = (value, lowerBound = false) => `${lowerBound ? "≥" : ""}$${value.toFixed(3)}`;
const fmtMs = value => value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
const fmtCompact = value => value >= 1_000_000 ? `${(value / 1_000_000).toFixed(2)}M` : value.toLocaleString("zh-CN");
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
    card.querySelector(".primary-score strong").textContent = model.headline?.f1?.toFixed(3) ?? "—";
    card.querySelector(".primary-score span").innerHTML = `F1<br>${model.headlineLabel}`;
    card.querySelector(".recall").textContent = fmtPct(model.headline?.recall);
    card.querySelector(".precision").textContent = fmtPct(model.headline?.precision);
    card.querySelector(".latency").textContent = `P50 ${fmtMs(model.latency.p50)}`;
    card.querySelector(".cost").textContent = `${fmtUsd(model.costPerThousandUsd, model.costIsLowerBound)} / 1k`;
    grid.append(card);
  });
}

function renderTradeoffs(models) {
  const byId = Object.fromEntries(models.map(model => [model.id, model]));
  const jev = byId.jev;
  const deepseek = byId.deepseek;
  const f1Lead = (jev.headline.f1 - deepseek.headline.f1) * 100;
  const speedup = deepseek.latency.p50 / jev.latency.p50;
  const costRatio = deepseek.costPerThousandUsd / jev.costPerThousandUsd;
  const leadName = f1Lead >= 0 ? jev.name : deepseek.name;
  document.querySelector("#headline-insight").textContent = `${leadName} 的 F1 高 ${Math.abs(f1Lead).toFixed(1)} 个百分点；Jev 响应快 ${speedup.toFixed(1)}×`;
  document.querySelector("#insight-copy").textContent = `Jev 的每千条已知成本也更低，约为 DeepSeek 的 ${(1 / costRatio).toFixed(1)}×。DeepSeek 的精确率更高，Jev 的召回率更高：两者适合不同的漏审与误杀约束。`;
  document.querySelector("#legend").innerHTML = models.map(model => `<span style="--legend:${modelColor(model.id)}">${model.name}</span>`).join("");

  const metrics = [
    { label: models[0].headlineLabel + " F1", values: models.map(model => model.headline.f1), format: value => value.toFixed(3), higher: true },
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
    const totals = payload.totals;
    const coverage = totals.pairedCompleted / totals.caseCount;
    document.querySelector("#header-status").textContent = totals.pairedCompleted === totals.caseCount ? "全部批次完整" : "全部批次已结束 · 有缺失";
    document.querySelector("#dataset-name").textContent = `${totals.datasetCount} 个数据集 · ${totals.caseCount.toLocaleString()} 条样本`;
    document.querySelector("#coverage-value").textContent = fmtPct(coverage, 2);
    document.querySelector("#coverage-bar").style.width = `${coverage * 100}%`;
    const missing = totals.caseCount - totals.pairedCompleted;
    document.querySelector("#coverage-note").textContent = `${totals.pairedCompleted.toLocaleString()} / ${totals.caseCount.toLocaleString()} 条完成双模型配对${missing ? `，${missing} 条存在结构化输出缺失` : ""}。`;
    document.querySelector("#total-tokens").textContent = fmtCompact(totals.totalTokens);
    document.querySelector("#token-breakdown").textContent = `输入 ${totals.promptTokens.toLocaleString()} + 输出 ${totals.completionTokens.toLocaleString()} token`;
    document.querySelector("#total-cost").textContent = fmtUsd(totals.costUsd, totals.costIsLowerBound);
    document.querySelector("#cost-note").textContent = totals.costIsLowerBound ? "已知费用下界；个别失败调用未返回费用字段" : "API 调用总费用，包含重试";
    document.querySelector("#model-consumption").innerHTML = totals.models.map(model => `<div class="consumption-row"><strong>${model.name}</strong><span>${fmtCompact(model.totalTokens)} token</span><b>${fmtUsd(model.costUsd, model.costIsLowerBound)}</b></div>`).join("");

    const selector = document.querySelector("#dataset-select");
    selector.innerHTML = payload.benchmarks.map((item, index) => `<option value="${index}">${item.datasetName}</option>`).join("");
    let benchmark = payload.benchmarks[0];
    const renderBenchmark = selected => {
      benchmark = selected;
      document.querySelector("#dataset-context").textContent = `${selected.caseCount.toLocaleString()} 条 · 阈值 ${selected.threshold.toFixed(2)} · ${selected.models[0].headlineLabel}`;
      document.querySelector("#run-id").textContent = selected.runId;
      document.querySelector("#taxonomy").textContent = selected.taxonomyVersion;
      document.querySelector("#updated-at").textContent = new Date(selected.updatedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
      renderModels(selected.models, selected.caseCount);
      renderTradeoffs(selected.models);
      renderCategories(selected, document.querySelector("#metric-select").value);
    };
    selector.addEventListener("change", event => renderBenchmark(payload.benchmarks[Number(event.target.value)]));
    document.querySelector("#metric-select").addEventListener("change", event => renderCategories(benchmark, event.target.value));
    renderBenchmark(benchmark);
  } catch (error) {
    document.querySelector("#model-grid").innerHTML = `<div class="error-state">数据载入失败：${error.message}</div>`;
    document.querySelector("#header-status").textContent = "数据不可用";
  }
}

init();
