const API_BASE = "http://127.0.0.1:8000";
const state = { document: null, queue: [] };

const elements = {
  connection: document.querySelector("#connection-state"),
  uploadForm: document.querySelector("#upload-form"),
  fileInput: document.querySelector("#receipt-file"),
  selectedFile: document.querySelector("#selected-file"),
  uploadButton: document.querySelector("#upload-button"),
  uploadStatus: document.querySelector("#upload-status"),
  documentEmpty: document.querySelector("#document-empty"),
  documentContent: document.querySelector("#document-content"),
  queue: document.querySelector("#review-queue"),
  queueCount: document.querySelector("#queue-count"),
  metricDocuments: document.querySelector("#metric-documents"),
  metricAccepted: document.querySelector("#metric-accepted"),
  metricReview: document.querySelector("#metric-review"),
  fieldTemplate: document.querySelector("#field-card-template"),
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;" })[character]);
}

function titleCase(value) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function percentage(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* Use default message. */ }
    throw new Error(detail);
  }
  return response.json();
}

async function checkHealth() {
  try {
    await api("/health");
    elements.connection.className = "connection-state online";
    elements.connection.innerHTML = "<i></i> API connected";
  } catch (_) {
    elements.connection.className = "connection-state offline";
    elements.connection.innerHTML = "<i></i> API unavailable";
  }
}

async function refreshMetrics() {
  try {
    const metrics = await api("/metrics");
    elements.metricDocuments.textContent = metrics.document_count || 0;
    elements.metricAccepted.textContent = metrics.decisions.accept || 0;
    elements.metricReview.textContent = (metrics.decisions.review || 0) + (metrics.decisions.abstain || 0);
  } catch (_) { /* Connection state already communicates the failure. */ }
}

async function refreshQueue() {
  try {
    state.queue = await api("/reviews");
    renderQueue();
  } catch (error) {
    elements.queue.innerHTML = `<p class="queue-empty">${escapeHtml(error.message)}</p>`;
  }
}

function renderQueue() {
  elements.queueCount.textContent = `${state.queue.length} pending`;
  if (!state.queue.length) {
    elements.queue.innerHTML = "<p class=\"queue-empty\">No pending fields. The review queue is clear.</p>";
    return;
  }
  elements.queue.innerHTML = state.queue.map((item) => `
    <article class="queue-item">
      <div>
        <p class="queue-title">Document #${item.document_id} · ${escapeHtml(titleCase(item.field_name))}</p>
        <p class="queue-subtitle">${escapeHtml(item.review_candidate || "No proposed value — manual entry required")} · ${escapeHtml(item.original_filename)}</p>
      </div>
      <button type="button" data-document-id="${item.document_id}">Open review</button>
    </article>
  `).join("");
}

function makeOverview(documentRecord) {
  const counts = documentRecord.fields.reduce((result, field) => {
    result[field.decision] = (result[field.decision] || 0) + 1;
    return result;
  }, {});
  return [
    [counts.accept || 0, "Accepted"],
    [counts.review || 0, "Review"],
    [counts.abstain || 0, "Abstain"],
  ].map(([value, label]) => `<div class="overview-stat"><strong>${value}</strong><span>${label}</span></div>`).join("");
}

function renderDocument(documentRecord) {
  state.document = documentRecord;
  elements.documentEmpty.hidden = true;
  elements.documentContent.hidden = false;
  const created = new Date(documentRecord.created_at).toLocaleString();
  elements.documentContent.innerHTML = `
    <div class="document-header">
      <div>
        <p class="eyebrow">Processed document #${documentRecord.id}</p>
        <h2 title="${escapeHtml(documentRecord.original_filename)}">${escapeHtml(documentRecord.original_filename)}</h2>
        <p class="document-meta">${documentRecord.ocr_line_count} OCR lines · ${escapeHtml(created)}</p>
      </div>
      <div class="document-overview">${makeOverview(documentRecord)}</div>
    </div>
    <div class="field-grid" id="field-grid"></div>
  `;
  const grid = elements.documentContent.querySelector("#field-grid");
  documentRecord.fields.forEach((field) => grid.appendChild(createFieldCard(documentRecord, field)));
}

