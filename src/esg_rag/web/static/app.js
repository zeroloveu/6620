const queryResults = document.getElementById("queryResults");
const analysisOutput = document.getElementById("analysisOutput");

let kbListData = [];
let selectedKbId = null;

// ── Helpers ────────────────────────────────────────────────────────

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  return Intl.NumberFormat().format(value);
}

function setButtonBusy(button, busy, label) {
  button.disabled = busy;
  if (label) {
    button.dataset.defaultLabel ??= button.textContent;
    button.textContent = busy ? label : button.dataset.defaultLabel;
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

function showConfirm(title, message) {
  return new Promise((resolve) => {
    const dialog = document.getElementById("confirmDialog");
    document.getElementById("confirmTitle").textContent = title;
    document.getElementById("confirmMessage").textContent = message;
    const ok = document.getElementById("confirmOk");
    const cancel = document.getElementById("confirmCancel");
    function cleanup(result) {
      ok.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      dialog.close();
      resolve(result);
    }
    function onOk() { cleanup(true); }
    function onCancel() { cleanup(false); }
    ok.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
    dialog.showModal();
  });
}

// ── System ─────────────────────────────────────────────────────────

function renderSystem(data) {
  document.getElementById("metricBackend").textContent = data.vector_backend || "-";
  document.getElementById("metricEmbedding").textContent = data.embedding_backend || "-";
  document.getElementById("metricModel").textContent =
    data.openai_enabled === "true" ? "OpenAI enabled" : "Fallback mode";
  document.getElementById("metricChunks").textContent = formatNumber(data.indexed_chunks);
  document.getElementById("metricSources").textContent = formatNumber(data.indexed_sources);
  document.getElementById("systemSummary").textContent =
    `Using ${data.vector_backend || "unknown"} retrieval with ${data.embedding_backend || "unknown"} embeddings.`;
}

async function loadSystem() {
  const data = await request("/system");
  renderSystem(data);
}

// ── Knowledge Base: selectors for query/analyze ────────────────────

function getCheckedKbIds(containerId) {
  return [...document.querySelectorAll(`#${containerId} input:checked`)].map(
    (cb) => cb.value,
  );
}

function renderKbSelectRow(containerId) {
  const el = document.getElementById(containerId);
  if (!kbListData.length) {
    el.innerHTML = `<span class="detail-copy">No knowledge bases yet.</span>`;
    return;
  }
  el.innerHTML = kbListData
    .map(
      (kb) => `
      <label class="kb-checkbox">
        <input type="checkbox" value="${escapeHtml(kb.id)}" />
        ${escapeHtml(kb.name)}
        <span class="badge">${kb.document_count} docs</span>
      </label>`,
    )
    .join("");
}

// ── Knowledge Base: list + CRUD ────────────────────────────────────

async function loadKbList() {
  kbListData = await request("/kb");
  renderKbList();
  renderKbSelectRow("queryKbSelect");
  renderKbSelectRow("analyzeKbSelect");
}

function renderKbList() {
  const el = document.getElementById("kbList");
  if (!kbListData.length) {
    el.innerHTML = `<div class="empty-state">No knowledge bases yet. Create one above.</div>`;
    return;
  }
  el.innerHTML = kbListData
    .map(
      (kb) => `
      <div class="kb-item ${kb.id === selectedKbId ? "active" : ""}" data-id="${escapeHtml(kb.id)}">
        <div class="kb-item-main">
          <strong>${escapeHtml(kb.name)}</strong>
          <span class="detail-copy">${escapeHtml(kb.description || "")}</span>
        </div>
        <div class="kb-item-right">
          <span class="badge">${kb.document_count} docs</span>
          <button class="danger-btn-sm kb-delete-inline" data-kb-id="${escapeHtml(kb.id)}" data-kb-name="${escapeHtml(kb.name)}" title="Delete this knowledge base">✕</button>
        </div>
      </div>`,
    )
    .join("");

  el.querySelectorAll(".kb-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      if (e.target.closest(".kb-delete-inline")) return;
      selectKb(item.dataset.id);
    });
  });

  el.querySelectorAll(".kb-delete-inline").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const kbId = btn.dataset.kbId;
      const kbName = btn.dataset.kbName;
      const confirmed = await showConfirm(
        "Delete knowledge base",
        `Are you sure you want to delete "${kbName}"? This will permanently remove all documents and indexes in this knowledge base.`,
      );
      if (!confirmed) return;
      await request(`/kb/${kbId}`, { method: "DELETE" });
      if (selectedKbId === kbId) {
        selectedKbId = null;
        document.getElementById("kbDocSection").style.display = "none";
      }
      await loadKbList();
    });
  });
}

