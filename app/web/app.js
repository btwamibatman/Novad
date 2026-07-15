const state = {
  documents: [],
  summary: null,
  session: null,
  selectedId: null,
  chatDocumentId: null,
  chatOpen: false,
  chatAbortController: null,
  pendingAction: null,
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
  analysisQualityNotice: document.querySelector("#analysisQualityNotice"),
  previewState: document.querySelector("#previewState"),
  summaryPreview: document.querySelector("#summaryPreview"),
  summaryState: document.querySelector("#summaryState"),
  contentReviewPreview: document.querySelector("#contentReviewPreview"),
  contentReviewState: document.querySelector("#contentReviewState"),
  contentReviewMode: document.querySelector("#contentReviewMode"),
  contentReviewButton: document.querySelector("#contentReviewButton"),
  layoutReviewPreview: document.querySelector("#layoutReviewPreview"),
  layoutReviewState: document.querySelector("#layoutReviewState"),
  layoutReviewButton: document.querySelector("#layoutReviewButton"),
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
  aiChatToggle: document.querySelector("#aiChatToggle"),
  aiChatPopup: document.querySelector("#aiChatPopup"),
  aiChatClose: document.querySelector("#aiChatClose"),
  aiChatState: document.querySelector("#aiChatState"),
  aiChatDocumentSelect: document.querySelector("#aiChatDocumentSelect"),
  aiChatMessages: document.querySelector("#aiChatMessages"),
  aiChatForm: document.querySelector("#aiChatForm"),
  aiChatInput: document.querySelector("#aiChatInput"),
  aiChatSend: document.querySelector("#aiChatSend"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(element, markdown) {
  const unsafeHtml = marked.parse(markdown || "");
  element.innerHTML = DOMPurify.sanitize(unsafeHtml);
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

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value);
  }
  return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/\.?0+$/, "");
}

function extractionQualityWarning(documentItem) {
  const meta = documentItem?.extraction_quality_meta || {};
  if (!meta.requires_manual_review) {
    return "";
  }
  const pages = (meta.manual_review_pages || []).filter((page) => page != null);
  const pageLabel = pages.length ? ` Pages to verify: ${pages.join(", ")}.` : "";
  return `OCR quality: ${documentItem.extraction_quality || "unknown"}. Extracted text is advisory; verify names, dates and identifiers against the PDF image.${pageLabel}`;
}

function formatLanguageDistribution(distribution) {
  const entries = Object.entries(distribution || {}).filter(([, share]) => Number(share) > 0);
  if (!entries.length) {
    return "";
  }
  return entries
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([language, share]) => `${language} ${Math.round(Number(share) * 100)}%`)
    .join(", ");
}

function documentLanguageLabel(documentItem) {
  return formatLanguageDistribution(documentItem.language_distribution) || documentItem.detected_language || "-";
}

function isPendingAction(action, documentId = null) {
  return (
    state.pendingAction?.action === action &&
    (documentId === null || state.pendingAction.documentId === documentId)
  );
}

function actionButton(item, action, label, pendingLabel, extraClass = "", disabled = false) {
  const pending = isPendingAction(action, item.id);
  const className = ["button", "small", extraClass, pending ? "loading" : ""].filter(Boolean).join(" ");
  return `
    <button
      class="${className}"
      type="button"
      data-action="${action}"
      data-document-id="${item.id}"
      ${pending ? 'aria-busy="true"' : ""}
      ${disabled || state.loading ? "disabled" : ""}
    >${pending ? pendingLabel : label}</button>
  `;
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("document-console-theme", theme);
  elements.themeIcon.textContent = theme === "dark" ? "Sun" : "Moon";
}

