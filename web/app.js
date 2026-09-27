const savedViewModeVersion = localStorage.getItem("onenote-view-mode-version");
if (savedViewModeVersion !== "any-default-v1") {
  localStorage.setItem("onenote-view-mode", "any");
  localStorage.setItem("onenote-view-mode-version", "any-default-v1");
}

const state = {
  notebooks: [],
  sections: [],
  selectedNotebookId: localStorage.getItem("onenote-selected-notebook-id"),
  selectedSectionId: localStorage.getItem("onenote-selected-section-id"),
  selectedPageId: localStorage.getItem("onenote-selected-page-id"),
  selectedPage: null,
  pages: [],
  resources: [],
  viewMode: localStorage.getItem("onenote-view-mode") || "any",
  searchPdfContent: localStorage.getItem("onenote-search-pdf") === "1",
  showDates: localStorage.getItem("onenote-show-dates") !== "0",
  sectionSort: localStorage.getItem("onenote-section-sort") || "onenote",
  pageSort: localStorage.getItem("onenote-page-sort") || "onenote",
  cacheFilter: localStorage.getItem("onenote-cache-filter") || "all",
  showSectionColors: localStorage.getItem("onenote-section-colors") === "1",
  panelFontStep: Number.parseInt(localStorage.getItem("onenote-panel-font-step") || "0", 10),
  isRefreshingMetadata: false,
  lastMetadataRefresh: 0,
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
const viewAnyButton = document.querySelector("#viewAnyButton");
const viewPdfButton = document.querySelector("#viewPdfButton");
const viewTextButton = document.querySelector("#viewTextButton");
const viewPageButton = document.querySelector("#viewPageButton");
const searchPdfButton = document.querySelector("#searchPdfButton");
const sectionSortSelect = document.querySelector("#sectionSortSelect");
const pageSortSelect = document.querySelector("#pageSortSelect");
const cacheFilterSelect = document.querySelector("#cacheFilterSelect");
const fontSmallerButton = document.querySelector("#fontSmallerButton");
const fontLargerButton = document.querySelector("#fontLargerButton");
const sectionColorsButton = document.querySelector("#sectionColorsButton");
const toggleDatesButton = document.querySelector("#toggleDatesButton");
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

viewAnyButton.addEventListener("click", () => {
  setViewMode("any");
});

viewPdfButton.addEventListener("click", () => {
  setViewMode("pdf");
});

viewTextButton.addEventListener("click", () => {
  setViewMode("text");
});

viewPageButton.addEventListener("click", () => {
  setViewMode("page");
});

searchPdfButton.addEventListener("click", () => {
  setPdfSearchMode(!state.searchPdfContent);
});

sectionSortSelect.addEventListener("change", () => {
  state.sectionSort = sectionSortSelect.value;
  localStorage.setItem("onenote-section-sort", state.sectionSort);
  renderSections();
});

pageSortSelect.addEventListener("change", () => {
  state.pageSort = pageSortSelect.value;
  localStorage.setItem("onenote-page-sort", state.pageSort);
  renderPages();
});

cacheFilterSelect.addEventListener("change", () => {
  state.cacheFilter = cacheFilterSelect.value;
  localStorage.setItem("onenote-cache-filter", state.cacheFilter);
  renderSections();
  renderPages();
});

fontSmallerButton.addEventListener("click", () => {
  setPanelFontStep(state.panelFontStep - 1);
});

fontLargerButton.addEventListener("click", () => {
  setPanelFontStep(state.panelFontStep + 1);
});

sectionColorsButton.addEventListener("click", () => {
  setSectionColors(!state.showSectionColors);
});

toggleDatesButton.addEventListener("click", () => {
  setShowDates(!state.showDates);
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
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    setPanelCollapsed(button.dataset.collapsePanel, true);
  });
});

document.querySelectorAll("[data-expand-panel]").forEach((button) => {
  button.addEventListener("click", () => setPanelCollapsed(button.dataset.expandPanel, false));
});

