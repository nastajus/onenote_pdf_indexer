from __future__ import annotations

import csv
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from onenote_indexer.auth import get_access_token
from onenote_indexer.config import load_config
from onenote_indexer.graph import GraphClient
from onenote_indexer.page_html import extract_resources

ROOT = Path(r"C:\Users\USER\OneDrive - University of Toronto\Desktop\one note references")
TARGET_SECTION = "RETRY ref.2nd nonlinear 20260927 2336"
SOURCE_SECTION = "ref.2nd nonlinear"
TARGET_PAGE = "Enhanced Third Harmonic Generation in Single Germanium Nanodisks Excited at the Anapole Mode"

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)


def text_from_html(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


def main() -> None:
    config = load_config()
    graph = GraphClient(get_access_token(config))
    me = graph.me()
    notebooks = graph.notebooks()
    samira = next((n for n in notebooks if n.get("displayName") == "Samira"), None)
    if not samira:
        raise SystemExit("Graph could not find notebook named Samira")

    sections = graph.collection(f"/me/onenote/notebooks/{quote(samira['id'], safe='')}/sections", **{"$top": 100})
    target_section = next((s for s in sections if s.get("displayName") == TARGET_SECTION), None)
    if not target_section:
        raise SystemExit(f"Graph could not find section {TARGET_SECTION!r}")

    pages = graph.pages_for_section(target_section["id"])
    pages_sorted = sorted(pages, key=lambda p: p.get("order", 999999))
    target_page = next((p for p in pages_sorted if p.get("title") == TARGET_PAGE), None)
    if not target_page:
        raise SystemExit(f"Graph could not find page {TARGET_PAGE!r}")

    html = graph.page_content(target_page["id"])
    text = text_from_html(html)
    resources = extract_resources(html)

    source_titles_path = ROOT / "onenote_retry_ref_2nd_nonlinear_page_title_validation.csv"
    local_source_titles = []
    if source_titles_path.exists():
        with source_titles_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                if str(row.get("InUofTSource", "")).lower() == "true":
                    local_source_titles.append(row["Title"])

    graph_titles = [p.get("title", "") for p in pages_sorted]
    missing_from_graph = [title for title in local_source_titles if title not in graph_titles]
    extra_in_graph = [title for title in graph_titles if title not in local_source_titles]

    page_rows = []
    for index, page in enumerate(pages_sorted, start=1):
        page_rows.append({
            "Order": index,
            "Title": page.get("title", ""),
            "GraphPageId": page.get("id", ""),
            "CreatedDateTime": page.get("createdDateTime", ""),
            "LastModifiedDateTime": page.get("lastModifiedDateTime", ""),
            "Level": page.get("level", ""),
            "LinksOneNoteWebUrl": ((page.get("links") or {}).get("oneNoteWebUrl") or {}).get("href", ""),
        })

    csv_path = ROOT / "onenote_retry_ref_2nd_nonlinear_graph_pages.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(page_rows[0].keys()))
        writer.writeheader()
        writer.writerows(page_rows)

    resources_path = ROOT / "onenote_retry_ref_2nd_nonlinear_failed_page_graph_resources.csv"
    with resources_path.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = ["Index", "Tag", "Kind", "Alt", "Url"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for i, resource in enumerate(resources, start=1):
            writer.writerow({"Index": i, "Tag": resource.tag, "Kind": resource.kind, "Alt": resource.alt, "Url": resource.url})

    html_path = ROOT / "onenote_retry_ref_2nd_nonlinear_failed_page_graph_content.html"
    html_path.write_text(html, encoding="utf-8")

    text_path = ROOT / "onenote_retry_ref_2nd_nonlinear_failed_page_graph_text.txt"
    text_path.write_text(text, encoding="utf-8")

    summary = {
        "validatedAccount": me.get("userPrincipalName"),
        "notebook": samira.get("displayName"),
        "notebookId": samira.get("id"),
        "section": target_section.get("displayName"),
        "sectionId": target_section.get("id"),
        "graphPageCount": len(pages_sorted),
        "localSourcePageCount": len(local_source_titles),
        "titlesMatchLocalSource": not missing_from_graph and not extra_in_graph and len(graph_titles) == len(local_source_titles),
        "missingFromGraph": missing_from_graph,
        "extraInGraph": extra_in_graph,
        "targetPageFound": True,
        "targetPageId": target_page.get("id"),
        "targetPageLastModifiedDateTime": target_page.get("lastModifiedDateTime"),
        "targetPageHtmlBytes": len(html.encode("utf-8")),
        "targetPageExtractedTextChars": len(text),
        "targetPageResourceCount": len(resources),
        "targetPagePdfResourceNames": [r.alt for r in resources if "pdf" in (r.alt or "").lower() or "pdf" in (r.url or "").lower()],
        "files": {
            "pagesCsv": str(csv_path),
            "resourcesCsv": str(resources_path),
            "html": str(html_path),
            "text": str(text_path),
        }
    }
    summary_path = ROOT / "onenote_retry_ref_2nd_nonlinear_graph_audit.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md_path = ROOT / "onenote_retry_ref_2nd_nonlinear_graph_audit.md"
    pdfs = summary["targetPagePdfResourceNames"]
    md = [
        "# Graph Audit: RETRY ref.2nd nonlinear 20260927 2336",
        "",
        f"Validated account: `{summary['validatedAccount']}`",
        "",
        f"Notebook: `{summary['notebook']}`",
        f"Section: `{summary['section']}`",
        "",
        "## Results",
        "",
        f"- Graph page count: {summary['graphPageCount']}",
        f"- Local UofT source page count: {summary['localSourcePageCount']}",
        f"- Page titles match local source: {summary['titlesMatchLocalSource']}",
        f"- Missing titles from Graph: {len(missing_from_graph)}",
        f"- Extra titles in Graph: {len(extra_in_graph)}",
        f"- Target failed page found by Graph: {summary['targetPageFound']}",
        f"- Target failed page HTML bytes: {summary['targetPageHtmlBytes']}",
        f"- Target failed page extracted text chars: {summary['targetPageExtractedTextChars']}",
        f"- Target failed page resource count: {summary['targetPageResourceCount']}",
        "",
        "## Target page PDF/resource signals",
        "",
    ]
    if pdfs:
        md.extend(f"- `{name}`" for name in pdfs)
    else:
        md.append("- No PDF-named resource detected in Graph HTML.")
    md.extend([
        "",
        "## Files",
        "",
        f"- Pages CSV: `{csv_path}`",
        f"- Resources CSV: `{resources_path}`",
        f"- Page HTML: `{html_path}`",
        f"- Page text: `{text_path}`",
        f"- Raw summary JSON: `{summary_path}`",
    ])
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
