const state = {
  sections: [],
  selectedSectionId: null,
  selectedPage: null,
  pages: [],
  resources: [],
  viewMode: localStorage.getItem("onenote-view-mode") || "pdf",
};

const accountStatus = document.querySelector("#accountStatus");
const notebooksList = document.querySelector("#notebooksList");
const sectionsList = document.querySelector("#sectionsList");
const pagesList = document.querySelector("#pagesList");
const resourcesList = document.querySelector("#resourcesList");
const queryInput = document.querySelector("#queryInput");
const viewPdfButton = document.querySelector("#viewPdfButton");
const viewTextButton = document.querySelector("#viewTextButton");
const refreshSelectedButton = document.querySelector("#refreshSelectedButton");

document.querySelector("#refreshButton").addEventListener("click", () => {
  loadBasics({ refresh: true });
});

queryInput.addEventListener("input", () => {
  renderPages();
});

viewPdfButton.addEventListener("click", () => {
  setViewMode("pdf");
});

viewTextButton.addEventListener("click", () => {
  setViewMode("text");
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
    renderPages();
  } catch (error) {
    renderError(pagesList, error);
  }
}

function renderPages() {
  const query = queryInput.value.trim().toLowerCase();
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
    button.className = "item";
    button.type = "button";
    button.innerHTML = `
      <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
      <div class="item-meta">${escapeHtml(page.lastModifiedDateTime || page.id)}</div>
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
    renderResources();
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

  const pdfs = resources.filter((resource) => resource.kind === "application/pdf");
  const images = resources.filter((resource) => resource.kind === "image-fullres" || resource.kind.startsWith("image/"));

  resourcesList.innerHTML = "";
  const summary = document.createElement("div");
  summary.className = "resource-summary";
  summary.innerHTML = `
    <div class="item-title">${escapeHtml(page.title || "Untitled page")}</div>
    <div class="item-meta">${pdfs.length} embedded PDF${pdfs.length === 1 ? "" : "s"} · ${images.length} printout image${images.length === 1 ? "" : "s"}</div>
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
    const iframe = document.createElement("iframe");
    iframe.className = "pdf-frame";
    iframe.title = "Embedded PDF";
    iframe.src = `/api/resource?resource_url=${encodeURIComponent(pdf.url)}&kind=${encodeURIComponent(pdf.kind)}`;
    resourcesList.append(iframe);

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

function renderTextMode(page, pdfs, images) {
  if (pdfs.length) {
    for (const pdf of pdfs) {
      const card = document.createElement("div");
      card.className = "item";
      card.innerHTML = `
        <div class="item-title"><span class="resource-kind">◇ text</span> Extracted PDF text</div>
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
    <div class="item-title"><span class="resource-kind">◇ OCR</span> Printout text</div>
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
  } catch (error) {
    textBox.textContent = `PDF text extraction failed: ${error.message}`;
  }
}

setViewMode(state.viewMode);
loadBasics();
