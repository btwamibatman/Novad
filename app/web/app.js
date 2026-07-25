const state = {
  documents: [],
  summary: null,
  session: null,
  selectedId: null,
  chatDocumentId: null,
  chatOpen: false,
  chatAbortController: null,
  pendingAction: null,
  analysisPollTimer: null,
  loading: false,
  language: "en",
  translations: {},
};

const elements = {
  authView: document.querySelector("#authView"),
  appShell: document.querySelector("#appShell"),
  loginForm: document.querySelector("#loginForm"),
  loginUsername: document.querySelector("#loginUsername"),
  loginPassword: document.querySelector("#loginPassword"),
  loginButton: document.querySelector("#loginButton"),
  loginError: document.querySelector("#loginError"),
  logoutButton: document.querySelector("#logoutButton"),
  currentUsername: document.querySelector("#currentUsername"),
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
  languageButtons: document.querySelectorAll("[data-language]"),
};

function t(key, params = {}) {
  const template = state.translations[key] || key;
  return Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

function applyStaticTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((element) => {
    element.title = t(element.dataset.i18nTitle);
  });
}

async function setLanguage(language) {
  const selectedLanguage = ["en", "ru"].includes(language) ? language : "en";
  const response = await fetch(`/web/i18n/${selectedLanguage}.json`);
  if (!response.ok) {
    throw new Error(t("errors.translation_load", { language: selectedLanguage }));
  }
  const translations = await response.json();
  state.language = selectedLanguage;
  state.translations = translations;
  document.documentElement.lang = selectedLanguage;
  localStorage.setItem("document-console-language", selectedLanguage);
  elements.languageButtons.forEach((button) => {
    const active = button.dataset.language === selectedLanguage;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  applyStaticTranslations();
  setTheme(
    localStorage.getItem("document-console-theme") ||
      document.documentElement.getAttribute("data-theme") ||
      "dark",
  );
  render();
}

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
  const pageLabel = pages.length ? t("analysis.pages_to_verify", { pages: pages.join(", ") }) : "";
  return t("analysis.quality_warning", {
    quality: extractionQualityLabel(documentItem.extraction_quality),
    pages: pageLabel,
  });
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

function statusLabel(status) {
  return state.translations[`status.${status}`] || status;
}

function extractionQualityLabel(quality) {
  const value = quality || "unknown";
  return state.translations[`quality.${value}`] || value;
}

function contentReviewModeLabel(mode) {
  const value = mode || "review";
  return state.translations[`content_review.mode_${value}`] || value;
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
  elements.themeIcon.textContent = theme === "dark" ? t("theme.sun") : t("theme.moon");
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
    const detail = typeof payload === "string" ? payload : payload.detail || t("errors.request_failed");
    const message = typeof detail === "string" ? detail : detail.message || t("errors.request_failed");
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
  state.session = await fetchJson("/api/auth/me");
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

function showLoginView(message = "") {
  elements.authView.hidden = false;
  elements.appShell.hidden = true;
  elements.aiChatToggle.hidden = true;
  elements.aiChatPopup.hidden = true;
  elements.currentUsername.textContent = "";
  elements.loginError.textContent = message;
  elements.loginError.hidden = !message;
  elements.loginPassword.value = "";
  requestAnimationFrame(() => elements.loginUsername.focus());
}

function showAppView() {
  elements.authView.hidden = true;
  elements.appShell.hidden = false;
  elements.aiChatToggle.hidden = false;
  elements.currentUsername.textContent = state.session?.user?.username || "";
  elements.loginError.hidden = true;
}

function clearSessionState(message = t("auth.session_expired")) {
  if (state.analysisPollTimer) {
    clearTimeout(state.analysisPollTimer);
    state.analysisPollTimer = null;
  }
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
  state.chatOpen = false;
  render();
  showLoginView(message);
}

function handleApiError(error) {
  if (error.status === 401) {
    clearSessionState();
    return true;
  }
  if (error.status === 429) {
    showToast(t("errors.rate_limit", { seconds: error.retryAfter || t("errors.a_few") }), "error");
    return true;
  }
  return false;
}

function errorMessage(error) {
  const detail = error.payload?.detail;
  if (detail && typeof detail === "object" && detail.used_bytes !== undefined) {
    return t("errors.quota", {
      message: detail.message || error.message,
      used: formatBytes(detail.used_bytes),
      quota: formatBytes(detail.quota_bytes),
    });
  }
  return error.message;
}

function aiBadge(documentItem) {
  if (documentItem.ai_error || documentItem.content_review_error || documentItem.layout_review_error) {
    return `<span class="badge failed">${escapeHtml(t("ai.error"))}</span>`;
  }
  if (documentItem.ai_summary || documentItem.content_review || documentItem.layout_review) {
    return `<span class="badge processed">${escapeHtml(t("ai.ready"))}</span>`;
  }
  return `<span class="badge uploaded">${escapeHtml(t("ai.none"))}</span>`;
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
    elements.languageList.innerHTML = `<span class="muted">${escapeHtml(t("languages.empty"))}</span>`;
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

  elements.tableState.textContent = t("documents.shown", { count: documents.length });

  if (!documents.length) {
    elements.documentsBody.innerHTML = `<tr><td colspan="8" class="muted">${escapeHtml(t("documents.empty"))}</td></tr>`;
    return;
  }

  elements.documentsBody.innerHTML = documents
    .map(
      (item) => `
        <tr data-document-id="${item.id}" data-selected="${item.id === state.selectedId}">
          <td>
            <p class="file-name">${escapeHtml(item.filename)}</p>
            <span class="file-meta">#${item.id} ${escapeHtml(t("documents.created", { date: new Date(item.created_at).toLocaleString(state.language) }))}</span>
          </td>
          <td>${escapeHtml(item.content_type)}</td>
          <td><span class="badge ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span></td>
          <td>${formatBytes(item.size_bytes)}</td>
          <td>${escapeHtml(documentLanguageLabel(item))}</td>
          <td>${item.word_count || 0}</td>
          <td>${aiBadge(item)}</td>
          <td>
            <div class="row-actions">
              ${actionButton(item, "select", t("documents.open"), t("documents.opening"))}
              ${actionButton(item, "analyze", t("documents.analyze"), t("documents.analyzing"))}
              ${actionButton(item, "summarize", t("documents.summarize"), t("documents.summarizing"), "", item.status !== "processed")}
              ${actionButton(item, "download", t("documents.download"), t("documents.downloading"))}
              ${actionButton(item, "delete", t("documents.delete"), t("documents.deleting"), "danger")}
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
    elements.selectedState.textContent = t("common.none");
    elements.detailsPanel.innerHTML = `<div class="empty">${escapeHtml(t("details.select_document"))}</div>`;
    elements.previewState.textContent = t("common.no_document_selected");
    elements.analysisPreview.textContent = t("analysis.select_processed");
    elements.analysisQualityNotice.hidden = true;
    elements.analysisQualityNotice.textContent = "";
    elements.summaryState.textContent = t("common.no_document_selected");
    elements.summaryPreview.textContent = t("summary.analyze_first_help");
    elements.contentReviewState.textContent = t("common.no_document_selected");
    elements.contentReviewPreview.textContent = t("content_review.analyze_first_help");
    elements.contentReviewButton.disabled = true;
    elements.layoutReviewState.textContent = t("common.no_document_selected");
    elements.layoutReviewPreview.textContent = t("layout_review.select_pdf");
    elements.layoutReviewButton.disabled = true;
    return;
  }

  elements.selectedState.textContent = `#${documentItem.id}`;
  const analysisProgress = documentItem.analysis_progress || {};
  const progressText =
    documentItem.status === "analyzing"
      ? t("analysis.progress", {
          completed: analysisProgress.completed_pages ?? 0,
          total: analysisProgress.total_pages ?? "?",
          stage: analysisProgress.stage || "queued",
        })
      : "";
  elements.detailsPanel.innerHTML = `
    <div class="detail-grid">
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.filename"))}</span><span>${escapeHtml(documentItem.filename)}</span></div>
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.status"))}</span><span><span class="badge ${escapeHtml(documentItem.status)}">${escapeHtml(statusLabel(documentItem.status))}</span></span></div>
      ${progressText ? `<div class="detail-row"><span class="detail-label">${escapeHtml(t("analysis.title"))}</span><span>${escapeHtml(progressText)}</span></div>` : ""}
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.type"))}</span><span>${escapeHtml(documentItem.content_type)}</span></div>
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.size"))}</span><span>${formatBytes(documentItem.size_bytes)}</span></div>
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.language"))}</span><span>${escapeHtml(documentLanguageLabel(documentItem))}</span></div>
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.words"))}</span><span>${documentItem.word_count || 0}</span></div>
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.characters"))}</span><span>${documentItem.char_count || 0}</span></div>
      ${
        documentItem.status === "processed"
          ? `<div class="detail-row"><span class="detail-label">${escapeHtml(t("details.text_quality"))}</span><span>${escapeHtml(extractionQualityLabel(documentItem.extraction_quality))}</span></div>`
          : ""
      }
      <div class="detail-row"><span class="detail-label">AI</span><span>${aiBadge(documentItem)}</span></div>
      ${
        documentItem.ai_model
          ? `<div class="detail-row"><span class="detail-label">${escapeHtml(t("details.ai_model"))}</span><span>${escapeHtml(documentItem.ai_model)}</span></div>`
          : ""
      }
      <div class="detail-row"><span class="detail-label">${escapeHtml(t("details.updated"))}</span><span>${escapeHtml(new Date(documentItem.updated_at).toLocaleString(state.language))}</span></div>
      ${
        documentItem.error_message
          ? `<div class="detail-row"><span class="detail-label">${escapeHtml(t("details.error"))}</span><span>${escapeHtml(documentItem.error_message)}</span></div>`
          : ""
      }
      ${
        documentItem.ai_error
          ? `<div class="detail-row"><span class="detail-label">${escapeHtml(t("details.ai_error"))}</span><span>${escapeHtml(documentItem.ai_error)}</span></div>`
          : ""
      }
      ${
        documentItem.content_review_error
          ? `<div class="detail-row"><span class="detail-label">${escapeHtml(t("details.content_review"))}</span><span>${escapeHtml(documentItem.content_review_error)}</span></div>`
          : ""
      }
      ${
        documentItem.layout_review_error
          ? `<div class="detail-row"><span class="detail-label">${escapeHtml(t("details.layout_review"))}</span><span>${escapeHtml(documentItem.layout_review_error)}</span></div>`
          : ""
      }
    </div>
  `;

  elements.previewState.textContent = documentItem.status === "processed" ? t("analysis.extracted_text") : statusLabel(documentItem.status);
  const qualityWarning = extractionQualityWarning(documentItem);
  elements.analysisQualityNotice.hidden = !qualityWarning;
  elements.analysisQualityNotice.textContent = qualityWarning;
  elements.analysisPreview.textContent =
    documentItem.extracted_text || t("analysis.run");
  elements.summaryState.textContent = documentItem.ai_error
    ? t("common.error")
    : documentItem.ai_summary
      ? documentItem.ai_model || t("common.generated")
      : documentItem.status === "processed"
        ? t("common.ready")
        : t("common.analyze_first");
  const summaryText =
    documentItem.ai_summary ||
    documentItem.ai_error ||
    (documentItem.status === "processed"
      ? t("summary.not_generated")
      : t("summary.must_analyze"));
  elements.summaryPreview.textContent = qualityWarning
    ? `${qualityWarning}\n\n${summaryText}`
    : summaryText;

  const contentMeta = documentItem.content_review_meta || {};
  const contentPending = isPendingAction("content-review", documentItem.id);
  elements.contentReviewButton.disabled = documentItem.status !== "processed" || state.loading;
  elements.contentReviewButton.classList.toggle("loading", contentPending);
  elements.contentReviewButton.setAttribute("aria-busy", contentPending ? "true" : "false");
  elements.contentReviewButton.textContent = contentPending ? t("content_review.reviewing") : t("content_review.action");
  elements.contentReviewMode.disabled = state.loading;
  elements.contentReviewState.textContent = documentItem.content_review_error
    ? t("common.error")
    : documentItem.content_review
      ? t("content_review.state", {
          mode: contentReviewModeLabel(documentItem.content_review_mode),
          coverage: contentMeta.complete ? t("common.full") : t("common.sample"),
          batches: contentMeta.batch_count ? t("content_review.batches", { count: contentMeta.batch_count }) : "",
        })
      : documentItem.status === "processed"
        ? t("common.ready")
        : t("common.analyze_first");
  const contentReviewText =
    documentItem.content_review ||
    documentItem.content_review_error ||
    (documentItem.status === "processed"
      ? t("content_review.start")
      : t("summary.must_analyze"));
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
  elements.layoutReviewButton.textContent = layoutPending ? t("layout_review.reviewing") : t("layout_review.action");
  elements.layoutReviewState.textContent = documentItem.layout_review_error
    ? t("common.error")
    : documentItem.layout_review
      ? t("layout_review.state", {
          pages: (layoutMeta.reviewed_pages || []).join(", ") || t("common.reviewed"),
          coverage: layoutMeta.complete ? t("common.full") : t("common.sample"),
        })
      : isPdf
        ? t("common.ready")
        : t("common.pdf_only");
  elements.layoutReviewPreview.textContent =
    documentItem.layout_review ||
    documentItem.layout_review_error ||
    (isPdf
      ? t("layout_review.start")
      : t("layout_review.pdf_only"));
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
    : `<option value="">${escapeHtml(t("chat.no_processed"))}</option>`;

  const chatDocument = selectedChatDocument();
  const disabled = !chatDocument || state.loading;
  elements.aiChatDocumentSelect.disabled = !processed.length;
  elements.aiChatInput.disabled = disabled;
  elements.aiChatSend.disabled = disabled;

  if (!chatDocument) {
    elements.aiChatState.textContent = t("chat.analyze_first");
    elements.aiChatMessages.innerHTML = `<div class="empty">${escapeHtml(t("chat.processed_appear"))}</div>`;
    return;
  }

  const messages = readChatMessages(chatDocument.id);
  elements.aiChatState.textContent = t("chat.answering_from", { id: chatDocument.id });
  elements.aiChatMessages.innerHTML = messages.length
    ? messages
        .map(
          (message) =>
            `<div class="ai-chat-message ${escapeHtml(message.role)}">${escapeHtml(message.content)}</div>`,
        )
        .join("")
    : `<div class="empty">${escapeHtml(t("chat.ask_question"))}</div>`;
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
  elements.uploadButton.textContent = isPendingAction("upload") ? t("upload.uploading") : t("upload.action");
  elements.contentReviewButton.disabled = isLoading || selectedDocument()?.status !== "processed";
  elements.contentReviewMode.disabled = isLoading;
  elements.layoutReviewButton.disabled =
    isLoading || selectedDocument()?.content_type !== "application/pdf";
  elements.tableState.textContent = isLoading ? t("common.loading") : elements.tableState.textContent;
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

async function loadData(refreshSession = true) {
  setLoading(true);
  renderSkeleton();
  try {
    if (refreshSession) {
      await loadSession();
    }
    showAppView();
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
    scheduleAnalysisPoll();
  } catch (error) {
    if (handleApiError(error)) {
      return;
    }
    showToast(error.message, "error");
    elements.documentsBody.innerHTML = `<tr><td colspan="8" class="muted">${escapeHtml(t("documents.load_error", { message: error.message }))}</td></tr>`;
  } finally {
    setLoading(false);
  }
}

function scheduleAnalysisPoll() {
  if (state.analysisPollTimer) {
    clearTimeout(state.analysisPollTimer);
    state.analysisPollTimer = null;
  }
  if (!state.documents.some((item) => item.status === "analyzing")) {
    return;
  }
  state.analysisPollTimer = setTimeout(async () => {
    state.analysisPollTimer = null;
    await loadData(false);
  }, 1500);
}

async function uploadSelectedFile(file) {
  if (!file) {
    showToast(t("upload.choose_pdf"), "error");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast(t("upload.pdf_only"), "error");
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
    showToast(t("upload.completed"), "success");
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
    showToast(t("analysis.queued"), "success");
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
    showToast(t("summary.generated"), "success");
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
    showToast(t("content_review.completed"), "success");
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
  if (!confirm(t("layout_review.consent_confirm"))) {
    return;
  }
  setPendingAction("layout-review", documentId);
  try {
    const updated = await fetchJson(`/api/documents/${documentId}/layout-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent_to_external_image_processing: true }),
    });
    state.selectedId = updated.id;
    showToast(t("layout_review.completed"), "success");
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
          ? `${payload.answer}\n\n${t("chat.truncated_note")}`
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
  if (!confirm(t("delete.confirm"))) {
    return;
  }
  setPendingAction("delete", documentId);
  try {
    await fetchJson(`/api/documents/${documentId}`, { method: "DELETE" });
    if (state.selectedId === documentId) {
      state.selectedId = null;
    }
    showToast(t("delete.completed"), "success");
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

async function login(event) {
  event.preventDefault();
  elements.loginButton.disabled = true;
  elements.loginButton.classList.add("loading");
  elements.loginError.hidden = true;
  try {
    state.session = await fetchJson("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: elements.loginUsername.value,
        password: elements.loginPassword.value,
      }),
    });
    elements.loginPassword.value = "";
    showAppView();
    await loadData(false);
  } catch (error) {
    if (error.status === 401) {
      elements.loginError.textContent = t("auth.invalid_credentials");
    } else if (error.status === 429) {
      elements.loginError.textContent = t("errors.rate_limit", {
        seconds: error.retryAfter || t("errors.a_few"),
      });
    } else {
      elements.loginError.textContent = error.message || t("errors.request_failed");
    }
    elements.loginError.hidden = false;
  } finally {
    elements.loginButton.disabled = false;
    elements.loginButton.classList.remove("loading");
  }
}

async function logout() {
  elements.logoutButton.disabled = true;
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
  } catch (error) {
    if (error.status !== 401) {
      showToast(error.message, "error");
    }
  } finally {
    elements.logoutButton.disabled = false;
    clearSessionState("");
  }
}

elements.loginForm.addEventListener("submit", login);
elements.logoutButton.addEventListener("click", logout);

elements.themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  setTheme(current === "dark" ? "light" : "dark");
});

elements.languageButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    if (button.dataset.language === state.language) {
      return;
    }
    try {
      await setLanguage(button.dataset.language);
    } catch (error) {
      showToast(error.message, "error");
    }
  });
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

async function initialize() {
  const savedLanguage = localStorage.getItem("document-console-language") || "en";
  try {
    await setLanguage(savedLanguage);
  } catch (error) {
    if (savedLanguage !== "en") {
      try {
        await setLanguage("en");
      } catch (fallbackError) {
        console.error(fallbackError);
      }
    } else {
      console.error(error);
    }
    setTheme(localStorage.getItem("document-console-theme") || "dark");
  }
  try {
    await loadSession();
    showAppView();
    await loadData(false);
  } catch (error) {
    if (error.status === 401) {
      showLoginView();
      return;
    }
    showLoginView(error.message || t("errors.request_failed"));
  }
}

initialize();
