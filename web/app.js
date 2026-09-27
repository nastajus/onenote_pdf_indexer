const state = {
  sections: [],
  selectedSectionId: null,
  selectedPage: null,
  pages: [],
  resources: [],
  viewMode: localStorage.getItem("onenote-view-mode") || "pdf",
  searchPdfContent: localStorage.getItem("onenote-search-pdf") === "1",
  searchResults: [],
  searchTimer: null,
  collapsedPanels: JSON.parse(localStorage.getItem("onenote-collapsed-panels") || "{}"),
};

const accountStatus = document.querySelector("#accountStatus");
const notebooksList = document.querySelector("#notebooksList");
const sectionsList = document.querySelector("#sectionsList");
const pagesList = document.querySelector("#pagesList");
const resourcesList = document.querySelector("#resourcesList");
const queryInput = document.querySelector("#queryInput");
const grid = document.querySelector(".grid");
const viewPdfButton = document.querySelector("#viewPdfButton");
const viewTextButton = document.querySelector("#viewTextButton");
const searchPdfButton = document.querySelector("#searchPdfButton");
const refreshSelectedButton = document.querySelector("#refreshSelectedButton");
const resetLayoutButton = document.querySelector("#resetLayoutButton");
const splitters = document.querySelectorAll(".splitter");
const panels = document.querySelectorAll("[data-panel]");
const cacheProgress = document.querySelector("#cacheProgress");
const cacheProgressFill = document.querySelector("#cacheProgressFill");
const cacheProgressLabel = document.querySelector("#cacheProgressLabel");
const cacheProgressCount = document.querySelector("#cacheProgressCount");

document.querySelector("#refreshButton").addEventListener("click", () => {
  loadBasics({ refresh: true });
});

queryInput.addEventListener("input", () => {
  handleQueryInput();
});

viewPdfButton.addEventListener("click", () => {
  setViewMode("pdf");
});

viewTextButton.addEventListener("click", () => {
  setViewMode("text");
});

searchPdfButton.addEventListener("click", () => {
  setPdfSearchMode(!state.searchPdfContent);
});

refreshSelectedButton.addEventListener("click", () => {
  if (state.selectedPage) {
    loadResources(state.selectedPage, { refresh: true });
  } else if (state.selectedSectionId) {
    selectSection(state.selectedSectionId, { refresh: true });
  } else {
    loadBasics({ refresh: true });
  }
});

resetLayoutButton.addEventListener("click", () => {
  resetLayout();
});

document.querySelectorAll("[data-collapse-panel]").forEach((button) => {
  button.addEventListener("click", () => setPanelCollapsed(button.dataset.collapsePanel, true));
});

document.querySelectorAll("[data-expand-panel]").forEach((button) => {
  button.addEventListener("click", () => setPanelCollapsed(button.dataset.expandPanel, false));
});

