const extendedCopy = {
  navStudy: t("Study", "研究设计"),
  navScale: t("Input scale", "输入规模"),
  studyLabel: t("STUDY DESIGN", "研究设计"),
  researchContext: t("RESEARCH CONTEXT", "研究背景"),
  studyTitle: t(
    "Interpreting a request is part of service execution.",
    "意图解析是服务执行时间线的一部分。",
  ),
  studyIntro: t(
    "Natural-language requests specify a service, locality requirements, quality tier, and urgency. An interpreter converts these requirements into fields that an admission controller can validate and schedule. This interpretation step consumes part of the request deadline.",
    "自然语言请求包含服务类型、本地执行要求、质量档位和紧急程度。解析器将这些要求转换为结构化字段，供接纳控制器校验和调度。意图解析所需时间计入请求的截止时间预算。",
  ),
  studySecond: t(
    "The study changes the interpreter while retaining the contract, validator, admission limits, execution policy, and cache. It measures both the accuracy of the interpreted fields and the resulting service outcomes.",
    "本研究替换意图解析器，保持合约、校验器、接纳限制、执行策略和缓存机制一致，同时衡量字段解析的准确性及其对最终服务结果的影响。",
  ),
  layerATitle: t("Interpretation-layer evaluation", "意图解析层评估"),
  layerA: t(
    "Identical request texts are sent to each interpreter. Input length, wording, contract width, and service catalogs are varied to measure correctness and decision latency.",
    "向各解析器发送相同的请求文本，分别改变输入长度、措辞、合约宽度和服务目录，测量正确性与决策时延。",
  ),
  layerBTitle: t("Service-layer evaluation", "服务层评估"),
  layerB: t(
    "Part A combines live decision timing with modeled execution. Part B runs a real three-worker OCR service and checks the recognized text.",
    "A 部分将真实决策时间与模拟执行结合；B 部分运行包含三个工作节点的真实 OCR 服务，并检查识别文本。",
  ),
  corpusConditions: t(
    "generated + derived conditions",
    "生成条件 + 程序派生条件",
  ),
  corpusSplits: t(
    "test / development cases per generated condition",
    "每个生成条件的测试 / 开发样本",
  ),
  wording: t("request wording families", "请求措辞类型"),
  corpusMore: t(
    "Dataset construction and comparison settings",
    "数据集构建与比较设置",
  ),
  c1Title: t("Specify reference fields", "确定参考字段"),
  c1: t(
    "Label tuples are fixed before text generation, with balanced marginal distributions for each field.",
    "先确定标签元组，再生成文本；各字段的边际分布保持均衡。",
  ),
  c2Title: t("Generate and verify independently", "生成与独立会话验证"),
  c2: t(
    "A verifier labels the generated text in a separate session without seeing the reference tuple. All fields must agree for the case to be retained.",
    "验证模型在独立会话中读取文本，不接触参考标签。仅保留所有字段均与参考标签一致的案例。",
  ),
  c3Title: t("Control the comparison", "控制比较条件"),
  c3: t(
    "Hosted LLMs use strict JSON schemas and temperature zero, with no generated reasoning trace. Qwen3.5-4B-JSON is the same-weight reference for SemIf.",
    "托管 LLM 使用严格 JSON Schema、温度零且不生成推理过程。Qwen3.5-4B-JSON 作为 SemIf 的同权重生成式参考。",
  ),
  scaleLabel: t("INPUT SCALE", "输入规模"),
  scaleTitle: t(
    "Input length, decision latency, and API fees",
    "输入长度、决策时延与 API 费用",
  ),
  scaleIntro: t(
    "Requests are padded with unrelated logs, ticket threads, or configuration text. The intended service contract is unchanged.",
    "在请求中加入无关日志、工单对话或配置文本，保持目标服务合约不变。",
  ),
  lengthLabel: t("Input length", "输入长度"),
  selectedCondition: t("SELECTED CONDITION", "当前条件"),
  scaleSource: t(
    "Source: RQ1a manuscript table. Discrete conditions; lines connect observed point estimates. Confidence intervals are available in the paper. Fees cover interpretation API calls only.",
    "来源：论文 RQ1a 表格。横轴为离散条件，连线连接观测点；置信区间见论文。费用仅包含意图解析 API 调用。",
  ),
  catalogLabel: t("SERVICE CATALOG", "服务目录"),
  catalogTitle: t(
    "Service selection with request-time catalogs",
    "请求时提供目录的服务选择",
  ),
  catalogIntro: t(
    "Catalogs contain 4–254 services. Service identification, unsupported-request detection, and interface validity are evaluated separately.",
    "目录包含 4–254 个服务。分别评估服务识别、不支持请求检测及接口输出有效性。",
  ),
  catalogSize: t("Services in catalog", "目录中的服务数"),
  interpreter: t("Interpreter", "解析器"),
  seen: t("Seen top-1", "已见服务 top-1"),
  unseen: t("Unseen top-1", "未见服务 top-1"),
  unsupported: t("Unsupported F1", "不支持请求 F1"),
  valid: t("Valid output", "有效输出率"),
  decisionTime: t("Decision p50", "决策 p50"),
  catalogNote1: t(
    "Jev and the hosted LLMs receive the catalog with each request. At 254 services, their unseen-service top-1 accuracy is 99.5–100%. Identifying a service and rejecting unsupported requests remain separate tasks.",
    "Jev 与托管 LLM 随每次请求接收服务目录。目录包含 254 个服务时，它们对未见服务的 top-1 准确率为 99.5–100%。识别服务与拒绝不支持的请求是不同任务。",
  ),
  catalogNote2: t(
    "Interface limits affect the self-hosted models: SemIf returns no valid output from 64 services onward, and Laya returns no valid output at 254. Low latency in these cells represents failed calls.",
    "自托管模型受到接口限制：SemIf 在目录达到 64 个服务起无有效输出，Laya 在 254 个服务时无有效输出。这些条件下的低时延对应失败调用。",
  ),
  catalogSource: t(
    "Source: RQ4a manuscript table · “—” indicates that unseen services were not evaluated in that cell. Red cells indicate no valid output; all rows are retained.",
    "来源：论文 RQ4a 表格 · “—” 表示该条件未评估未见服务。红色单元格表示无有效输出，保留全部模型行。",
  ),
};
document
  .querySelectorAll("[data-x]")
  .forEach((n) => (n.textContent = extendedCopy[n.dataset.x] || ""));
