const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);

const configuredApiBaseUrl = document.body.dataset.apiBaseUrl || "";
const apiBaseUrl = configuredApiBaseUrl.startsWith("{{")
  ? ""
  : configuredApiBaseUrl.replace(/\/+$/, "");

function apiUrl(path) {
  return `${apiBaseUrl}${path}`;
}

const progressPercent = (earned, required) => required > 0
  ? Math.min(100, Math.round(earned / required * 100))
  : 100;

function installOptions() {
  const template = document.querySelector("#optionsTemplate");
  document.querySelectorAll(".options").forEach(target => {
    target.append(template.content.cloneNode(true));
  });
}

function setLoginMode() {
  const enabled = document.body.dataset.remoteLoginEnabled === "true";
  document.querySelector(enabled ? "#loginEnabled" : "#loginDisabled").classList.remove("hidden");
}

async function setDeploymentContext() {
  const location = document.querySelector("#processingLocation");
  const status = document.querySelector("#backendStatus");
  if (apiBaseUrl) {
    location.textContent = "此頁面由 GitHub Pages 提供；你選擇的檔案會加密傳送至 Hugging Face 後端，並只在單次請求的暫存目錄解析。";
  } else {
    location.textContent = "此頁面與解析服務位於同一個部署環境；檔案只在單次請求的暫存目錄解析。";
  }
  try {
    const response = await fetch(apiUrl("/health"), { cache: "no-store" });
    if (!response.ok) throw new Error("health check failed");
    status.textContent = "後端可用";
    status.className = "status-chip good";
  } catch {
    status.textContent = "後端啟動中／暫時無法連線";
    status.className = "status-chip caution";
  }
}

function setStatus(message, isError = false) {
  const panel = document.querySelector("#statusPanel");
  const box = document.querySelector("#statusMessage");
  panel.classList.remove("hidden");
  box.className = `notice${isError ? " error" : ""}`;
  box.textContent = message;
}

function courseRows(courses) {
  if (!courses.length) return '<p class="muted">沒有課程紀錄。</p>';
  const rows = courses.map(course => `<tr>
    <td>${escapeHtml(course.name)}</td><td>${escapeHtml(course.credits)}</td>
    <td>${escapeHtml(course.semester || "—")}</td><td>${escapeHtml(course.grade || course.status)}</td>
  </tr>`).join("");
  return `<table><thead><tr><th>課程</th><th>學分</th><th>學期</th><th>成績／狀態</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function requirementCard(requirement) {
  const status = requirement.complete ? "完成" : (requirement.verification_required ? "待確認" : "未完成");
  const chipClass = requirement.complete ? "good" : "caution";
  const missing = requirement.missing_courses.length
    ? `<p><strong>缺少：</strong>${escapeHtml(requirement.missing_courses.join("、"))}</p>` : "";
  const warnings = requirement.warnings.length
    ? `<ul class="warning-list">${requirement.warnings.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "";
  return `<section class="requirement">
    <div class="section-heading"><strong>${escapeHtml(requirement.title)}</strong><span class="status-chip ${chipClass}">${status}</span></div>
    <div class="progress"><span style="width:${progressPercent(requirement.earned_credits, requirement.required_credits)}%"></span></div>
    <div>${escapeHtml(requirement.earned_credits)} / ${escapeHtml(requirement.required_credits)} 學分</div>
    ${missing}${warnings}
    <details><summary>查看已歸類課程（${requirement.matched_courses.length}）</summary>${courseRows(requirement.matched_courses)}</details>
  </section>`;
}

function programResult(result) {
  const remaining = Math.max(0, result.total_required_credits - result.total_earned_credits);
  const warnings = [...(result.warnings || [])];
  if (result.provisional) warnings.unshift("這是預估結果，兼充與替代課程仍需系所核准。");
  const warningList = warnings.length
    ? `<ul class="warning-list">${warnings.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "";
  return `<article class="program">
    <div class="section-heading">
      <div><h3>${escapeHtml(result.profile)}</h3><p class="muted">規則 ${escapeHtml(result.rule_version)} · 檢核日期 ${escapeHtml(result.reviewed_at || "—")}</p></div>
      <span class="status-chip ${result.complete ? "good" : "caution"}">${result.complete ? "條件已達成" : "尚有缺項／待確認"}</span>
    </div>
    <div class="summary-grid">
      <div class="metric"><span>已採計</span><strong>${escapeHtml(result.total_earned_credits)}</strong><small>學分</small></div>
      <div class="metric"><span>最低要求</span><strong>${escapeHtml(result.total_required_credits)}</strong><small>學分</small></div>
      <div class="metric"><span>仍差</span><strong>${escapeHtml(remaining)}</strong><small>學分</small></div>
      <div class="metric"><span>待確認</span><strong>${escapeHtml(result.needs_review.length)}</strong><small>門課</small></div>
    </div>
    ${warningList}
    <div class="requirement-grid">${result.requirements.map(requirementCard).join("")}</div>
    <details><summary>修習中課程（${result.in_progress.length}）</summary>${courseRows(result.in_progress)}</details>
    <details><summary>待人工確認（${result.needs_review.length}）</summary>${courseRows(result.needs_review)}</details>
    <details><summary>未採計／未通過（${result.excluded.length}）</summary>${courseRows(result.excluded)}</details>
  </article>`;
}

function render(payload) {
  const labels = { complete: "解析完整", partial: "部分解析", failed: "解析失敗" };
  const chip = document.querySelector("#qualityChip");
  chip.textContent = labels[payload.data_quality] || payload.data_quality;
  chip.className = `status-chip ${payload.data_quality === "complete" ? "good" : "caution"}`;
  document.querySelector("#diagnostics").innerHTML = payload.diagnostics.map(item =>
    `<div class="notice ${item.quality === "failed" ? "error" : ""}"><strong>${escapeHtml(item.source)}</strong>：${escapeHtml(labels[item.quality] || item.quality)}，解析 ${escapeHtml(item.parsed_count)}/${escapeHtml(item.total_candidates)} 筆。 ${escapeHtml((item.messages || []).join(" "))}</div>`
  ).join("");
  document.querySelector("#results").innerHTML = payload.results.map(programResult).join("");
  document.querySelector("#disclaimer").textContent = payload.disclaimer;
  document.querySelector("#resultsPanel").classList.remove("hidden");
}

async function submitForm(form, url) {
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  document.querySelector("#resultsPanel").classList.add("hidden");
  setStatus("處理中，正在驗證檔案與解析課程…");
  const data = new FormData(form);
  ["include_chem_double_major", "include_cs_double_major", "include_cs_minor"].forEach(name => {
    if (!data.has(name)) data.set(name, "false");
  });
  try {
    const response = await fetch(apiUrl(url), { method: "POST", body: data, cache: "no-store" });
    let payload;
    try { payload = await response.json(); } catch { throw new Error("伺服器回傳非 JSON 回應。"); }
    if (!response.ok) throw new Error(payload.detail || "處理失敗");
    render(payload);
    setStatus("審核完成。請先查看解析品質與待確認項目。");
  } catch (error) {
    setStatus(error.message || String(error), true);
  } finally {
    button.disabled = false;
  }
}

installOptions();
setLoginMode();
setDeploymentContext();
document.querySelector("#uploadForm").addEventListener("submit", event => {
  event.preventDefault();
  submitForm(event.currentTarget, "/audit/upload");
});
const loginForm = document.querySelector("#loginForm");
if (loginForm) loginForm.addEventListener("submit", event => {
  event.preventDefault();
  submitForm(event.currentTarget, "/audit/login");
});