async function api(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderError(container, error) {
  container.innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
}

function renderItems(container, items, options) {
  if (!items.length) {
    container.textContent = options.emptyText;
    return;
  }

  container.innerHTML = items
    .map((item, index) => {
      const title = options.title(item, index);
      const meta = options.meta(item, index);
      return `
        <div class="item">
          <div class="item-title">${escapeHtml(title)}</div>
          <div class="item-meta">${escapeHtml(meta)}</div>
        </div>
      `;
    })
    .join("");
}

async function loadBasics({ refresh = false } = {}) {
  const refreshParam = refresh ? "?refresh=1" : "";
  accountStatus.textContent = "Checking Microsoft Graph connection...";
  notebooksList.textContent = "Loading...";
  sectionsList.textContent = "Loading...";

  try {
    const me = await api("/api/whoami");
    accountStatus.textContent = `Signed in as ${me.mail || me.userPrincipalName || me.displayName}`;
  } catch (error) {
    accountStatus.innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
  }

  try {
    const notebooks = await api(`/api/notebooks${refreshParam}`);
    renderItems(notebooksList, notebooks, {
      emptyText: "No notebooks found.",
      title: (item) => item.displayName,
      meta: (item) => item.lastModifiedDateTime || item.id,
    });
  } catch (error) {
    renderError(notebooksList, error);
  }

  try {
    state.sections = await api(`/api/sections${refreshParam}`);
    renderSections();

    const selectedStillExists = state.sections.some((section) => section.id === state.selectedSectionId);
    if (!selectedStillExists) {
      selectFirstSectionWithPages({ refresh });
    } else if (state.selectedSectionId) {
      selectSection(state.selectedSectionId, { refresh });
    }
  } catch (error) {
    renderError(sectionsList, error);
  }

  loadCacheMetrics();
}

async function selectFirstSectionWithPages({ refresh = false } = {}) {
  for (const section of state.sections) {
    await selectSection(section.id, { refresh });
    if (state.pages.length) {
      return;
    }
  }
}

function renderSections() {
  if (!state.sections.length) {
    sectionsList.textContent = "No sections found.";
    return;
  }

  sectionsList.innerHTML = "";
  for (const section of state.sections) {
    const button = document.createElement("button");
    button.className = `item${section.id === state.selectedSectionId ? " active" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <div class="item-title">${escapeHtml(section.displayName || "Untitled section")}</div>
      <div class="item-meta">${escapeHtml(section.lastModifiedDateTime || section.id)}</div>
    `;
    button.addEventListener("click", () => selectSection(section.id));
    sectionsList.append(button);
  }
}

async function selectSection(sectionId, { refresh = false } = {}) {
  state.selectedSectionId = sectionId;
  state.selectedPage = null;
  state.pages = [];
  state.resources = [];
  resourcesList.textContent = "Select a page to inspect its PDF/image resources.";
  pagesList.textContent = "Loading section pages...";
  renderSections();

  const params = new URLSearchParams({ section_id: sectionId });
  if (refresh) {
    params.set("refresh", "1");
  }

  try {
    state.pages = await api(`/api/pages?${params}`);
    handleQueryInput();
  } catch (error) {
    renderError(pagesList, error);
  }
}

function handleQueryInput() {
  window.clearTimeout(state.searchTimer);
  const query = queryInput.value.trim();

  if (!state.searchPdfContent || query.length < 2) {
    state.searchResults = [];
    renderPages();
    return;
  }

  pagesList.textContent = "Searching cached PDF text...";
  state.searchTimer = window.setTimeout(() => {
    loadPdfSearch(query);
  }, 250);
}

async function loadPdfSearch(query) {
  const params = new URLSearchParams({ q: query, limit: "75" });
  if (state.selectedSectionId) {
    params.set("section_id", state.selectedSectionId);
  }

  try {
    const payload = await api(`/api/search?${params}`);
    if (query !== queryInput.value.trim()) {
      return;
    }
    state.searchResults = payload.results || [];
    renderPages();
  } catch (error) {
    renderError(pagesList, error);
  }
}

function renderPages() {
  const query = queryInput.value.trim().toLowerCase();
  if (state.searchPdfContent && query.length >= 2) {
    renderPdfSearchResults();
    return;
  }

  const pages = state.pages.filter((page) => {
    const section = page._section?.displayName || "";
    const title = page.title || "";
    return `${section} ${title}`.toLowerCase().includes(query);
  });

  if (!pages.length) {
    pagesList.textContent = state.pages.length ? "No pages match this filter." : "No pages found in this section.";
    return;
  }

  pagesList.innerHTML = "";
  for (const page of pages) {
    const button = document.createElement("button");
    const resourceCount = page._cache?.resource_count || 0;
    button.className = "item page-item";
    button.type = "button";
    const cacheMark = resourceCount
      ? `<span class="cache-mark" title="Contents cached locally: ${resourceCount} embedded resource${resourceCount === 1 ? "" : "s"}">&#9670;</span>`
      : "";
    button.innerHTML = `
      <div class="page-item-main">
        <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
        <div class="item-meta">${escapeHtml(page.lastModifiedDateTime || page.id)}</div>
      </div>
      ${cacheMark}
    `;
    button.addEventListener("click", () => loadResources(page));
    pagesList.append(button);
  }
}

function renderPdfSearchResults() {
  const query = queryInput.value.trim();
  if (!state.searchResults.length) {
    pagesList.textContent = query ? "No cached PDF text matches this search." : "Enter a search term.";
    return;
  }

  pagesList.innerHTML = "";
  for (const result of state.searchResults) {
    const page = result.page || {};
    const button = document.createElement("button");
    button.className = "item page-item search-hit";
    button.type = "button";
    button.innerHTML = `
      <div class="page-item-main">
        <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
        <div class="item-meta">PDF page ${escapeHtml(result.pdf_page_number || "?")} &middot; ${escapeHtml(page.lastModifiedDateTime || result.page_id)}</div>
        <div class="search-hit-snippet">${escapeHtml(result.snippet || "")}</div>
      </div>
      <span class="cache-mark" title="Matched cached extracted PDF text">&#9671;</span>
    `;
    button.addEventListener("click", () => loadResources(page));
    pagesList.append(button);
  }
}

async function loadResources(page, { refresh = false } = {}) {
  state.selectedPage = page;
  state.resources = [];
  resourcesList.textContent = `Inspecting ${page.title || "page"}...`;

  const params = new URLSearchParams({ page_id: page.id });
  if (refresh) {
    params.set("refresh", "1");
  }

  try {
    state.resources = await api(`/api/resources?${params}`);
    page._cache = {
      ...(page._cache || {}),
      resource_count: state.resources.filter((resource) => resource.kind !== "unavailable").length,
    };
    renderPages();
    renderResources();
    loadCacheMetrics();
  } catch (error) {
    renderError(resourcesList, error);
  }
}

function setViewMode(mode) {
  state.viewMode = mode;
  localStorage.setItem("onenote-view-mode", mode);
  viewPdfButton.classList.toggle("active", mode === "pdf");
  viewTextButton.classList.toggle("active", mode === "text");
  renderResources();
}

function setPdfSearchMode(enabled) {
  state.searchPdfContent = enabled;
  localStorage.setItem("onenote-search-pdf", enabled ? "1" : "0");
  searchPdfButton.classList.toggle("active", enabled);
  queryInput.placeholder = enabled
    ? "Search extracted PDF text in the selected section"
    : "Filter page titles in the selected section";
  handleQueryInput();
}

function renderResources() {
  const page = state.selectedPage;
  const resources = state.resources;
  viewPdfButton.classList.toggle("active", state.viewMode === "pdf");
  viewTextButton.classList.toggle("active", state.viewMode === "text");

  if (!page) {
    resourcesList.textContent = "Select a page to inspect its PDF/image resources.";
    return;
  }

  if (!resources.length) {
    resourcesList.textContent = "No embedded resources found on this page.";
    return;
  }

  const unavailable = resources.find((resource) => resource.kind === "unavailable");
  if (unavailable) {
    const diagnostics = (unavailable.diagnostics || [])
      .map((row) => `<div class="diagnostic-row"><strong>${escapeHtml(row.label)}:</strong> ${escapeHtml(row.value)}</div>`)
      .join("");
    const link = unavailable.oneNoteWebUrl
      ? `<div class="item-meta"><a href="${escapeHtml(unavailable.oneNoteWebUrl)}" target="_blank" rel="noreferrer">Open this page in OneNote Online</a></div>`
      : "";
    resourcesList.innerHTML = `
      <div class="item">
        <div class="item-title">Resource unavailable</div>
        <div class="item-meta">${escapeHtml(unavailable.message || "OneNote did not return resources for this page.")}</div>
        <div class="item-meta">${escapeHtml(unavailable.details || "Refresh Selected will retry the page-content lookup.")}</div>
        ${link}
        <div class="diagnostic-list">${diagnostics}</div>
      </div>
    `;
    return;
  }

  const pdfs = resources.filter((resource) => resource.kind === "application/pdf");
  const images = resources.filter((resource) => resource.kind === "image-fullres" || resource.kind.startsWith("image/"));

  resourcesList.innerHTML = "";
  const summary = document.createElement("div");
  summary.className = "resource-summary";
  summary.innerHTML = `
    <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
    <div class="item-meta">${pdfs.length} embedded PDF${pdfs.length === 1 ? "" : "s"} &middot; ${images.length} printout image${images.length === 1 ? "" : "s"}</div>
  `;
  resourcesList.append(summary);

  if (state.viewMode === "pdf") {
    renderPdfMode(pdfs, images);
  } else {
    renderTextMode(page, pdfs, images);
  }
}

function renderPdfMode(pdfs, images) {
  if (pdfs.length) {
    const pdf = pdfs[0];
    const card = document.createElement("div");
    card.className = "item";
    card.innerHTML = `
      <div class="item-title"><span class="resource-kind">&#9635; PDF</span> Embedded PDF</div>
      <div class="item-meta">Checking local cache...</div>
    `;
    resourcesList.append(card);
    loadPdfFrame(pdf, card);

    if (pdfs.length > 1) {
      const note = document.createElement("div");
      note.className = "item-meta";
      note.textContent = `${pdfs.length - 1} additional PDF resource(s) are available on this page.`;
      resourcesList.append(note);
    }
    return;
  }

  const card = document.createElement("div");
  card.className = "item";
  card.innerHTML = `
    <div class="item-title">No original PDF resource found</div>
    <div class="item-meta">${images.length ? "This page has printout images. OCR mode for images is a later step." : "No PDF or printout images were found."}</div>
  `;
  resourcesList.append(card);
}

async function loadPdfFrame(pdf, card) {
  try {
    const info = await api(`/api/resource-info?resource_url=${encodeURIComponent(pdf.url)}&kind=${encodeURIComponent(pdf.kind)}`);
    if (!info.available) {
      card.innerHTML = `
        <div class="item-title">PDF unavailable</div>
        <div class="item-meta">${escapeHtml(info.message || "OneNote no longer exposes this embedded PDF.")}</div>
      `;
      return;
    }

    card.innerHTML = `
      <div class="item-title"><span class="resource-kind">&#9635; PDF</span> Embedded PDF</div>
      <div class="item-meta">Cached locally &middot; ${Math.round((info.size || 0) / 1024).toLocaleString()} KB &middot; ${escapeHtml((info.sha256 || "").slice(0, 12))}</div>
    `;
    const iframe = document.createElement("iframe");
    iframe.className = "pdf-frame";
    iframe.title = "Embedded PDF";
    iframe.src = `/api/resource?resource_url=${encodeURIComponent(pdf.url)}&kind=${encodeURIComponent(pdf.kind)}`;
    card.append(iframe);
    loadCacheMetrics();
  } catch (error) {
    card.innerHTML = `
      <div class="item-title">PDF unavailable</div>
      <div class="item-meta">${escapeHtml(error.message)}</div>
    `;
  }
}

function renderTextMode(page, pdfs, images) {
  if (pdfs.length) {
    for (const pdf of pdfs) {
      const card = document.createElement("div");
      card.className = "item";
      card.innerHTML = `
        <div class="item-title"><span class="resource-kind">&#9671; text</span> Extracted PDF text</div>
        <div class="item-meta">Loaded from cache when available; otherwise extracted once from the embedded PDF.</div>
      `;
      resourcesList.append(card);
      loadPdfText(page, pdf, card);
    }
    return;
  }

  const card = document.createElement("div");
  card.className = "item";
  card.innerHTML = `
    <div class="item-title"><span class="resource-kind">&#9671; OCR</span> Printout text</div>
    <div class="item-meta">${images.length} printout image${images.length === 1 ? "" : "s"} found. Image OCR is not installed yet, so there is no text cache for these images.</div>
  `;
  resourcesList.append(card);
}

async function loadPdfText(page, resource, card) {
  const textBox = document.createElement("div");
  textBox.className = "pdf-text";
  textBox.textContent = "Loading extracted text...";
  card.append(textBox);

  try {
    const text = await api(`/api/pdf-text?page_id=${encodeURIComponent(page.id)}&resource_url=${encodeURIComponent(resource.url)}`);
    const previewPages = text.pages
      .filter((pdfPage) => pdfPage.text.trim())
      .map((pdfPage) => `PDF page ${pdfPage.page_number}\n${pdfPage.text.trim()}`)
      .join("\n\n---\n\n");

    textBox.textContent = previewPages || `PDF has ${text.page_count} pages, but no extractable text was found.`;
    loadCacheMetrics();
  } catch (error) {
    textBox.textContent = `PDF text extraction failed: ${error.message}`;
  }
}

function applyLayout(layout) {
  const current = layout || JSON.parse(localStorage.getItem("onenote-layout") || "null");
  if (!current) {
    return;
  }

  document.documentElement.style.setProperty("--left-col", `${current.left}fr`);
  document.documentElement.style.setProperty("--middle-col", `${current.middle}fr`);
  document.documentElement.style.setProperty("--right-col", `${current.right}fr`);
}

function resetLayout() {
  localStorage.removeItem("onenote-layout");
  localStorage.removeItem("onenote-collapsed-panels");
  state.collapsedPanels = {};
  document.documentElement.style.removeProperty("--left-col");
  document.documentElement.style.removeProperty("--middle-col");
  document.documentElement.style.removeProperty("--right-col");
  applyCollapsedPanels();
}

function readLayout() {
  const styles = getComputedStyle(document.documentElement);
  return {
    left: Number.parseFloat(styles.getPropertyValue("--left-col")) || 0.8,
    middle: Number.parseFloat(styles.getPropertyValue("--middle-col")) || 1.4,
    right: Number.parseFloat(styles.getPropertyValue("--right-col")) || 1,
  };
}

function saveLayout(layout) {
  localStorage.setItem("onenote-layout", JSON.stringify(layout));
  applyLayout(layout);
}

function setupSplitters() {
  for (const splitter of splitters) {
    splitter.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      if (
        (splitter.dataset.splitter === "left" && (state.collapsedPanels.left || state.collapsedPanels.middle)) ||
        (splitter.dataset.splitter === "right" && (state.collapsedPanels.middle || state.collapsedPanels.right))
      ) {
        return;
      }
      splitter.classList.add("active");
      splitter.setPointerCapture(event.pointerId);

      const startX = event.clientX;
      const start = readLayout();
      const gridWidth = grid.getBoundingClientRect().width;

      const move = (moveEvent) => {
        const delta = ((moveEvent.clientX - startX) / gridWidth) * 3.2;
        const next = { ...start };
        if (splitter.dataset.splitter === "left") {
          next.left = Math.max(0.45, start.left + delta);
          next.middle = Math.max(0.55, start.middle - delta);
        } else {
          next.middle = Math.max(0.55, start.middle + delta);
          next.right = Math.max(0.55, start.right - delta);
        }
        saveLayout(next);
      };

      const up = () => {
        splitter.classList.remove("active");
        splitter.removeEventListener("pointermove", move);
        splitter.removeEventListener("pointerup", up);
        splitter.removeEventListener("pointercancel", up);
      };

      splitter.addEventListener("pointermove", move);
      splitter.addEventListener("pointerup", up);
      splitter.addEventListener("pointercancel", up);
    });
  }
}