document.querySelectorAll("[data-toggle-panel]").forEach((bar) => {
  const toggle = () => setPanelCollapsed(bar.dataset.togglePanel, !state.collapsedPanels[bar.dataset.togglePanel]);
  bar.addEventListener("click", (event) => {
    if (event.target.closest("button")) {
      return;
    }
    toggle();
  });
  bar.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggle();
    }
  });
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

function orderedNotebooks(notebooks = state.notebooks) {
  return [...notebooks].sort((left, right) => {
    const leftIsPrimary = (left.displayName || "").toLowerCase() === "samira";
    const rightIsPrimary = (right.displayName || "").toLowerCase() === "samira";
    if (leftIsPrimary !== rightIsPrimary) {
      return leftIsPrimary ? -1 : 1;
    }
    return (left.displayName || "").localeCompare(right.displayName || "");
  });
}

function primaryNotebook() {
  return orderedNotebooks()[0];
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
    state.notebooks = await api(`/api/notebooks${refreshParam}`);
    if (!state.selectedNotebookId && state.notebooks.length) {
      const primary = primaryNotebook();
      state.selectedNotebookId = primary.id;
      localStorage.setItem("onenote-selected-notebook-id", primary.id);
    }
    renderNotebooks();
  } catch (error) {
    renderError(notebooksList, error);
  }

  try {
    state.sections = await api(`/api/sections${refreshParam}`);
    if (refresh) {
      state.lastMetadataRefresh = Date.now();
    }
    renderNotebooks();
    renderSections();

    const selectedStillExists = filteredSections().some((section) => section.id === state.selectedSectionId);
    if (!selectedStillExists) {
      selectFirstSectionWithPages({ refresh });
    } else if (state.selectedSectionId) {
      selectSection(state.selectedSectionId, { refresh });
    }
  } catch (error) {
    renderError(sectionsList, error);
  }

  loadCacheMetrics();
  if (!refresh) {
    window.setTimeout(() => refreshMetadata({ quiet: true }), 1200);
  }
}

async function selectFirstSectionWithPages({ refresh = false } = {}) {
  for (const section of filteredSections()) {
    await selectSection(section.id, { refresh });
    if (state.pages.length) {
      return;
    }
  }
}

function reconcileSelectionAfterMetadataRefresh() {
  const selectedNotebookExists = state.notebooks.some((notebook) => notebook.id === state.selectedNotebookId);
  if (!state.selectedNotebookId || !selectedNotebookExists) {
    const primary = primaryNotebook();
    state.selectedNotebookId = primary?.id || null;
    if (state.selectedNotebookId) {
      localStorage.setItem("onenote-selected-notebook-id", state.selectedNotebookId);
    } else {
      localStorage.removeItem("onenote-selected-notebook-id");
    }
  }

  const selectedSectionExists = filteredSections().some((section) => section.id === state.selectedSectionId);
  if (state.selectedSectionId && !selectedSectionExists) {
    state.selectedSectionId = null;
    state.selectedPageId = null;
    state.selectedPage = null;
    state.pages = [];
    state.resources = [];
    localStorage.removeItem("onenote-selected-section-id");
    localStorage.removeItem("onenote-selected-page-id");
    pagesList.textContent = "Select a section to load its pages.";
    resourcesList.textContent = "Select a page to inspect its PDF/image resources.";
  }
}

async function refreshMetadata({ force = true, quiet = true } = {}) {
  if (state.isRefreshingMetadata) {
    return;
  }

  state.isRefreshingMetadata = true;
  const previousStatus = accountStatus.textContent;
  if (!quiet) {
    accountStatus.textContent = "Refreshing OneNote notebook metadata...";
  }

  const refreshParam = force ? "?refresh=1" : "";
  try {
    const [notebooks, sections] = await Promise.all([
      api(`/api/notebooks${refreshParam}`),
      api(`/api/sections${refreshParam}`),
    ]);
    state.notebooks = notebooks;
    state.sections = sections;
    state.lastMetadataRefresh = Date.now();
    reconcileSelectionAfterMetadataRefresh();
    renderNotebooks();
    renderSections();

    if (!state.selectedSectionId) {
      selectFirstSectionWithPages();
    } else {
      const currentSectionIsVisible = filteredSections().some((section) => section.id === state.selectedSectionId);
      if (currentSectionIsVisible && !state.pages.length) {
        selectSection(state.selectedSectionId);
      }
    }

    if (!quiet) {
      accountStatus.textContent = "Notebook metadata refreshed.";
      window.setTimeout(() => {
        if (accountStatus.textContent === "Notebook metadata refreshed.") {
          accountStatus.textContent = previousStatus;
        }
      }, 1600);
    }
  } catch (error) {
    if (!quiet) {
      accountStatus.innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
    }
  } finally {
    state.isRefreshingMetadata = false;
  }
}

