const state = {
  documents: [],
  summary: null,
  selectedId: null,
  loading: false,
};

const elements = {
  totalDocuments: document.querySelector("#totalDocuments"),
  processedDocuments: document.querySelector("#processedDocuments"),
  failedDocuments: document.querySelector("#failedDocuments"),
  storageBytes: document.querySelector("#storageBytes"),
  tableState: document.querySelector("#tableState"),
  documentsBody: document.querySelector("#documentsBody"),
  searchInput: document.querySelector("#searchInput"),
  statusFilter: document.querySelector("#statusFilter"),
  analysisPreview: document.querySelector("#analysisPreview"),
  previewState: document.querySelector("#previewState"),
  summaryPreview: document.querySelector("#summaryPreview"),
  summaryState: document.querySelector("#summaryState"),
  uploadForm: document.querySelector("#uploadForm"),
  fileInput: document.querySelector("#fileInput"),
  dropZone: document.querySelector("#dropZone"),
  uploadButton: document.querySelector("#uploadButton"),
  refreshButton: document.querySelector("#refreshButton"),
  themeToggle: document.querySelector("#themeToggle"),
  themeIcon: document.querySelector("#themeIcon"),
  detailsPanel: document.querySelector("#detailsPanel"),
  selectedState: document.querySelector("#selectedState"),
  languageList: document.querySelector("#languageList"),
  toastStack: document.querySelector("#toastStack"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatBytes(bytes) {
  if (!bytes) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("document-console-theme", theme);
  elements.themeIcon.textContent = theme === "dark" ? "Sun" : "Moon";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === "string" ? payload : payload.detail || "Request failed";
    throw new Error(message);
  }
  return payload;
}

function showToast(message, type = "info", timeout = 3200) {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  elements.toastStack.appendChild(toast);
  setTimeout(() => toast.remove(), timeout);
}

function selectedDocument() {
  return state.documents.find((item) => item.id === state.selectedId) || null;
}

function aiBadge(documentItem) {
  if (documentItem.ai_error) {
    return '<span class="badge failed">error</span>';
  }
  if (documentItem.ai_summary) {
    return '<span class="badge processed">ready</span>';
  }
  return '<span class="badge uploaded">none</span>';
}

function renderMetrics() {
  const summary = state.summary || {};
  elements.totalDocuments.textContent = summary.total_documents ?? state.documents.length;
  elements.processedDocuments.textContent =
    summary.processed_documents ?? state.documents.filter((item) => item.status === "processed").length;
  elements.failedDocuments.textContent =
    summary.failed_documents ?? state.documents.filter((item) => item.status === "failed").length;
  elements.storageBytes.textContent = formatBytes(summary.storage_bytes ?? 0);

  const languages = summary.detected_languages || {};
  const entries = Object.entries(languages);
  if (!entries.length) {
    elements.languageList.innerHTML = '<span class="muted">No language data yet.</span>';
    return;
  }
  elements.languageList.innerHTML = entries
    .sort((a, b) => b[1] - a[1])
    .map(([language, count]) => `<span class="badge processed">${escapeHtml(language)} ${count}</span>`)
    .join("");
}

function renderTable() {
  const query = elements.searchInput.value.toLowerCase().trim();
  const status = elements.statusFilter.value;
  let documents = state.documents;

  if (status !== "all") {
    documents = documents.filter((item) => item.status === status);
  }
  if (query) {
    documents = documents.filter((item) =>
      [item.filename, item.content_type, item.detected_language, item.status]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)) ||
      String(item.ai_summary || "").toLowerCase().includes(query),
    );
  }

  elements.tableState.textContent = `${documents.length} shown`;

  if (!documents.length) {
    elements.documentsBody.innerHTML = '<tr><td colspan="8" class="muted">No documents for this filter.</td></tr>';
    return;
  }

  elements.documentsBody.innerHTML = documents
    .map(
      (item) => `
        <tr data-document-id="${item.id}" data-selected="${item.id === state.selectedId}">
          <td>
            <p class="file-name">${escapeHtml(item.filename)}</p>
            <span class="file-meta">#${item.id} created ${escapeHtml(new Date(item.created_at).toLocaleString())}</span>
          </td>
          <td>${escapeHtml(item.content_type)}</td>
          <td><span class="badge ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td>
          <td>${formatBytes(item.size_bytes)}</td>
          <td>${escapeHtml(item.detected_language || "-")}</td>
          <td>${item.word_count || 0}</td>
          <td>${aiBadge(item)}</td>
          <td>
            <div class="row-actions">
              <button class="button small" type="button" data-action="select" data-document-id="${item.id}">Open</button>
              <button class="button small" type="button" data-action="analyze" data-document-id="${item.id}">Analyze</button>
              <button class="button small" type="button" data-action="summarize" data-document-id="${item.id}" ${item.status === "processed" ? "" : "disabled"}>Summarize</button>
              <button class="button small" type="button" data-action="download" data-document-id="${item.id}">Download</button>
              <button class="button danger small" type="button" data-action="delete" data-document-id="${item.id}">Delete</button>
            </div>
          </td>
        </tr>
      `,
    )
    .join("");
}