function createFieldCard(documentRecord, field) {
  const fragment = elements.fieldTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".field-card");
  const candidate = field.candidate_value || field.review_candidate || "No value extracted";
  card.classList.add(`decision-${field.decision}`);
  card.querySelector(".field-label").textContent = titleCase(field.field_name);
  const value = card.querySelector(".field-value");
  value.textContent = candidate;
  if (!field.candidate_value) value.classList.add("empty-value");
  const tag = card.querySelector(".decision-tag");
  tag.textContent = field.decision;
  tag.classList.add(field.decision);
  card.querySelector(".confidence-value").textContent = percentage(field.confidence_score);
  card.querySelector(".confidence-bar").style.width = percentage(field.confidence_score);
  card.querySelector(".evidence-ocr").textContent = percentage(field.ocr_quality);
  card.querySelector(".evidence-format").textContent = percentage(field.format_validity);
  card.querySelector(".evidence-context").textContent = percentage(field.context_evidence);
  card.querySelector(".rule-text").textContent = `Rule: ${field.extraction_rule.replace(/_/g, " ")}`;

  const reviewArea = card.querySelector(".review-area");
  if (field.review_status === "pending" && ["review", "abstain"].includes(field.decision)) {
    const prefill = field.review_candidate || "";
    reviewArea.innerHTML = `
      <form class="review-form" data-document-id="${documentRecord.id}" data-field-name="${field.field_name}" data-candidate="${escapeHtml(prefill)}">
        <label for="review-${documentRecord.id}-${field.field_name}">Human-verified value</label>
        <input id="review-${documentRecord.id}-${field.field_name}" name="human_value" value="${escapeHtml(prefill)}" placeholder="Enter verified value" required />
        <div class="review-actions"><button class="secondary-button" type="submit">Save review</button></div>
      </form>
    `;
  } else if (field.review_status !== "not_required") {
    reviewArea.innerHTML = `<p class="review-note">Human ${escapeHtml(field.review_status)} value: ${escapeHtml(field.human_value || "")}</p>`;
  } else if (field.automation_value) {
    reviewArea.innerHTML = `<p class="review-note">Automation value: ${escapeHtml(field.automation_value)}</p>`;
  }
  return fragment;
}

async function loadDocument(documentId) {
  try {
    const document = await api(`/documents/${documentId}`);
    renderDocument(document);
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (error) {
    setStatus(error.message, "error");
  }
}

function setStatus(message, kind = "") {
  elements.uploadStatus.className = `form-status ${kind}`;
  elements.uploadStatus.textContent = message;
}

elements.fileInput.addEventListener("change", () => {
  const [file] = elements.fileInput.files;
  elements.selectedFile.textContent = file ? file.name : "No file selected";
});

elements.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const [file] = elements.fileInput.files;
  if (!file) return setStatus("Choose a receipt image before processing.", "error");
  elements.uploadButton.disabled = true;
  elements.uploadButton.textContent = "Processing receipt";
  setStatus("Running OCR, confidence scoring, and calibrated policy.");
  try {
    const form = new FormData();
    form.append("file", file);
    const document = await api("/documents", { method: "POST", body: form });
    renderDocument(document);
    setStatus(`Document #${document.id} was processed and saved.`, "success");
    await Promise.all([refreshMetrics(), refreshQueue()]);
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    elements.uploadButton.disabled = false;
    elements.uploadButton.textContent = "Process receipt";
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target.closest(".review-form");
  if (!form) return;
  event.preventDefault();
  const value = form.human_value.value.trim();
  if (!value) return;
  const candidate = form.dataset.candidate;
  const status = value === candidate ? "approved" : "corrected";
  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "Saving";
  try {
    await api(`/documents/${form.dataset.documentId}/fields/${form.dataset.fieldName}/review`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ human_value: value, review_status: status }),
    });
    await Promise.all([loadDocument(form.dataset.documentId), refreshMetrics(), refreshQueue()]);
  } catch (error) {
    button.disabled = false;
    button.textContent = error.message;
  }
});

elements.queue.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-document-id]");
  if (button) loadDocument(button.dataset.documentId);
});

Promise.all([checkHealth(), refreshMetrics(), refreshQueue()]);