function maybeRefreshMetadataOnFocus() {
  if (document.visibilityState !== "visible") {
    return;
  }
  if (Date.now() - state.lastMetadataRefresh > 30000) {
    refreshMetadata({ quiet: true });
  }
}

function renderNotebooks() {
  if (!state.notebooks.length) {
    notebooksList.textContent = "No notebooks found.";
    return;
  }

  notebooksList.innerHTML = "";
  for (const notebook of orderedNotebooks()) {
    const sectionCount = state.sections.filter((section) => section.parentNotebook?.id === notebook.id).length;
    const button = document.createElement("button");
    button.className = `item${notebook.id === state.selectedNotebookId ? " active" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <div class="item-title">${escapeHtml(notebook.displayName || "Untitled notebook")}</div>
      <div class="item-meta"><span>${sectionCount} section${sectionCount === 1 ? "" : "s"}</span><span class="date-meta"> &middot; ${escapeHtml(notebook.lastModifiedDateTime || notebook.id)}</span></div>
    `;
    button.addEventListener("click", () => selectNotebook(notebook.id));
    notebooksList.append(button);
  }
}

function selectNotebook(notebookId) {
  state.selectedNotebookId = notebookId;
  localStorage.setItem("onenote-selected-notebook-id", notebookId);
  state.selectedSectionId = null;
  state.selectedPageId = null;
  state.selectedPage = null;
  state.pages = [];
  state.resources = [];
  localStorage.removeItem("onenote-selected-section-id");
  localStorage.removeItem("onenote-selected-page-id");
  pagesList.textContent = "Select a section to load its pages.";
  resourcesList.textContent = "Select a page to inspect its PDF/image resources.";
  renderNotebooks();
  renderSections();
  selectFirstSectionWithPages();
}

function filteredSections() {
  let sections;
  if (!state.selectedNotebookId) {
    sections = state.sections;
  } else {
    sections = state.sections.filter((section) => section.parentNotebook?.id === state.selectedNotebookId);
  }
  return sortSections(sections);
}

function sortSections(sections) {
  const indexed = sections.map((section, index) => ({ section, index }));
  indexed.sort((left, right) => {
    switch (state.sectionSort) {
      case "title":
        return compareText(left.section.displayName, right.section.displayName) || left.index - right.index;
      case "modified-desc":
        return compareDate(right.section.lastModifiedDateTime, left.section.lastModifiedDateTime) || left.index - right.index;
      case "modified-asc":
        return compareDate(left.section.lastModifiedDateTime, right.section.lastModifiedDateTime) || left.index - right.index;
      default:
        return left.index - right.index;
    }
  });
  return indexed.map((row) => row.section);
}

function renderSections() {
  const sections = filteredSections();
  if (!sections.length) {
    sectionsList.textContent = "No sections found.";
    return;
  }

  sectionsList.innerHTML = "";
  for (const section of sections) {
    const button = document.createElement("button");
    const cacheInfo = section._cache || {};
    button.className = `item section-item${state.showSectionColors ? " colored" : ""}${section.id === state.selectedSectionId ? " active" : ""}`;
    button.type = "button";
    button.style.setProperty("--section-color", sectionColor(section));
    const cacheLabel = sectionCacheLabel(cacheInfo);
    button.innerHTML = `
      <div class="section-item-main">
        <div class="item-title">${escapeHtml(section.displayName || "Untitled section")}</div>
        <div class="item-meta"><span class="date-meta">${escapeHtml(section.lastModifiedDateTime || section.id)}</span></div>
      </div>
      ${cacheLabel}
    `;
    button.addEventListener("click", () => {
      state.selectedPageId = null;
      localStorage.removeItem("onenote-selected-page-id");
      selectSection(section.id);
    });
    sectionsList.append(button);
  }
}