class ApiError extends Error {
  constructor(message, status, payload, retryAfter) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    this.retryAfter = retryAfter;
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : payload.detail || "Request failed";
    const message = typeof detail === "string" ? detail : detail.message || "Request failed";
    throw new ApiError(message, response.status, payload, response.headers.get("Retry-After"));
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

function processedDocuments() {
  return state.documents.filter((item) => item.status === "processed");
}

function selectedChatDocument() {
  return state.documents.find((item) => item.id === state.chatDocumentId && item.status === "processed") || null;
}

function sessionExpired() {
  return state.session?.expires_at && new Date(state.session.expires_at).getTime() <= Date.now();
}

async function loadSession() {
  state.session = await fetchJson("/api/session");
  return state.session;
}

function chatStorageKey(documentId) {
  return `document-console-chat:${state.session?.session_id || "anonymous"}:${documentId}`;
}

function readChatMessages(documentId) {
  if (!documentId || !state.session || sessionExpired()) {
    return [];
  }
  try {
    const saved = JSON.parse(sessionStorage.getItem(chatStorageKey(documentId)) || "null");
    if (!saved || saved.expires_at !== state.session.expires_at) {
      return [];
    }
    return Array.isArray(saved.messages) ? saved.messages : [];
  } catch {
    return [];
  }
}

function writeChatMessages(documentId, messages) {
  if (!documentId || !state.session) {
    return;
  }
  sessionStorage.setItem(
    chatStorageKey(documentId),
    JSON.stringify({
      expires_at: state.session.expires_at,
      messages: messages.slice(-40),
    }),
  );
}

function clearSessionState(message = "Session expired, upload files again.") {
  if (state.chatAbortController) {
    state.chatAbortController.abort();
    state.chatAbortController = null;
  }
  if (state.session?.session_id) {
    const prefix = `document-console-chat:${state.session.session_id}:`;
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith(prefix))
      .forEach((key) => sessionStorage.removeItem(key));
  }
  state.documents = [];
  state.summary = null;
  state.session = null;
  state.selectedId = null;
  state.chatDocumentId = null;
  render();
  showToast(message, "error");
}

function handleApiError(error) {
  if (error.status === 401 || error.status === 419) {
    clearSessionState("Session expired, upload files again.");
    return true;
  }
  if (error.status === 429) {
    showToast(`Rate limit exceeded. Try again in ${error.retryAfter || "a few"} seconds.`, "error");
    return true;
  }
  return false;
}

function errorMessage(error) {
  const detail = error.payload?.detail;
  if (detail && typeof detail === "object" && detail.used_bytes !== undefined) {
    return `${detail.message || error.message}. Used ${formatBytes(detail.used_bytes)} of ${formatBytes(detail.quota_bytes)}.`;
  }
  return error.message;
}