function renderDetails() {
  const documentItem = selectedDocument();
  if (!documentItem) {
    elements.selectedState.textContent = "None";
    elements.detailsPanel.innerHTML = '<div class="empty">Select a document from the table.</div>';
    elements.previewState.textContent = "No document selected";
    elements.analysisPreview.textContent = "Select a processed document to inspect extracted text.";
    elements.summaryState.textContent = "No document selected";
    elements.summaryPreview.textContent = "Analyze a document before generating an AI summary.";
    return;
  }

  elements.selectedState.textContent = `#${documentItem.id}`;
  elements.detailsPanel.innerHTML = `
    <div class="detail-grid">
      <div class="detail-row"><span class="detail-label">Filename</span><span>${escapeHtml(documentItem.filename)}</span></div>
      <div class="detail-row"><span class="detail-label">Status</span><span><span class="badge ${escapeHtml(documentItem.status)}">${escapeHtml(documentItem.status)}</span></span></div>
      <div class="detail-row"><span class="detail-label">Type</span><span>${escapeHtml(documentItem.content_type)}</span></div>
      <div class="detail-row"><span class="detail-label">Size</span><span>${formatBytes(documentItem.size_bytes)}</span></div>
      <div class="detail-row"><span class="detail-label">Language</span><span>${escapeHtml(documentItem.detected_language || "-")}</span></div>
      <div class="detail-row"><span class="detail-label">Words</span><span>${documentItem.word_count || 0}</span></div>
      <div class="detail-row"><span class="detail-label">Characters</span><span>${documentItem.char_count || 0}</span></div>
      <div class="detail-row"><span class="detail-label">AI</span><span>${aiBadge(documentItem)}</span></div>
      ${
        documentItem.ai_model
          ? `<div class="detail-row"><span class="detail-label">AI model</span><span>${escapeHtml(documentItem.ai_model)}</span></div>`
          : ""
      }
      <div class="detail-row"><span class="detail-label">Updated</span><span>${escapeHtml(new Date(documentItem.updated_at).toLocaleString())}</span></div>
      ${
        documentItem.error_message
          ? `<div class="detail-row"><span class="detail-label">Error</span><span>${escapeHtml(documentItem.error_message)}</span></div>`
          : ""
      }
      ${
        documentItem.ai_error
          ? `<div class="detail-row"><span class="detail-label">AI error</span><span>${escapeHtml(documentItem.ai_error)}</span></div>`
          : ""
      }
    </div>
  `;

  elements.previewState.textContent = documentItem.status === "processed" ? "Extracted text" : documentItem.status;
  elements.analysisPreview.textContent =
    documentItem.extracted_text || "Run analysis to extract text and compute document metrics.";
  elements.summaryState.textContent = documentItem.ai_error
    ? "Error"
    : documentItem.ai_summary
      ? documentItem.ai_model || "Generated"
      : documentItem.status === "processed"
        ? "Ready"
        : "Analyze first";
  elements.summaryPreview.textContent =
    documentItem.ai_summary ||
    documentItem.ai_error ||
    (documentItem.status === "processed"
      ? "AI summary has not been generated for this document."
      : "Document must be analyzed first.");
}

function render() {
  renderMetrics();
  renderTable();
  renderDetails();
}