function sectionCacheLabel(cacheInfo) {
  if (state.cacheFilter === "cached-pages") {
    const count = Number(cacheInfo.native_page_count || 0);
    return count
      ? `<span class="section-cache-label" title="${count.toLocaleString()} cached native OneNote page${count === 1 ? "" : "s"} in this section">page ${count.toLocaleString()}</span>`
      : "";
  }
  if (state.cacheFilter === "cached-pdfs") {
    const count = Number(cacheInfo.pdf_page_count || 0);
    return count
      ? `<span class="section-cache-label" title="${count.toLocaleString()} page${count === 1 ? "" : "s"} with downloaded cached PDFs in this section">PDF ${count.toLocaleString()}</span>`
      : "";
  }
  const count = Number(cacheInfo.resource_page_count || 0);
  return count
    ? `<span class="section-cache-label subtle" title="${count.toLocaleString()} page${count === 1 ? "" : "s"} with cached resource metadata in this section">${count.toLocaleString()}</span>`
    : "";
}

function sectionColor(section) {
  const palette = ["#0b7a75", "#9b5de5", "#d97706", "#2563eb", "#c2410c", "#16835f", "#be185d", "#4f46e5", "#64748b"];
  const value = section.id || section.displayName || "";
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return palette[hash % palette.length];
}

async function selectSection(sectionId, { refresh = false } = {}) {
  state.selectedSectionId = sectionId;
  localStorage.setItem("onenote-selected-section-id", sectionId);
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
    const restoredPage = state.selectedPageId
      ? state.pages.find((page) => page.id === state.selectedPageId)
      : null;
    if (restoredPage) {
      loadResources(restoredPage);
    }
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
  updatePagesHeader();
  if (state.searchPdfContent && query.length >= 2) {
    renderPdfSearchResults();
    return;
  }

  const pages = sortPages(state.pages.filter((page) => {
    const section = page._section?.displayName || "";
    const title = page.title || "";
    return `${section} ${title}`.toLowerCase().includes(query) && pageMatchesCacheFilter(page);
  }));

  if (!pages.length) {
    pagesList.textContent = state.pages.length ? "No pages match this filter." : "No pages found in this section.";
    return;
  }

  pagesList.innerHTML = "";
  for (const page of pages) {
    const button = document.createElement("button");
    const cacheInfo = page._cache || {};
    const resourceCount = cacheInfo.resource_count || 0;
    const pdfCount = cacheInfo.pdf_count || 0;
    const pdfBlobCount = cacheInfo.pdf_blob_count || 0;
    const pagePreviewCached = pdfCount === 0 && hasCachedPagePreview(cacheInfo);
    button.className = `item page-item${page.id === state.selectedPage?.id ? " active" : ""}`;
    button.type = "button";
    const cacheMark = pdfCount
      ? `<span class="cache-mark" title="Embedded PDF/resource metadata cached locally: ${pdfBlobCount}/${pdfCount} PDF${pdfCount === 1 ? "" : "s"} downloaded, ${resourceCount} total resource${resourceCount === 1 ? "" : "s"}">&#9670;</span>`
      : pagePreviewCached
        ? `<span class="page-mark" title="Native OneNote page preview cached locally">&#9638;</span>`
      : "";
    button.innerHTML = `
      <div class="page-item-main">
        <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
        <div class="item-meta"><span class="date-meta">${escapeHtml(page.lastModifiedDateTime || page.id)}</span></div>
      </div>
      ${cacheMark}
    `;
    button.addEventListener("click", () => loadResources(page));
    pagesList.append(button);
  }
}

function pageMatchesCacheFilter(page) {
  const cacheInfo = page._cache || {};
  if (state.cacheFilter === "cached-pdfs") {
    return Number(cacheInfo.pdf_blob_count || 0) > 0;
  }
  if (state.cacheFilter === "cached-pages") {
    return Number(cacheInfo.pdf_count || 0) === 0 && hasCachedPagePreview(cacheInfo);
  }
  return true;
}

