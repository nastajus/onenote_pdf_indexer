const params = new URLSearchParams(window.location.search);
const resourceUrl = params.get("resource_url") || "";
const initialPage = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
const query = params.get("q") || "";
const title = params.get("title") || "PDF Match Viewer";

const viewerTitle = document.querySelector("#viewerTitle");
const viewerStatus = document.querySelector("#viewerStatus");
const pageHost = document.querySelector("#pageHost");
const pageFrame = document.querySelector("#pageFrame");
const canvas = document.querySelector("#pdfCanvas");
const textLayer = document.querySelector("#textLayer");
const highlightLayer = document.querySelector("#highlightLayer");
const pageInput = document.querySelector("#pageInput");
const pageTotal = document.querySelector("#pageTotal");
const zoomLabel = document.querySelector("#zoomLabel");
const prevPageButton = document.querySelector("#prevPageButton");
const nextPageButton = document.querySelector("#nextPageButton");
const zoomOutButton = document.querySelector("#zoomOutButton");
const zoomInButton = document.querySelector("#zoomInButton");
const fitWidthButton = document.querySelector("#fitWidthButton");
const prevMatchButton = document.querySelector("#prevMatchButton");
const nextMatchButton = document.querySelector("#nextMatchButton");

const state = {
  pdf: null,
  pageNumber: initialPage,
  scale: 1,
  fitWidth: true,
  renderToken: 0,
  highlights: [],
  activeHighlight: 0,
};

viewerTitle.textContent = title;
pageInput.value = String(initialPage);

prevPageButton.addEventListener("click", () => setPage(state.pageNumber - 1));
nextPageButton.addEventListener("click", () => setPage(state.pageNumber + 1));
pageInput.addEventListener("change", () => setPage(Number.parseInt(pageInput.value || "1", 10)));
zoomOutButton.addEventListener("click", () => setZoom(state.scale / 1.15));
zoomInButton.addEventListener("click", () => setZoom(state.scale * 1.15));
fitWidthButton.addEventListener("click", () => {
  state.fitWidth = true;
  renderPage();
});
prevMatchButton.addEventListener("click", () => activateHighlight(state.activeHighlight - 1));
nextMatchButton.addEventListener("click", () => activateHighlight(state.activeHighlight + 1));
window.addEventListener("resize", () => {
  if (state.fitWidth) {
    window.clearTimeout(state.resizeTimer);
    state.resizeTimer = window.setTimeout(() => renderPage(), 120);
  }
});

loadPdf();

async function loadPdf() {
  if (!resourceUrl) {
    showError("Missing PDF resource URL.");
    return;
  }
  if (!window.pdfjsLib) {
    showError("PDF.js did not load. Check the internet connection for the PDF.js CDN.");
    return;
  }

  pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  const pdfUrl = `/api/resource?resource_url=${encodeURIComponent(resourceUrl)}&kind=application%2Fpdf`;
  try {
    viewerStatus.textContent = "Loading PDF...";
    state.pdf = await pdfjsLib.getDocument(pdfUrl).promise;
    state.pageNumber = Math.min(Math.max(1, initialPage), state.pdf.numPages);
    pageTotal.textContent = `/ ${state.pdf.numPages.toLocaleString()}`;
    pageInput.max = String(state.pdf.numPages);
    pageInput.value = String(state.pageNumber);
    await renderPage();
  } catch (error) {
    showError(`PDF load failed: ${error.message}`);
  }
}

async function setPage(pageNumber) {
  if (!state.pdf) {
    return;
  }
  state.pageNumber = Math.min(Math.max(1, pageNumber || 1), state.pdf.numPages);
  pageInput.value = String(state.pageNumber);
  await renderPage();
}

function setZoom(scale) {
  state.fitWidth = false;
  state.scale = Math.min(4, Math.max(0.35, scale));
  renderPage();
}

async function renderPage() {
  if (!state.pdf) {
    return;
  }
  const token = ++state.renderToken;
  const page = await state.pdf.getPage(state.pageNumber);
  const unscaledViewport = page.getViewport({ scale: 1 });
  if (state.fitWidth) {
    const availableWidth = Math.max(260, pageHost.clientWidth - 48);
    state.scale = Math.max(0.35, Math.min(3.5, availableWidth / unscaledViewport.width));
  }
  const viewport = page.getViewport({ scale: state.scale });
  const outputScale = window.devicePixelRatio || 1;

  pageFrame.style.width = `${viewport.width}px`;
  pageFrame.style.height = `${viewport.height}px`;
  canvas.width = Math.floor(viewport.width * outputScale);
  canvas.height = Math.floor(viewport.height * outputScale);
  canvas.style.width = `${viewport.width}px`;
  canvas.style.height = `${viewport.height}px`;
  textLayer.style.width = `${viewport.width}px`;
  textLayer.style.height = `${viewport.height}px`;
  highlightLayer.style.width = `${viewport.width}px`;
  highlightLayer.style.height = `${viewport.height}px`;
  textLayer.textContent = "";
  highlightLayer.textContent = "";

  const context = canvas.getContext("2d");
  context.setTransform(outputScale, 0, 0, outputScale, 0, 0);
  viewerStatus.textContent = `Rendering page ${state.pageNumber.toLocaleString()}...`;
  await page.render({ canvasContext: context, viewport }).promise;
  if (token !== state.renderToken) {
    return;
  }

  const textContent = await page.getTextContent();
  await renderSelectableText(textContent, viewport);
  if (token !== state.renderToken) {
    return;
  }

  state.highlights = buildHighlights(query);
  state.activeHighlight = 0;
  activateHighlight(0, { scroll: false });
  zoomLabel.textContent = `${Math.round(state.scale * 100)}%`;
  viewerStatus.textContent = state.highlights.length
    ? `${state.highlights.length.toLocaleString()} match${state.highlights.length === 1 ? "" : "es"} on page ${state.pageNumber.toLocaleString()}`
    : `No exact text-layer match found on page ${state.pageNumber.toLocaleString()}`;
}