function aiBadge(documentItem) {
  if (documentItem.ai_error || documentItem.content_review_error || documentItem.layout_review_error) {
    return '<span class="badge failed">error</span>';
  }
  if (documentItem.ai_summary || documentItem.content_review || documentItem.layout_review) {
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
    .map(([language, count]) => `<span class="badge processed">${escapeHtml(language)} ${formatNumber(count)}</span>`)
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
      [item.ai_summary, item.content_review, item.layout_review]
        .some((value) => String(value || "").toLowerCase().includes(query)),
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
          <td>${escapeHtml(documentLanguageLabel(item))}</td>
          <td>${item.word_count || 0}</td>
          <td>${aiBadge(item)}</td>
          <td>
            <div class="row-actions">
              ${actionButton(item, "select", "Open", "Opening...")}
              ${actionButton(item, "analyze", "Analyze", "Analyzing...")}
              ${actionButton(item, "summarize", "Summarize", "Summarizing...", "", item.status !== "processed")}
              ${actionButton(item, "download", "Download", "Downloading...")}
              ${actionButton(item, "delete", "Delete", "Deleting...", "danger")}
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
    elements.analysisQualityNotice.hidden = true;
    elements.analysisQualityNotice.textContent = "";
    elements.summaryState.textContent = "No document selected";
    elements.summaryPreview.textContent = "Analyze a document before generating an AI summary.";
    elements.contentReviewState.textContent = "No document selected";
    elements.contentReviewPreview.textContent = "Analyze a document before reviewing its content.";
    elements.contentReviewButton.disabled = true;
    elements.layoutReviewState.textContent = "No document selected";
    elements.layoutReviewPreview.textContent = "Select a PDF document to review its visual layout.";
    elements.layoutReviewButton.disabled = true;
    return;
  }

  elements.selectedState.textContent = `#${documentItem.id}`;
  elements.detailsPanel.innerHTML = `
    <div class="detail-grid">
      <div class="detail-row"><span class="detail-label">Filename</span><span>${escapeHtml(documentItem.filename)}</span></div>
      <div class="detail-row"><span class="detail-label">Status</span><span><span class="badge ${escapeHtml(documentItem.status)}">${escapeHtml(documentItem.status)}</span></span></div>
      <div class="detail-row"><span class="detail-label">Type</span><span>${escapeHtml(documentItem.content_type)}</span></div>
      <div class="detail-row"><span class="detail-label">Size</span><span>${formatBytes(documentItem.size_bytes)}</span></div>
      <div class="detail-row"><span class="detail-label">Language</span><span>${escapeHtml(documentLanguageLabel(documentItem))}</span></div>
      <div class="detail-row"><span class="detail-label">Words</span><span>${documentItem.word_count || 0}</span></div>
      <div class="detail-row"><span class="detail-label">Characters</span><span>${documentItem.char_count || 0}</span></div>
      ${
        documentItem.status === "processed"
          ? `<div class="detail-row"><span class="detail-label">Text quality</span><span>${escapeHtml(documentItem.extraction_quality || "unknown")}</span></div>`
          : ""
      }
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
      ${
        documentItem.content_review_error
          ? `<div class="detail-row"><span class="detail-label">Content review</span><span>${escapeHtml(documentItem.content_review_error)}</span></div>`
          : ""
      }
      ${
        documentItem.layout_review_error
          ? `<div class="detail-row"><span class="detail-label">Layout review</span><span>${escapeHtml(documentItem.layout_review_error)}</span></div>`
          : ""
      }
    </div>
  `;

  elements.previewState.textContent = documentItem.status === "processed" ? "Extracted text" : documentItem.status;
  const qualityWarning = extractionQualityWarning(documentItem);
  elements.analysisQualityNotice.hidden = !qualityWarning;
  elements.analysisQualityNotice.textContent = qualityWarning;
  elements.analysisPreview.textContent =
    documentItem.extracted_text || "Run analysis to extract text and compute document metrics.";
  elements.summaryState.textContent = documentItem.ai_error
    ? "Error"
    : documentItem.ai_summary
      ? documentItem.ai_model || "Generated"
      : documentItem.status === "processed"
        ? "Ready"
        : "Analyze first";
  const summaryText =
    documentItem.ai_summary ||
    documentItem.ai_error ||
    (documentItem.status === "processed"
      ? "AI summary has not been generated for this document."
      : "Document must be analyzed first.");
  elements.summaryPreview.textContent = qualityWarning
    ? `${qualityWarning}\n\n${summaryText}`
    : summaryText;

  const contentMeta = documentItem.content_review_meta || {};
  const contentPending = isPendingAction("content-review", documentItem.id);
  elements.contentReviewButton.disabled = documentItem.status !== "processed" || state.loading;
  elements.contentReviewButton.classList.toggle("loading", contentPending);
  elements.contentReviewButton.setAttribute("aria-busy", contentPending ? "true" : "false");
  elements.contentReviewButton.textContent = contentPending ? "Reviewing..." : "Review content";
  elements.contentReviewMode.disabled = state.loading;
  elements.contentReviewState.textContent = documentItem.content_review_error
    ? "Error"
    : documentItem.content_review
      ? `${documentItem.content_review_mode || "review"} · ${contentMeta.complete ? "full" : "sample"}${contentMeta.batch_count ? ` · ${contentMeta.batch_count} call batch(es)` : ""}`
      : documentItem.status === "processed"
        ? "Ready"
        : "Analyze first";
  const contentReviewText =
    documentItem.content_review ||
    documentItem.content_review_error ||
    (documentItem.status === "processed"
      ? "Choose a review depth and start the content quality review."
      : "Document must be analyzed first.");
  const contentReviewMarkdown = qualityWarning
    ? `${qualityWarning}\n\n${contentReviewText}`
    : contentReviewText;
  renderMarkdown(elements.contentReviewPreview, contentReviewMarkdown);

  const isPdf = documentItem.content_type === "application/pdf";
  const layoutMeta = documentItem.layout_review_meta || {};
  const layoutPending = isPendingAction("layout-review", documentItem.id);
  elements.layoutReviewButton.disabled = !isPdf || state.loading;
  elements.layoutReviewButton.classList.toggle("loading", layoutPending);
  elements.layoutReviewButton.setAttribute("aria-busy", layoutPending ? "true" : "false");
  elements.layoutReviewButton.textContent = layoutPending ? "Reviewing..." : "Review layout visually";
  elements.layoutReviewState.textContent = documentItem.layout_review_error
    ? "Error"
    : documentItem.layout_review
      ? `pages ${(layoutMeta.reviewed_pages || []).join(", ") || "reviewed"} · ${layoutMeta.complete ? "full" : "sample"}`
      : isPdf
        ? "Ready"
        : "PDF only";
  elements.layoutReviewPreview.textContent =
    documentItem.layout_review ||
    documentItem.layout_review_error ||
    (isPdf
      ? "Start an advisory visual review of selected PDF pages."
      : "Visual layout review is available only for PDF documents.");
}