function hasCachedPagePreview(cacheInfo) {
  return Boolean(
    cacheInfo.page_preview ||
    cacheInfo.native_hint ||
    (Number(cacheInfo.resource_count || 0) > 0 && Number(cacheInfo.pdf_count || 0) === 0),
  );
}

function sortPages(pages) {
  const indexed = pages.map((page, index) => ({ page, index }));
  indexed.sort((left, right) => {
    switch (state.pageSort) {
      case "title":
        return compareText(left.page.title, right.page.title) || left.index - right.index;
      case "modified-desc":
        return compareDate(right.page.lastModifiedDateTime, left.page.lastModifiedDateTime) || left.index - right.index;
      case "modified-asc":
        return compareDate(left.page.lastModifiedDateTime, right.page.lastModifiedDateTime) || left.index - right.index;
      case "created-desc":
        return compareDate(right.page.createdDateTime, left.page.createdDateTime) || left.index - right.index;
      case "created-asc":
        return compareDate(left.page.createdDateTime, right.page.createdDateTime) || left.index - right.index;
      case "pdf-first":
        return comparePdfCache(right.page, left.page) || left.index - right.index;
      default:
        return left.index - right.index;
    }
  });
  return indexed.map((row) => row.page);
}

function compareText(left, right) {
  return String(left || "").localeCompare(String(right || ""), undefined, { sensitivity: "base", numeric: true });
}

function compareDate(left, right) {
  const leftTime = Date.parse(left || "");
  const rightTime = Date.parse(right || "");
  return (Number.isFinite(leftTime) ? leftTime : 0) - (Number.isFinite(rightTime) ? rightTime : 0);
}

function comparePdfCache(left, right) {
  const leftPdf = Number(left._cache?.pdf_count || 0);
  const rightPdf = Number(right._cache?.pdf_count || 0);
  const leftResources = Number(left._cache?.resource_count || 0);
  const rightResources = Number(right._cache?.resource_count || 0);
  return leftPdf - rightPdf || leftResources - rightResources;
}