async function selectKb(kbId) {
  selectedKbId = kbId;
  renderKbList();
  const section = document.getElementById("kbDocSection");
  section.style.display = "block";
  const kb = await request(`/kb/${kbId}`);
  document.getElementById("kbDocTitle").textContent = kb.name;
  document.getElementById("kbDocDesc").textContent = kb.description || "";
  document.getElementById("kbOutput").textContent = "";
  renderDocList(kb.documents || []);
}

// ── Documents within KB ────────────────────────────────────────────

function renderDocList(docs) {
  const el = document.getElementById("kbDocList");
  if (!docs.length) {
    el.innerHTML = `<div class="empty-state">No documents yet. Upload files above.</div>`;
    return;
  }
  el.innerHTML = docs
    .map(
      (doc) => `
      <div class="kb-doc-item">
        <div class="kb-doc-info">
          <strong>${escapeHtml(doc.original_name)}</strong>
          <span class="detail-copy">${(doc.file_size / 1024).toFixed(1)} KB · ${escapeHtml(doc.file_type)}</span>
        </div>
        <button class="danger-btn-sm" data-doc-id="${escapeHtml(doc.id)}" data-doc-name="${escapeHtml(doc.original_name)}">Delete</button>
      </div>`,
    )
    .join("");
  el.querySelectorAll(".danger-btn-sm").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const docId = btn.dataset.docId;
      const docName = btn.dataset.docName;
      const confirmed = await showConfirm(
        "Delete document",
        `Are you sure you want to delete "${docName}"?`,
      );
      if (!confirmed) return;
      await request(`/kb/${selectedKbId}/documents/${docId}`, { method: "DELETE" });
      await selectKb(selectedKbId);
      await loadKbList();
    });
  });
}

// ── KB action buttons ──────────────────────────────────────────────

document.getElementById("kbCreateBtn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const nameInput = document.getElementById("kbNameInput");
  const descInput = document.getElementById("kbDescInput");
  const name = nameInput.value.trim();
  if (!name) return;
  setButtonBusy(button, true, "Creating...");
  try {
    await request("/kb", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: descInput.value.trim() }),
    });
    nameInput.value = "";
    descInput.value = "";
    await loadKbList();
  } finally {
    setButtonBusy(button, false);
  }
});

document.getElementById("kbUploadBtn").addEventListener("click", async (event) => {
  if (!selectedKbId) return;
  const button = event.currentTarget;
  const input = document.getElementById("kbFileInput");
  if (!input.files.length) {
    document.getElementById("kbOutput").textContent = "Choose files first.";
    return;
  }
  const form = new FormData();
  [...input.files].forEach((f) => form.append("files", f));
  const output = document.getElementById("kbOutput");
  output.textContent = "Uploading and indexing...";
  setButtonBusy(button, true, "Uploading & indexing...");
  try {
    const data = await request(`/kb/${selectedKbId}/documents`, { method: "POST", body: form });
    input.value = "";
    const idx = data.index || {};
    output.textContent = `Uploaded and indexed: ${idx.files_indexed || 0} files → ${idx.chunks_indexed || 0} chunks.`;
    await selectKb(selectedKbId);
    await loadKbList();
    await loadSystem();
  } catch (error) {
    output.textContent = error.message;
  } finally {
    setButtonBusy(button, false);
  }
});

document.getElementById("kbIndexBtn").addEventListener("click", async (event) => {
  if (!selectedKbId) return;
  const button = event.currentTarget;
  const output = document.getElementById("kbOutput");
  output.textContent = "Indexing knowledge base...";
  setButtonBusy(button, true, "Indexing...");
  try {
    const data = await request(`/kb/${selectedKbId}/index`, { method: "POST" });
    output.textContent = `Indexed: ${data.files_indexed} files → ${data.chunks_indexed} chunks.`;
    await loadSystem();
  } catch (error) {
    output.textContent = error.message;
  } finally {
    setButtonBusy(button, false);
  }
});