function setLoading(isLoading) {
  state.loading = isLoading;
  elements.refreshButton.disabled = isLoading;
  elements.uploadButton.disabled = isLoading;
  elements.tableState.textContent = isLoading ? "Loading" : elements.tableState.textContent;
}

function renderSkeleton() {
  elements.documentsBody.innerHTML = Array.from(
    { length: 4 },
    () => '<tr><td colspan="8"><div class="skeleton" style="height:28px;border-radius:6px;"></div></td></tr>',
  ).join("");
}

async function loadData() {
  setLoading(true);
  renderSkeleton();
  try {
    const [summary, documents] = await Promise.all([
      fetchJson("/api/dashboard/summary"),
      fetchJson("/api/documents"),
    ]);
    state.summary = summary;
    state.documents = documents;
    if (state.selectedId && !state.documents.some((item) => item.id === state.selectedId)) {
      state.selectedId = null;
    }
    render();
  } catch (error) {
    showToast(error.message, "error");
    elements.documentsBody.innerHTML = `<tr><td colspan="8" class="muted">Could not load data: ${escapeHtml(error.message)}</td></tr>`;
  } finally {
    setLoading(false);
  }
}

async function uploadSelectedFile(file) {
  if (!file) {
    showToast("Choose a PDF or TXT file first.", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  setLoading(true);
  try {
    const created = await fetchJson("/api/documents/upload", {
      method: "POST",
      body: formData,
    });
    state.selectedId = created.id;
    elements.fileInput.value = "";
    showToast("Document uploaded.", "success");
    await loadData();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function analyzeDocument(documentId) {
  setLoading(true);
  try {
    const updated = await fetchJson(`/api/documents/${documentId}/analyze`, { method: "POST" });
    state.selectedId = updated.id;
    showToast(updated.status === "failed" ? "Analysis failed." : "Analysis completed.", updated.status === "failed" ? "error" : "success");
    await loadData();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function summarizeDocument(documentId) {
  setLoading(true);
  try {
    const updated = await fetchJson(`/api/documents/${documentId}/summarize`, { method: "POST" });
    state.selectedId = updated.id;
    showToast("AI summary generated.", "success");
    await loadData();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function deleteDocument(documentId) {
  if (!confirm("Delete this document and its stored file?")) {
    return;
  }
  setLoading(true);
  try {
    await fetchJson(`/api/documents/${documentId}`, { method: "DELETE" });
    if (state.selectedId === documentId) {
      state.selectedId = null;
    }
    showToast("Document deleted.", "success");
    await loadData();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

elements.themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  setTheme(current === "dark" ? "light" : "dark");
});

elements.refreshButton.addEventListener("click", loadData);
elements.searchInput.addEventListener("input", renderTable);
elements.statusFilter.addEventListener("change", renderTable);

elements.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await uploadSelectedFile(elements.fileInput.files[0]);
});

elements.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  elements.dropZone.classList.add("dragover");
});

elements.dropZone.addEventListener("dragleave", () => {
  elements.dropZone.classList.remove("dragover");
});

elements.dropZone.addEventListener("drop", async (event) => {
  event.preventDefault();
  elements.dropZone.classList.remove("dragover");
  await uploadSelectedFile(event.dataTransfer.files[0]);
});

elements.documentsBody.addEventListener("click", async (event) => {
  const target = event.target.closest("button[data-action]");
  if (!target) {
    const row = event.target.closest("tr[data-document-id]");
    if (row) {
      state.selectedId = Number(row.dataset.documentId);
      render();
    }
    return;
  }

  const documentId = Number(target.dataset.documentId);
  if (target.dataset.action === "select") {
    state.selectedId = documentId;
    render();
  }
  if (target.dataset.action === "analyze") {
    await analyzeDocument(documentId);
  }
  if (target.dataset.action === "summarize") {
    await summarizeDocument(documentId);
  }
  if (target.dataset.action === "download") {
    window.location.href = `/api/documents/${documentId}/download`;
  }
  if (target.dataset.action === "delete") {
    await deleteDocument(documentId);
  }
});

setTheme(localStorage.getItem("document-console-theme") || "dark");
loadData();
