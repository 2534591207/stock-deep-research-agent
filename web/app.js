const queryEl = document.querySelector("#query");
const filesEl = document.querySelector("#files");
const fileSummary = document.querySelector("#file-summary");
const runButton = document.querySelector("#run-button");
const overview = document.querySelector("#run-overview");
const stockGrid = document.querySelector("#stock-grid");
const comparisonCard = document.querySelector("#comparison-card");
const reportCard = document.querySelector("#report-card");
let latestReport = "";

filesEl.addEventListener("change", () => {
  fileSummary.textContent = filesEl.files.length ? `${filesEl.files.length} 个文件已选择` : "未选择文件";
});

runButton.addEventListener("click", async () => {
  runButton.disabled = true;
  const documents = await Promise.all([...filesEl.files].map(readFile));
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({query: queryEl.value, documents}),
  });
  const run = await response.json();
  overview.classList.remove("hidden");
  comparisonCard.classList.add("hidden");
  reportCard.classList.add("hidden");
  await poll(run.run_id);
  runButton.disabled = false;
});

document.querySelector("#download-button").addEventListener("click", () => {
  const blob = new Blob([latestReport], {type: "text/markdown;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "stock-research-report.md";
  link.click();
  URL.revokeObjectURL(url);
});

async function poll(runId) {
  while (true) {
    const response = await fetch(`/api/runs/${runId}`);
    const run = await response.json();
    render(run);
    if (["completed", "partial", "failed"].includes(run.status)) break;
    await new Promise(resolve => setTimeout(resolve, 650));
  }
}

function render(run) {
  document.querySelector("#run-status").textContent = label(run.status);
  document.querySelector("#run-message").textContent = run.message;
  const understanding = document.querySelector("#task-understanding");
  understanding.innerHTML = "";
  if (run.task) {
    const values = [
      ...run.task.companies.map(company => `${company.name} · ${company.symbol}`),
      `${run.task.time_range.label} · ${run.task.time_range.start_date} 至 ${run.task.time_range.end_date}`,
      ...run.task.defaults_applied,
    ];
    values.filter(Boolean).forEach(value => understanding.insertAdjacentHTML("beforeend", `<span class="tag">${escapeHtml(value)}</span>`));
  }

  stockGrid.innerHTML = "";
  Object.values(run.stocks || {}).forEach(stock => stockGrid.insertAdjacentHTML("beforeend", stockCard(stock)));

  if (run.comparison) {
    comparisonCard.classList.remove("hidden");
    const rankings = run.comparison.rankings || {};
    const series = Object.values(run.stocks || {}).filter(stock => stock.result?.normalized_series).map(stock => ({
      symbol: stock.company.symbol,
      values: stock.result.normalized_series,
    }));
    document.querySelector("#comparison").innerHTML = `
      ${renderChart(series)}
      <p>${escapeHtml(run.comparison.summary)}</p>
      ${rankings.return ? `<p><strong>收益：</strong>${rankings.return.join(" > ")}</p>` : ""}
      ${rankings.volatility ? `<p><strong>波动：</strong>${rankings.volatility.join(" > ")}</p>` : ""}
      ${rankings.drawdown ? `<p><strong>回撤风险：</strong>${rankings.drawdown.join(" > ")}</p>` : ""}
    `;
  }
  if (run.report_markdown) {
    latestReport = run.report_markdown;
    reportCard.classList.remove("hidden");
    document.querySelector("#report").textContent = latestReport;
  }
}

function stockCard(stock) {
  const result = stock.result;
  const metrics = result?.market_metrics;
  return `<article class="card stock-card">
    <div class="stock-head">
      <div><span class="symbol">${escapeHtml(stock.company.symbol)}</span><h2>${escapeHtml(stock.company.name)}</h2></div>
      <span class="pill">${label(stock.status)}</span>
    </div>
    <div class="steps">${stock.steps.map(step => `
      <div class="step ${step.status}">
        <span class="marker">${marker(step.status)}</span>
        <div><strong>${escapeHtml(step.label)}</strong><span>${escapeHtml(step.detail || "")}</span></div>
      </div>`).join("")}
    </div>
    ${metrics ? `<div class="metrics">
      <div class="metric"><span>区间收益</span><strong>${metrics.period_return_percent}%</strong></div>
      <div class="metric"><span>波动率</span><strong>${metrics.daily_volatility_percent}%</strong></div>
      <div class="metric"><span>最大回撤</span><strong>${metrics.max_drawdown_percent}%</strong></div>
    </div>` : ""}
    ${stock.warnings?.length ? `<p class="warning">${stock.warnings.map(escapeHtml).join("；")}</p>` : ""}
  </article>`;
}

function renderChart(series) {
  if (!series.length) return "";
  const width = 900, height = 260, pad = 28;
  const allValues = series.flatMap(item => item.values.map(point => point.value));
  const min = Math.min(...allValues), max = Math.max(...allValues);
  const span = Math.max(max - min, 1);
  const colors = ["#55d9ad", "#60a9ff", "#ffc56e"];
  const paths = series.map((item, itemIndex) => {
    const points = item.values.map((point, index) => {
      const x = pad + index / Math.max(item.values.length - 1, 1) * (width - pad * 2);
      const y = height - pad - (point.value - min) / span * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return `<polyline points="${points}" fill="none" stroke="${colors[itemIndex % colors.length]}" stroke-width="3" />`;
  }).join("");
  const legend = series.map((item, index) => `<span style="color:${colors[index % colors.length]}">● ${item.symbol}</span>`).join("");
  return `<div class="chart"><div class="chart-legend">${legend}</div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="归一化走势对比图">${paths}</svg></div>`;
}

async function readFile(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach(byte => binary += String.fromCharCode(byte));
  return {name: file.name, content_base64: btoa(binary)};
}

function marker(status) {
  return {pending: "○", running: "●", completed: "✓", partial: "!", failed: "×"}[status] || "○";
}
function label(status) {
  return {pending: "等待执行", running: "正在执行", completed: "已完成", partial: "部分完成", failed: "执行失败"}[status] || status;
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
}