// ── Query results rendering ────────────────────────────────────────

function renderQueryResults(results) {
  if (!results.length) {
    queryResults.innerHTML = `<div class="empty-state">No evidence matched. Try a broader ESG phrase or check your knowledge base selection.</div>`;
    return;
  }
  queryResults.innerHTML = results
    .map((item) => {
      const metadata = item.metadata || {};
      const badges = [
        `<span class="badge">score ${Number(item.score).toFixed(3)}</span>`,
        metadata.page ? `<span class="badge accent">page ${escapeHtml(metadata.page)}</span>` : "",
        metadata.source_type ? `<span class="badge">${escapeHtml(metadata.source_type)}</span>` : "",
      ]
        .filter(Boolean)
        .join("");
      return `
        <article class="result-item">
          <div class="result-head">
            <div>
              <strong>${escapeHtml(metadata.source_name || metadata.source || "Unknown source")}</strong>
              <div class="result-meta">${escapeHtml(metadata.source || "")}</div>
            </div>
            <div class="badge-row">${badges}</div>
          </div>
          <p class="result-body">${escapeHtml(item.text)}</p>
        </article>
      `;
    })
    .join("");
}

// ── Analysis rendering ─────────────────────────────────────────────

function renderAnalysisSection(title, section) {
  const findings = (section.findings || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const risks = (section.risks || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const opportunities = (section.opportunities || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const evidence = (section.evidence || [])
    .map(
      (item) => `
        <div class="subtle-panel">
          <strong>${escapeHtml(item.source)}</strong>
          <p class="detail-copy">${escapeHtml(item.excerpt)}</p>
          <div class="badge-row">
            <span class="badge">score ${Number(item.score).toFixed(3)}</span>
            ${item.page ? `<span class="badge accent">page ${escapeHtml(item.page)}</span>` : ""}
          </div>
          <p class="detail-copy">${escapeHtml(item.verification_notes || "")}</p>
        </div>
      `,
    )
    .join("");

  return `
    <section class="analysis-block">
      <div class="analysis-head">
        <div>
          <span class="eyebrow">${escapeHtml(title)}</span>
          <strong>${escapeHtml(section.title || title)}</strong>
        </div>
      </div>
      <p class="analysis-copy">${escapeHtml(section.summary || "No summary available.")}</p>
      <ul class="bullet-list">${findings || "<li>No findings extracted.</li>"}</ul>
      <div class="compliance-grid">
        <div class="compliance-item">
          <h4>Risks</h4>
          <ul class="bullet-list">${risks || "<li>No risks identified.</li>"}</ul>
        </div>
        <div class="compliance-item">
          <h4>Opportunities</h4>
          <ul class="bullet-list">${opportunities || "<li>No opportunities identified.</li>"}</ul>
        </div>
      </div>
      ${evidence}
    </section>
  `;
}

function renderCompliance(report) {
  return Object.entries(report.compliance_alignment || {})
    .map(
      ([framework, details]) => `
        <div class="compliance-item">
          <h4>${escapeHtml(framework)}</h4>
          <p>${escapeHtml(details.coverage || "unknown")} coverage</p>
          <div class="badge-row">
            <span class="badge">hits ${escapeHtml(details.matched_evidence_count ?? 0)}</span>
          </div>
          <p class="detail-copy">${escapeHtml((details.covered_topics || []).join(", ") || "No mapped topics yet.")}</p>
        </div>
      `,
    )
    .join("");
}

function renderTrace(trace = []) {
  if (!trace.length) return `<div class="empty-state">No trace data available.</div>`;
  return trace
    .map((item) => `<pre class="trace-line">${escapeHtml(JSON.stringify(item, null, 2))}</pre>`)
    .join("");
}

function renderRawContext(context = []) {
  if (!context.length) return `<div class="empty-state">No raw retrieval context attached.</div>`;
  return context
    .map((item) => {
      const metadata = item.metadata || {};
      return `
        <div class="subtle-panel">
          <strong>${escapeHtml(metadata.source_name || metadata.source || "Unknown source")}</strong>
          <div class="badge-row">
            <span class="badge">score ${Number(item.score).toFixed(3)}</span>
            ${metadata.page ? `<span class="badge accent">page ${escapeHtml(metadata.page)}</span>` : ""}
          </div>
          <p class="detail-copy">${escapeHtml(item.text)}</p>
        </div>
      `;
    })
    .join("");
}

function renderAnalysis(report) {
  const confidenceLevel = report.confidence_assessment?.level || "unknown";
  analysisOutput.innerHTML = `
    <section class="analysis-block">
      <div class="analysis-head">
        <div>
          <span class="eyebrow">Executive Summary</span>
          <strong>${escapeHtml(report.company_name || "Selected company")}</strong>
        </div>
        <div class="pill-row">
          <span class="pill ${confidenceLevel === "low" ? "low" : ""}">confidence ${escapeHtml(confidenceLevel)}</span>
          <span class="pill accent">score ${escapeHtml(report.confidence_assessment?.score ?? "-")}</span>
        </div>
      </div>
      <p class="analysis-copy">${escapeHtml(report.executive_summary || "No executive summary returned.")}</p>
      <div class="compliance-grid">${renderCompliance(report)}</div>
      <ul class="bullet-list">
        ${(report.next_steps || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
      <details>
        <summary>Agent trace</summary>
        <div class="trace-list">${renderTrace(report.agent_trace || [])}</div>
      </details>
      <details>
        <summary>Raw retrieval context</summary>
        <div class="stack">${renderRawContext(report.raw_context || [])}</div>
      </details>
    </section>
    ${renderAnalysisSection("Environment", report.environment || {})}
    ${renderAnalysisSection("Social", report.social || {})}
    ${renderAnalysisSection("Governance", report.governance || {})}
  `;
}

// ── Query + Analyze buttons ────────────────────────────────────────

const queryClearBtn = document.getElementById("queryClearBtn");
const analyzeClearBtn = document.getElementById("analyzeClearBtn");

queryClearBtn.addEventListener("click", () => {
  queryResults.innerHTML = "";
  queryClearBtn.style.display = "none";
});

analyzeClearBtn.addEventListener("click", () => {
  analysisOutput.innerHTML = "";
  analyzeClearBtn.style.display = "none";
});

document.getElementById("queryBtn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const query = document.getElementById("queryInput").value.trim();
  if (!query) return;
  queryResults.innerHTML = `<div class="empty-state">Retrieving ESG evidence...</div>`;
  queryClearBtn.style.display = "none";
  setButtonBusy(button, true, "Searching...");
  try {
    const kb_ids = getCheckedKbIds("queryKbSelect");
    const payload = { query, top_k: 6 };
    if (kb_ids.length) payload.kb_ids = kb_ids;
    const data = await request("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderQueryResults(data.results || []);
    queryClearBtn.style.display = "";
  } catch (error) {
    queryResults.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    queryClearBtn.style.display = "";
  } finally {
    setButtonBusy(button, false);
  }
});

document.getElementById("analyzeBtn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const company_name = document.getElementById("companyInput").value.trim();
  const query = document.getElementById("analysisInput").value.trim();
  const framework_focus = document
    .getElementById("frameworkInput")
    .value.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  analysisOutput.innerHTML = `<div class="empty-state">Planning sub-queries, retrieving evidence, verifying sources, and drafting the report...</div>`;
  analyzeClearBtn.style.display = "none";
  setButtonBusy(button, true, "Analyzing...");
  try {
    const kb_ids = getCheckedKbIds("analyzeKbSelect");
    const payload = { company_name, query, framework_focus, top_k: 8 };
    if (kb_ids.length) payload.kb_ids = kb_ids;
    const data = await request("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderAnalysis(data);
    analyzeClearBtn.style.display = "";
  } catch (error) {
    analysisOutput.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    analyzeClearBtn.style.display = "";
  } finally {
    setButtonBusy(button, false);
  }
});

// ── Init ───────────────────────────────────────────────────────────

loadSystem().catch(() => {});
loadKbList().catch(() => {});