function updatePagesHeader() {
  const heading = document.querySelector('[data-panel="middle"] h2');
  if (!heading) {
    return;
  }
  const count = state.pages.length;
  heading.innerHTML = `Pages <span class="list-count">${count.toLocaleString()}</span>`;
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
    button.className = `item page-item search-hit${page.id === state.selectedPage?.id ? " active" : ""}`;
    button.type = "button";
    button.innerHTML = `
      <div class="page-item-main">
        <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
        <div class="item-meta">PDF page ${escapeHtml(result.pdf_page_number || "?")}<span class="date-meta"> &middot; ${escapeHtml(page.lastModifiedDateTime || result.page_id)}</span></div>
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
  state.selectedPageId = page.id;
  localStorage.setItem("onenote-selected-page-id", page.id);
  state.resources = [];
  resourcesList.textContent = `Inspecting ${page.title || "page"}...`;

  const params = new URLSearchParams({ page_id: page.id });
  if (refresh) {
    params.set("refresh", "1");
  }

  try {
    state.resources = await api(`/api/resources?${params}`);
    const availableResources = state.resources.filter((resource) => resource.kind !== "unavailable");
    const pdfCount = state.resources.filter(isPdfResource).length;
    const imageCount = state.resources.filter(isImageResource).length;
    const previousPagePreview = hasCachedPagePreview(page._cache || {});
    page._cache = {
      ...(page._cache || {}),
      resource_count: availableResources.length,
      pdf_count: pdfCount,
      pdf_blob_count: page._cache?.pdf_blob_count || 0,
      image_count: imageCount,
      page_preview: Boolean(previousPagePreview && !pdfCount),
      native_hint: Boolean(!pdfCount && (availableResources.length || previousPagePreview)),
    };
    renderPages();
    renderResources();
    loadCacheMetrics();
  } catch (error) {
    renderError(resourcesList, error);
  }
}

function setViewMode(mode) {
  if (!["any", "pdf", "text", "page"].includes(mode)) {
    mode = "any";
  }
  state.viewMode = mode;
  localStorage.setItem("onenote-view-mode", mode);
  localStorage.setItem("onenote-view-mode-version", "any-default-v1");
  viewAnyButton.classList.toggle("active", mode === "any");
  viewPdfButton.classList.toggle("active", mode === "pdf");
  viewTextButton.classList.toggle("active", mode === "text");
  viewPageButton.classList.toggle("active", mode === "page");
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
  viewAnyButton.classList.toggle("active", state.viewMode === "any");
  viewPdfButton.classList.toggle("active", state.viewMode === "pdf");
  viewTextButton.classList.toggle("active", state.viewMode === "text");
  viewPageButton.classList.toggle("active", state.viewMode === "page");

  if (!page) {
    resourcesList.textContent = "Select a page to inspect its PDF/image resources.";
    return;
  }

  if (!resources.length && !["any", "page"].includes(state.viewMode)) {
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

  const pdfs = resources.filter(isPdfResource);
  const images = resources.filter(isImageResource);

  resourcesList.innerHTML = "";
  const summary = document.createElement("div");
  summary.className = "resource-summary";
  summary.innerHTML = `
    <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
    <div class="item-meta">${pdfs.length} embedded PDF${pdfs.length === 1 ? "" : "s"} &middot; ${images.length} printout image${images.length === 1 ? "" : "s"}</div>
  `;
  resourcesList.append(summary);

  if (state.viewMode === "any") {
    if (pdfs.length) {
      renderPdfMode(pdfs, images);
    } else {
      renderPageMode(page, resources, pdfs, images);
    }
  } else if (state.viewMode === "pdf") {
    renderPdfMode(pdfs, images);
  } else if (state.viewMode === "text") {
    renderTextMode(page, pdfs, images);
  } else {
    renderPageMode(page, resources, pdfs, images);
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

function renderPageMode(page, resources, pdfs, images) {
  if (pdfs.length) {
    const card = document.createElement("div");
    card.className = "item page-pdf-card";
    card.innerHTML = `
      <div class="item-title"><span class="resource-kind">&#9635; PDF</span> Native PDF page view</div>
      <div class="item-meta">Using the embedded PDF directly for antialiasing and selectable text. OneNote printout images are skipped in this mode.</div>
    `;
    resourcesList.append(card);
    loadPdfFrame(pdfs[0], card, { pageMode: true });
    return;
  }

  const card = document.createElement("div");
  card.className = "item";
  card.innerHTML = `
    <div class="item-title"><span class="resource-kind">&#9638; page</span> OneNote page preview</div>
    <div class="item-meta">Rendering native OneNote HTML with cached resources when available.</div>
  `;
  resourcesList.append(card);
  loadOneNotePageFrame(page, card, { pdfs, images, resources });
}

async function loadOneNotePageFrame(page, card, summary) {
  const frame = document.createElement("iframe");
  frame.className = "onenote-html-frame";
  frame.title = "OneNote page preview";
  frame.sandbox = "allow-same-origin allow-popups";
  card.append(frame);

  try {
    const payload = await api(`/api/page-html?page_id=${encodeURIComponent(page.id)}`);
    const resources = payload.resources || summary.resources || [];
    const pdfs = resources.filter(isPdfResource);
    const images = resources.filter(isImageResource);
    frame.srcdoc = buildOneNotePreviewDocument(page, payload.html || "", {
      pdfCount: pdfs.length,
      imageCount: images.length,
      resourceCount: resources.length,
    });
    page._cache = {
      ...(page._cache || {}),
      ...(payload.cache || {}),
      resource_count: resources.length,
      pdf_count: pdfs.length,
      pdf_blob_count: payload.cache?.pdf_blob_count || page._cache?.pdf_blob_count || 0,
      image_count: images.length,
      page_preview: true,
      native_hint: Boolean(!pdfs.length),
    };
    renderPages();
    loadCacheMetrics();
  } catch (error) {
    frame.remove();
    card.insertAdjacentHTML(
      "beforeend",
      `<div class="error">OneNote page preview failed: ${escapeHtml(error.message)}</div>`,
    );
  }
}

function buildOneNotePreviewDocument(page, html, counts) {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<base target="_blank">
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background:
      linear-gradient(90deg, rgba(18, 103, 196, 0.045) 1px, transparent 1px),
      linear-gradient(rgba(24, 32, 42, 0.035) 1px, transparent 1px),
      #fffdf7;
    background-size: 34px 34px;
    color: #18202a;
    font: 14px/1.45 "Segoe UI", system-ui, sans-serif;
  }
  .page-shell {
    min-height: 100vh;
    overflow: auto;
    padding: 24px;
  }
  .page-meta {
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid #d8dee8;
    border-radius: 6px;
    color: #667085;
    margin: 0 0 18px;
    padding: 10px 12px;
  }
  .page-meta strong { color: #18202a; }
  .onenote-body {
    background: rgba(255, 255, 255, 0.74);
    border: 1px solid rgba(216, 222, 232, 0.82);
    border-radius: 6px;
    min-height: 480px;
    overflow: auto;
    overflow-wrap: anywhere;
    padding: 18px;
    position: relative;
    white-space: normal;
    word-break: normal;
  }
  .onenote-body [style*="position:absolute"],
  .onenote-body [style*="position: absolute"] {
    max-width: calc(100% - 24px) !important;
  }
  .onenote-reflowed-box {
    display: block;
    margin: 0 0 14px;
    max-width: min(100%, 960px) !important;
    position: static !important;
  }
  .onenote-body table {
    border-collapse: collapse;
    max-width: 100%;
    table-layout: auto;
  }
  .onenote-body td,
  .onenote-body th {
    max-width: 100%;
    vertical-align: top;
  }
  .onenote-body img {
    background: #ffffff;
  }
  .onenote-body img.onenote-inline-image {
    display: block;
    height: auto !important;
    margin: 10px auto 26px;
    max-width: 100% !important;
    object-fit: contain;
  }
  .onenote-body img.onenote-abs-image {
    display: block;
    margin: 0 !important;
    max-width: none !important;
  }
  .onenote-body td > img.onenote-inline-image,
  .onenote-body th > img.onenote-inline-image {
    margin: 8px auto;
    width: auto !important;
  }
  .onenote-body p,
  .onenote-body div {
    max-width: 100%;
  }
  .onenote-body p {
    clear: both;
    line-height: 1.35;
    margin-block: 0.28em;
    overflow-wrap: anywhere;
  }
  .onenote-body span {
    line-height: inherit;
  }
  .embedded-object {
    align-items: center;
    background: #f7f9fc;
    border: 1px solid #d8dee8;
    border-radius: 6px;
    display: flex;
    gap: 10px;
    margin: 10px 0 18px;
    padding: 10px 12px;
  }
  .onenote-page-spacer {
    pointer-events: none;
    width: 1px;
  }
  a { color: #1267c4; }
</style>
</head>
<body>
  <div class="page-shell">
    <div class="page-meta"><strong>${escapeHtml(page.title || "Untitled page")}</strong><br>${counts.pdfCount} embedded PDF${counts.pdfCount === 1 ? "" : "s"} &middot; ${counts.imageCount} image resource${counts.imageCount === 1 ? "" : "s"} &middot; ${counts.resourceCount} total resource${counts.resourceCount === 1 ? "" : "s"}</div>
    <div class="onenote-body">${html}</div>
  </div>
</body>
</html>`;
}