function syncChatDocumentSelection() {
  const processed = processedDocuments();
  if (!processed.length) {
    state.chatDocumentId = null;
    return;
  }
  if (processed.some((item) => item.id === state.chatDocumentId)) {
    return;
  }
  const selected = selectedDocument();
  state.chatDocumentId = selected?.status === "processed" ? selected.id : processed[0].id;
}

function renderChat() {
  elements.aiChatPopup.hidden = !state.chatOpen;
  syncChatDocumentSelection();

  const processed = processedDocuments();
  elements.aiChatDocumentSelect.innerHTML = processed.length
    ? processed
        .map(
          (item) =>
            `<option value="${item.id}" ${item.id === state.chatDocumentId ? "selected" : ""}>#${item.id} ${escapeHtml(item.filename)}</option>`,
        )
        .join("")
    : '<option value="">No processed documents</option>';

  const chatDocument = selectedChatDocument();
  const disabled = !chatDocument || state.loading;
  elements.aiChatDocumentSelect.disabled = !processed.length;
  elements.aiChatInput.disabled = disabled;
  elements.aiChatSend.disabled = disabled;

  if (!chatDocument) {
    elements.aiChatState.textContent = "Analyze a document first.";
    elements.aiChatMessages.innerHTML = '<div class="empty">Processed documents will appear here.</div>';
    return;
  }

  const messages = readChatMessages(chatDocument.id);
  elements.aiChatState.textContent = `Answering from #${chatDocument.id}`;
  elements.aiChatMessages.innerHTML = messages.length
    ? messages
        .map(
          (message) =>
            `<div class="ai-chat-message ${escapeHtml(message.role)}">${escapeHtml(message.content)}</div>`,
        )
        .join("")
    : '<div class="empty">Ask a question about the selected document.</div>';
  elements.aiChatMessages.scrollTop = elements.aiChatMessages.scrollHeight;
}

function render() {
  renderMetrics();
  renderTable();
  renderDetails();
  renderChat();
}

function setLoading(isLoading) {
  state.loading = isLoading;
  elements.refreshButton.disabled = isLoading;
  elements.uploadButton.disabled = isLoading;
  elements.uploadButton.classList.toggle("loading", isPendingAction("upload"));
  elements.uploadButton.setAttribute("aria-busy", isPendingAction("upload") ? "true" : "false");
  elements.uploadButton.textContent = isPendingAction("upload") ? "Uploading..." : "Upload document";
  elements.contentReviewButton.disabled = isLoading || selectedDocument()?.status !== "processed";
  elements.contentReviewMode.disabled = isLoading;
  elements.layoutReviewButton.disabled =
    isLoading || selectedDocument()?.content_type !== "application/pdf";
  elements.tableState.textContent = isLoading ? "Loading" : elements.tableState.textContent;
}

function setPendingAction(action, documentId = null) {
  state.pendingAction = action ? { action, documentId } : null;
  setLoading(Boolean(action));
  render();
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
    await loadSession();
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
    if (handleApiError(error)) {
      return;
    }
    showToast(error.message, "error");
    elements.documentsBody.innerHTML = `<tr><td colspan="8" class="muted">Could not load data: ${escapeHtml(error.message)}</td></tr>`;
  } finally {
    setLoading(false);
  }
}

async function uploadSelectedFile(file) {
  if (!file) {
    showToast("Choose a PDF file first.", "error");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Only PDF files are supported.", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  setPendingAction("upload");
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
    if (handleApiError(error)) {
      return;
    }
    showToast(errorMessage(error), "error");
  } finally {
    setPendingAction(null);
  }
}

async function analyzeDocument(documentId) {
  setPendingAction("analyze", documentId);
  try {
    const updated = await fetchJson(`/api/documents/${documentId}/analyze`, { method: "POST" });
    state.selectedId = updated.id;
    showToast(updated.status === "failed" ? "Analysis failed." : "Analysis completed.", updated.status === "failed" ? "error" : "success");
    await loadData();
  } catch (error) {
    if (handleApiError(error)) {
      return;
    }
    showToast(error.message, "error");
  } finally {
    setPendingAction(null);
  }
}

async function summarizeDocument(documentId) {
  setPendingAction("summarize", documentId);
  try {
    const updated = await fetchJson(`/api/documents/${documentId}/summarize`, { method: "POST" });
    state.selectedId = updated.id;
    showToast("AI summary generated.", "success");
    await loadData();
  } catch (error) {
    if (handleApiError(error)) {
      return;
    }
    showToast(error.message, "error");
  } finally {
    setPendingAction(null);
  }
}