function setPanelCollapsed(panel, collapsed) {
  state.collapsedPanels[panel] = collapsed;
  localStorage.setItem("onenote-collapsed-panels", JSON.stringify(state.collapsedPanels));
  applyCollapsedPanels();
}

function applyCollapsedPanels() {
  for (const panel of panels) {
    const key = panel.dataset.panel;
    panel.classList.toggle("collapsed", Boolean(state.collapsedPanels[key]));
  }
  for (const key of ["left", "middle", "right"]) {
    document.documentElement.classList.toggle(`collapse-${key}`, Boolean(state.collapsedPanels[key]));
  }
}

async function loadCacheMetrics() {
  try {
    const metrics = await api("/api/cache-metrics");
    renderCacheMetrics(metrics);
  } catch (error) {
    cacheProgressLabel.textContent = "Cache: unavailable";
    cacheProgressCount.textContent = "";
    cacheProgress.title = error.message;
  }
}

function renderCacheMetrics(metrics) {
  const percent = Number(metrics.percent || 0);
  const cached = Number(metrics.pdf_blobs || 0);
  const total = Number(metrics.pdf_resources || 0);
  const remaining = Number(metrics.remaining_pdf_resources || 0);
  cacheProgressFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  cacheProgressLabel.textContent = `Cache: ${percent.toFixed(1)}%`;
  cacheProgressCount.textContent = `${cached}/${total} PDFs, ${formatBytes(metrics.bytes || 0)}`;
  cacheProgress.title = [
    `${cached} of ${total} discovered PDF resources are downloaded into the local cache.`,
    `${remaining} PDF resources remain based on currently discovered OneNote pages/resources.`,
    `Estimated remaining warm-cache time: about ${metrics.estimated_minutes_1_5s_throttle} minutes in moderate batches, or ${metrics.estimated_minutes_3s_throttle} minutes at a gentler throttle.`,
    metrics.scope_note || "Refresh metadata to improve the estimate for the full notebook.",
  ].join("\n");
}

function formatBytes(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let value = Number(bytes || 0);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

applyLayout();
applyCollapsedPanels();
setupSplitters();
setViewMode(state.viewMode);
setPdfSearchMode(state.searchPdfContent);
loadBasics();