function isPdfResource(resource) {
  const kind = String(resource?.kind || "").toLowerCase();
  const url = String(resource?.url || "").toLowerCase();
  return kind === "application/pdf" || kind.includes("application/pdf") || url.includes(".pdf");
}

function isImageResource(resource) {
  const kind = String(resource?.kind || "").toLowerCase();
  return kind === "image-fullres" || kind.startsWith("image/");
}

async function loadPdfFrame(pdf, card, options = {}) {
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
      <div class="item-title"><span class="resource-kind">&#9635; PDF</span> ${options.pageMode ? "Native PDF page view" : "Embedded PDF"}</div>
      <div class="item-meta">Cached locally &middot; ${Math.round((info.size || 0) / 1024).toLocaleString()} KB &middot; ${escapeHtml((info.sha256 || "").slice(0, 12))}</div>
    `;
    const iframe = document.createElement("iframe");
    iframe.className = options.pageMode ? "pdf-frame page-pdf-frame" : "pdf-frame";
    iframe.title = "Embedded PDF";
    iframe.src = `/api/resource?resource_url=${encodeURIComponent(pdf.url)}&kind=${encodeURIComponent(pdf.kind)}#view=FitH&zoom=page-width`;
    card.append(iframe);
    if (state.selectedPage) {
      state.selectedPage._cache = {
        ...(state.selectedPage._cache || {}),
        pdf_blob_count: Math.max(1, Number(state.selectedPage._cache?.pdf_blob_count || 0)),
      };
      renderPages();
    }
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
  localStorage.removeItem("onenote-panel-font-step");
  state.collapsedPanels = {};
  state.panelFontStep = 0;
  document.documentElement.style.removeProperty("--left-col");
  document.documentElement.style.removeProperty("--middle-col");
  document.documentElement.style.removeProperty("--right-col");
  applyCollapsedPanels();
  applyPanelDisplaySettings();
}