async function reviewDocumentContent(documentId) {
  setPendingAction("content-review", documentId);
  try {
    const updated = await fetchJson(`/api/documents/${documentId}/content-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: elements.contentReviewMode.value }),
    });
    state.selectedId = updated.id;
    showToast("Content quality review completed.", "success");
    await loadData();
  } catch (error) {
    if (handleApiError(error)) {
      return;
    }
    showToast(errorMessage(error), "error");
    await loadData();
  } finally {
    setPendingAction(null);
  }
}

async function reviewDocumentLayout(documentId) {
  setPendingAction("layout-review", documentId);
  try {
    const updated = await fetchJson(`/api/documents/${documentId}/layout-review`, {
      method: "POST",
    });
    state.selectedId = updated.id;
    showToast("Visual layout review completed.", "success");
    await loadData();
  } catch (error) {
    if (handleApiError(error)) {
      return;
    }
    showToast(errorMessage(error), "error");
    await loadData();
  } finally {
    setPendingAction(null);
  }
}

async function askSelectedDocument(question) {
  const chatDocument = selectedChatDocument();
  const cleanQuestion = question.trim();
  if (!chatDocument || !cleanQuestion) {
    return;
  }

  if (state.chatAbortController) {
    state.chatAbortController.abort();
  }
  const requestDocumentId = chatDocument.id;
  const controller = new AbortController();
  state.chatAbortController = controller;

  const messages = readChatMessages(requestDocumentId);
  const nextMessages = [...messages, { role: "user", content: cleanQuestion }];
  writeChatMessages(requestDocumentId, nextMessages);
  elements.aiChatInput.value = "";
  renderChat();

  try {
    const payload = await fetchJson(`/api/documents/${requestDocumentId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: cleanQuestion,
        history: messages.slice(-12),
      }),
      signal: controller.signal,
    });
    if (state.chatDocumentId !== requestDocumentId) {
      return;
    }
    const updatedMessages = [
      ...readChatMessages(requestDocumentId),
      {
        role: "assistant",
        content: payload.truncated_context
          ? `${payload.answer}\n\nNote: only the available extracted text was checked.`
          : payload.answer,
      },
    ];
    writeChatMessages(requestDocumentId, updatedMessages);
    renderChat();
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    if (handleApiError(error)) {
      return;
    }
    showToast(error.message, "error");
  } finally {
    if (state.chatAbortController === controller) {
      state.chatAbortController = null;
    }
  }
}

async function deleteDocument(documentId) {
  if (!confirm("Delete this document and its stored file?")) {
    return;
  }
  setPendingAction("delete", documentId);
  try {
    await fetchJson(`/api/documents/${documentId}`, { method: "DELETE" });
    if (state.selectedId === documentId) {
      state.selectedId = null;
    }
    showToast("Document deleted.", "success");
    await loadData();
  } catch (error) {
    if (handleApiError(error)) {
      return;
    }
    showToast(error.message, "error");
  } finally {
    setPendingAction(null);
  }
}

elements.themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  setTheme(current === "dark" ? "light" : "dark");
});

elements.aiChatToggle.addEventListener("click", () => {
  state.chatOpen = !state.chatOpen;
  if (state.chatOpen) {
    syncChatDocumentSelection();
  }
  renderChat();
  if (state.chatOpen) {
    elements.aiChatInput.focus();
  }
});

elements.aiChatClose.addEventListener("click", () => {
  state.chatOpen = false;
  renderChat();
});

elements.aiChatDocumentSelect.addEventListener("change", () => {
  if (state.chatAbortController) {
    state.chatAbortController.abort();
    state.chatAbortController = null;
  }
  state.chatDocumentId = Number(elements.aiChatDocumentSelect.value) || null;
  renderChat();
});

elements.aiChatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await askSelectedDocument(elements.aiChatInput.value);
});

elements.refreshButton.addEventListener("click", loadData);
elements.searchInput.addEventListener("input", renderTable);
elements.statusFilter.addEventListener("change", renderTable);
elements.contentReviewButton.addEventListener("click", async () => {
  const documentItem = selectedDocument();
  if (documentItem) {
    await reviewDocumentContent(documentItem.id);
  }
});
elements.layoutReviewButton.addEventListener("click", async () => {
  const documentItem = selectedDocument();
  if (documentItem) {
    await reviewDocumentLayout(documentItem.id);
  }
});

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

  if (state.loading) {
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