let extendedData,
  scaleMetric = "latency",
  scaleIndex = 0,
  catalogSize = "64";
const inputKeys = ["base", "512", "2048", "8192", "16384"],
  hosted = [0, 3, 4, 5],
  colors = ["#255bf2", "#d18143", "#277d7b", "#986aab"];
const names = [
  "Jev-1.13.0",
  "DeepSeek-V4.1-Flash",
  "GLM-5.3-Flash",
  "Qwen3.8-Flash",
];
const inputName = (i) =>
  i === 0
    ? t("Base length", "原始长度")
    : Number(inputKeys[i]).toLocaleString() + t(" tokens", " tokens");
const labels = {
  latency: t("Decision latency", "决策时延"),
  accuracy: t("Exact match", "严格匹配率"),
  fee: t("API fees", "API 费用"),
};
function renderScale() {
  const values = hosted.flatMap((i) =>
    inputKeys.map((k) => extendedData.input[k][i][scaleMetric]),
  );
  const max = scaleMetric === "accuracy" ? 1 : Math.max(...values) * 1.15;
  const X = (i) => 65 + i * 126,
    Y = (v) => 252 - (v / max) * 212;
  let svg = `<svg viewBox="0 0 630 300" role="img" aria-label="${labels[scaleMetric]}"><title>${labels[scaleMetric]}</title>`;
  for (let j = 0; j <= 4; j++) {
    let v = (max * j) / 4,
      y = Y(v);
    svg += `<line x1="65" x2="580" y1="${y}" y2="${y}" class="grid-line"/><text x="50" y="${y + 4}" text-anchor="end" class="tick">${scaleMetric === "accuracy" ? (v * 100).toFixed(0) + "%" : v.toFixed(max < 1 ? 2 : 1)}</text>`;
  }
  svg += `<line x1="${X(scaleIndex)}" x2="${X(scaleIndex)}" y1="25" y2="255" class="selected-line"/>`;
  hosted.forEach((model, n) => {
    const pts = inputKeys.map(
      (k, i) => `${X(i)},${Y(extendedData.input[k][model][scaleMetric])}`,
    );
    svg += `<polyline points="${pts.join(" ")}" fill="none" stroke="${colors[n]}" stroke-width="${n === 0 ? 3.5 : 2}"/>`;
    inputKeys.forEach((k, i) => {
      let value = extendedData.input[k][model][scaleMetric];
      svg += `<circle cx="${X(i)}" cy="${Y(value)}" r="${i === scaleIndex ? 6 : 3.5}" fill="${colors[n]}" stroke="white" stroke-width="2"><title>${names[n]} · ${inputName(i)}: ${value}</title></circle>`;
    });
  });
  inputKeys.forEach((k, i) => {
    svg += `<text x="${X(i)}" y="280" text-anchor="middle" class="tick">${i === 0 ? t("Base", "原始") : Number(k).toLocaleString()}</text>`;
  });
  svg += "</svg>";
  $("trend-plot").innerHTML = svg;
  $("scale-unit").textContent =
    scaleMetric === "latency"
      ? t("Median · seconds", "中位数 · 秒")
      : scaleMetric === "accuracy"
        ? t("All fields correct", "全部字段正确")
        : t("USD / 1,000 correct decisions", "美元 / 1,000 次正确决策");
  $("scale-metrics").innerHTML = "";
  Object.entries(labels).forEach(([k, v]) => {
    const b = document.createElement("button");
    b.textContent = v;
    b.setAttribute("aria-pressed", k === scaleMetric);
    b.onclick = () => {
      scaleMetric = k;
      renderScale();
    };
    $("scale-metrics").append(b);
  });
  $("input-length-value").textContent = inputName(scaleIndex);
  $("scale-selection").textContent = inputName(scaleIndex);
  $("scale-readout").innerHTML = hosted
    .map((i, n) => {
      const v = extendedData.input[inputKeys[scaleIndex]][i][scaleMetric];
      const text =
        scaleMetric === "accuracy"
          ? (v * 100).toFixed(1) + "%"
          : scaleMetric === "fee"
            ? "$" + v.toFixed(4)
            : v.toFixed(3) + " s";
      return `<div class="readout-row"><span><i style="background:${colors[n]}"></i>${names[n]}</span><strong>${text}</strong></div>`;
    })
    .join("");
  $("plot-legend").innerHTML = names
    .map((n, i) => `<span><i style="background:${colors[i]}"></i>${n}</span>`)
    .join("");
  $("scale-note").textContent =
    scaleMetric === "fee"
      ? t(
          "At 16,384 tokens, Jev’s API fee is $1.044 per 1,000 correct decisions, compared with $5.455 for DeepSeek. These are recorded experiment fees, not current provider prices.",
          "16,384 tokens 时，Jev 与 DeepSeek 每 1,000 次正确决策的 API 费用分别为 1.044 和 5.455 美元。此处为实验记录的费用，不代表供应商当前价格。",
        )
      : scaleMetric === "accuracy"
        ? t(
            "Jev’s exact-match rate is 91.0–94.0% across these lengths, compared with 97.3–99.0% for DeepSeek. Latency and accuracy should be considered together.",
            "这些输入长度下，Jev 的严格匹配率为 91.0–94.0%，DeepSeek 为 97.3–99.0%。时延与准确率需要共同考虑。",
          )
        : t(
            "From base length to 16,384 tokens, median decision latency changes from 0.274 to 0.418 s for Jev and from 0.378 to 0.638 s for DeepSeek.",
            "从原始长度增加至 16,384 tokens，Jev 的决策时延中位数由 0.274 增至 0.418 秒，DeepSeek 由 0.378 增至 0.638 秒。",
          );
}
function renderCatalog() {
  $("catalog-sizes").innerHTML = "";
  ["4", "15", "64", "128", "254"].forEach((k) => {
    const b = document.createElement("button");
    b.textContent = k;
    b.setAttribute("aria-pressed", k === catalogSize);
    b.onclick = () => {
      catalogSize = k;
      renderCatalog();
    };
    $("catalog-sizes").append(b);
  });
  $("catalog-body").innerHTML = extendedData.catalog[catalogSize]
    .map(
      (r, i) =>
        `<tr class="${i === 0 ? "focus-row" : ""}"><th>${r.model}</th>${["seen", "unseen", "unsupported", "valid"].map((k) => `<td class="${r.valid === 0 ? "failed" : ""}">${r[k] === null ? '<span class="missing">—</span>' : `<span class="matrix-value">${k === "unsupported" ? r[k].toFixed(3) : (r[k] * 100).toFixed(1) + "%"}</span><span class="cell-track"><i style="width:${r[k] * 100}%"></i></span>`}</td>`).join("")}<td class="${r.valid === 0 ? "failed" : ""}">${r.latency.toFixed(3)} s${r.valid === 0 ? "<small>" + t("failed call", "失败调用") + "</small>" : ""}</td></tr>`,
    )
    .join("");
}
$("input-length").addEventListener("input", (e) => {
  scaleIndex = Number(e.target.value);
  renderScale();
});
fetch(base + "assets/extended-data.json")
  .then((r) => {
    if (!r.ok) throw Error();
    return r.json();
  })
  .then((d) => {
    extendedData = d;
    renderScale();
    renderCatalog();
  })
  .catch(() => {
    $("trend-plot").textContent = t(
      "Unable to load table data.",
      "表格数据未能加载。",
    );
  });
function progress() {
  let available = document.documentElement.scrollHeight - innerHeight;
  document.querySelector(".reading-progress span").style.width =
    (available > 0 ? (scrollY / available) * 100 : 0) + "%";
}
addEventListener("scroll", progress, { passive: true });
progress();
