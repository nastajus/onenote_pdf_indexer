# OneNote PDF Indexer

Local tooling for connecting to Microsoft Graph, reading OneNote notebook structure, and preparing a searchable PDF index.

## Current Milestone

This first pass only proves that Microsoft Graph can see the OneNote notebooks/pages in the personal Microsoft account.

## Setup

```powershell
cd "C:\Users\USER\OneDrive - University of Toronto\Desktop\one note references\onenote_pdf_indexer"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Test Connection

```powershell
.\.venv\Scripts\python.exe -m onenote_indexer whoami
.\.venv\Scripts\python.exe -m onenote_indexer notebooks
.\.venv\Scripts\python.exe -m onenote_indexer sections
.\.venv\Scripts\python.exe -m onenote_indexer pages --limit 25
```

The first command opens a Microsoft sign-in page. Sign in as the personal Microsoft account that owns the copied notebook.

If the browser redirect gets stuck, use device-code login:

```powershell
.\.venv\Scripts\python.exe -m onenote_indexer whoami --device-code --force-login
```

Inspect embedded resources on a page:

```powershell
.\.venv\Scripts\python.exe -m onenote_indexer resources --page-id "PASTE_PAGE_ID_HERE"
```

Known OneNote/Graph behavior: large accounts should be scanned section-by-section. A global pages request can fail when there are many sections.

## Launch In VS Code

Open this folder in VS Code:

```powershell
code "C:\Users\USER\OneDrive - University of Toronto\Desktop\one note references\onenote_pdf_indexer"
```

Then use **Run and Debug** and choose:

```text
OneNote UI: Chrome
```

That starts the local Python server and opens Chrome at:

```text
http://127.0.0.1:8765
```

Other debug options:

- `Debug OneNote web server` starts only the Python server.
- `Debug OneNote CLI: notebooks` runs the notebook-listing CLI command under the debugger.

## Current Browser Behavior

- Notebooks and sections are cached in `data/cache.sqlite3`.
- Cached notebooks/sections are shown immediately, then silently refreshed from Graph on startup, browser focus, and a slow interval.
- This local project sorts the `Samira` notebook first when present.
- Sections are clickable.
- Page metadata loads section-by-section and is cached locally.
- Embedded resources are cached locally after a page is inspected.
- Embedded PDF bytes are cached locally and served back through `/api/resource`.
- `image-fullres` resources are OneNote printout images, usually rendered PDF pages. These need OCR for text extraction.
- `application/pdf` resources are original embedded PDFs. The app extracts and caches text from those PDFs by PDF page.
- The server reads from cache before authenticating with Graph wherever possible.
- The bottom control dock switches between embedded PDF view, extracted text view, and OneNote page layout preview.
- **Search PDF Text** toggles full cached PDF-content search. Leave it off for fast title filtering; turn it on when you want results from extracted paper text and PDF page numbers.
- The bottom cache bar shows downloaded/discovered PDF cache progress. Its tooltip explains the current denominator and rough remaining batch time.
- Drag the vertical handles between columns to resize the notebook, page, and PDF/text panels.
- Use each panel arrow to collapse/restore a panel when you want to maximize the PDF area.
- Use **Reset Layout** to restore the default column layout and reopen collapsed panels.
- A diamond marker on a page means embedded resources for that page are cached locally.
- Stale OneNote/Graph resource `404` responses are handled gracefully; cached resources are used first, missing refreshed resources are pruned, and page-content failures retry alternate cached Graph URLs before showing diagnostics.

Use **Refresh** to force a fresh Graph fetch for notebooks, sections, and the selected section. OneNote/Graph can still take a short while to reflect newly created or deleted notebooks after OneDrive/OneNote sync.
Use **Refresh Selected** to refresh the selected page/section and prune cached resource data for resources that no longer match the OneNote page.

## Warm The Cache

Run a throttled cache fill from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m onenote_indexer warm-cache --max-pages 100 --max-mb 750 --delay 1.0
```

Defaults are conservative: PDFs only, PDF text extraction enabled, 100 pages inspected, 750 MB max new downloads, and a 1 second delay around Graph fetches. The command is resumable and skips already cached PDFs.

Useful variants:

```powershell
.\.venv\Scripts\python.exe -m onenote_indexer warm-cache --section "anapole" --max-pages 50
.\.venv\Scripts\python.exe -m onenote_indexer warm-cache --include-images --max-mb 250
.\.venv\Scripts\python.exe -m onenote_indexer warm-cache --refresh-metadata
```

## Git Checkpoints

Project-local Git automation lives at:

```powershell
.\scripts\auto_commit.ps1 -Message "Codex checkpoint: short summary"
```

It initializes a Git repository in `onenote_pdf_indexer` if needed, stages project files, and commits. It intentionally ignores `.venv/` and `data/`, including token/cache files.

Git for Windows must be installed and available on `PATH`:

```powershell
git --version
```

## Local Files

- `config/config.json` contains the app registration IDs. These are not secrets.
- `data/token_cache.bin` is created after login and contains reusable auth tokens. Do not share it.