async function renderSelectableText(textContent, viewport) {
  if (typeof pdfjsLib.renderTextLayer === "function") {
    const task = pdfjsLib.renderTextLayer({
      textContentSource: textContent,
      container: textLayer,
      viewport,
      textDivs: [],
    });
    await task.promise;
    return;
  }
  renderBasicTextLayer(textContent, viewport);
}

function renderBasicTextLayer(textContent, viewport) {
  for (const item of textContent.items || []) {
    const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
    const span = document.createElement("span");
    span.textContent = item.str;
    span.style.left = `${tx[4]}px`;
    span.style.top = `${tx[5]}px`;
    span.style.fontSize = `${Math.abs(tx[3])}px`;
    span.style.transform = `scaleX(${item.width ? viewport.scale * item.width / Math.max(1, span.textContent.length * Math.abs(tx[3]) * 0.55) : 1})`;
    textLayer.append(span);
  }
}

function buildHighlights(rawQuery) {
  const spans = [...textLayer.querySelectorAll("span")].filter((span) => span.textContent);
  const { text, map } = mappedText(spans);
  const ranges = matchRanges(text.toLowerCase(), rawQuery);
  const highlights = [];

  for (const range of ranges) {
    const start = nextMappedChar(map, range.start, 1);
    const end = nextMappedChar(map, range.end - 1, -1);
    if (!start || !end || start.node !== end.node && !start.node.isConnected) {
      continue;
    }
    const domRange = document.createRange();
    try {
      domRange.setStart(start.node, start.offset);
      domRange.setEnd(end.node, end.offset + 1);
    } catch {
      continue;
    }
    const rects = [...domRange.getClientRects()];
    domRange.detach();
    const pageRect = pageFrame.getBoundingClientRect();
    const boxes = rects
      .filter((rect) => rect.width > 1 && rect.height > 1)
      .map((rect) => makeHighlightBox(rect, pageRect));
    if (boxes.length) {
      highlights.push(...boxes);
    }
  }
  return highlights;
}

function mappedText(spans) {
  let text = "";
  const map = [];
  for (const span of spans) {
    const node = span.firstChild;
    if (!node) {
      continue;
    }
    if (text.length) {
      text += " ";
      map.push(null);
    }
    const value = span.textContent || "";
    for (let index = 0; index < value.length; index += 1) {
      text += value[index];
      map.push({ node, offset: index });
    }
  }
  return { text, map };
}

function matchRanges(text, rawQuery) {
  const terms = queryTerms(rawQuery);
  const ranges = [];
  for (const term of terms) {
    const needle = term.toLowerCase();
    let start = text.indexOf(needle);
    while (start !== -1) {
      ranges.push({ start, end: start + needle.length });
      start = text.indexOf(needle, start + Math.max(1, needle.length));
    }
  }
  ranges.sort((left, right) => left.start - right.start || right.end - left.end);
  return ranges;
}

function queryTerms(rawQuery) {
  const value = String(rawQuery || "").trim();
  if (!value) {
    return [];
  }
  const phrases = [...value.matchAll(/"([^"]+)"/g)]
    .map((match) => normalizeSpaces(match[1]))
    .filter((term) => term.length > 1);
  const unquoted = value.replace(/"[^"]+"/g, " ");
  const words = unquoted
    .split(/\s+/)
    .map((term) => normalizeSpaces(term))
    .filter((term) => term.length > 1);
  return [...phrases, normalizeSpaces(unquoted).trim(), ...words]
    .filter(Boolean)
    .filter((term, index, all) => all.indexOf(term) === index);
}

function normalizeSpaces(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function nextMappedChar(map, index, direction) {
  let cursor = index;
  while (cursor >= 0 && cursor < map.length) {
    if (map[cursor]) {
      return map[cursor];
    }
    cursor += direction;
  }
  return null;
}

function makeHighlightBox(rect, pageRect) {
  const box = document.createElement("div");
  box.className = "match-highlight";
  box.style.left = `${rect.left - pageRect.left}px`;
  box.style.top = `${rect.top - pageRect.top}px`;
  box.style.width = `${rect.width}px`;
  box.style.height = `${rect.height}px`;
  highlightLayer.append(box);
  return box;
}

function activateHighlight(index, options = {}) {
  if (!state.highlights.length) {
    return;
  }
  const scroll = options.scroll !== false;
  state.activeHighlight = (index + state.highlights.length) % state.highlights.length;
  state.highlights.forEach((highlight, itemIndex) => {
    highlight.classList.toggle("active", itemIndex === state.activeHighlight);
  });
  if (scroll) {
    state.highlights[state.activeHighlight].scrollIntoView({ block: "center", inline: "center" });
  }
}

function showError(message) {
  viewerStatus.textContent = "Unavailable";
  pageHost.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