function setPanelFontStep(step) {
  state.panelFontStep = Math.max(-3, Math.min(4, step));
  localStorage.setItem("onenote-panel-font-step", String(state.panelFontStep));
  applyPanelDisplaySettings();
}

function setShowDates(show) {
  state.showDates = show;
  localStorage.setItem("onenote-show-dates", show ? "1" : "0");
  applyPanelDisplaySettings();
}

function setSectionColors(show) {
  state.showSectionColors = show;
  localStorage.setItem("onenote-section-colors", show ? "1" : "0");
  sectionColorsButton.classList.toggle("active", show);
  sectionColorsButton.textContent = show ? "Section Colors On" : "Section Colors";
  renderSections();
}

function applyPanelDisplaySettings() {
  const base = 14 + state.panelFontStep;
  const meta = Math.max(10, base - 2);
  document.documentElement.style.setProperty("--panel-font-size", `${base}px`);
  document.documentElement.style.setProperty("--panel-meta-size", `${meta}px`);
  document.body.classList.toggle("hide-dates", !state.showDates);
  toggleDatesButton.classList.toggle("active", state.showDates);
  toggleDatesButton.textContent = state.showDates ? "Dates On" : "Dates Off";
  sectionColorsButton.classList.toggle("active", state.showSectionColors);
  sectionColorsButton.textContent = state.showSectionColors ? "Section Colors On" : "Section Colors";
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
  cacheProgressLabel.textContent = `Discovered PDF cache: ${percent.toFixed(1)}%`;
  cacheProgressCount.textContent = `${cached}/${total} PDFs, ${formatBytes(metrics.bytes || 0)} cached`;
  cacheProgress.title = [
    `${cached} of ${total} discovered original PDF resources are downloaded into the local cache.`,
    `${remaining} PDF resources remain based on currently discovered OneNote page/resource metadata.`,
    `${metrics.pages || 0} OneNote pages and ${metrics.resources || 0} embedded resources are currently known locally.`,
    `Estimated remaining warm-cache time: about ${metrics.estimated_minutes_1_5s_throttle} minutes in moderate batches, or ${metrics.estimated_minutes_3s_throttle} minutes at a gentler throttle.`,
    metrics.scope_note || "This is a discovered-resource metric, not a full OneDrive storage audit.",
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
applyPanelDisplaySettings();
sectionSortSelect.value = state.sectionSort;
pageSortSelect.value = state.pageSort;
cacheFilterSelect.value = state.cacheFilter;
setupSplitters();
setViewMode(state.viewMode);
setPdfSearchMode(state.searchPdfContent);
loadBasics();
window.addEventListener("focus", maybeRefreshMetadataOnFocus);
document.addEventListener("visibilitychange", maybeRefreshMetadataOnFocus);
window.setInterval(() => refreshMetadata({ quiet: true }), 120000);
