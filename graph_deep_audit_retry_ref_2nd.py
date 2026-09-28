from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from urllib.parse import quote

from onenote_indexer.auth import get_access_token
from onenote_indexer.config import load_config
from onenote_indexer.graph import GraphClient
from onenote_indexer.page_html import extract_resources

ROOT = Path(r"C:\Users\USER\OneDrive - University of Toronto\Desktop\one note references")
TARGET_SECTION = "RETRY ref.2nd nonlinear 20260927 2336"
TARGET_PAGE = "Enhanced Third Harmonic Generation in Single Germanium Nanodisks Excited at the Anapole Mode"


def main() -> None:
    graph = GraphClient(get_access_token(load_config()))
    me = graph.me()
    notebooks = graph.notebooks()
    samira = next(n for n in notebooks if n.get("displayName") == "Samira")
    sections = graph.collection(f"/me/onenote/notebooks/{quote(samira['id'], safe='')}/sections", **{"$top": 100})
    section = next(s for s in sections if s.get("displayName") == TARGET_SECTION)
    pages = graph.pages_for_section(section["id"])
    pages = sorted(pages, key=lambda p: p.get("order", 999999))

    page_rows = []
    resource_rows = []
    failures = []
    total_pdf_bytes = 0
    total_pdf_downloaded = 0

    for page_index, page in enumerate(pages, start=1):
        title = page.get("title", "")
        page_id = page["id"]
        row = {
            "Order": page_index,
            "Title": title,
            "PageId": page_id,
            "HtmlFetchOk": False,
            "HtmlBytes": 0,
            "ResourceCount": 0,
            "PdfResourceCount": 0,
            "ImageFullresCount": 0,
            "PdfDownloadOkCount": 0,
            "PdfBytes": 0,
            "Error": "",
        }
        try:
            html = graph.page_content(page_id)
            resources = extract_resources(html)
            row["HtmlFetchOk"] = True
            row["HtmlBytes"] = len(html.encode("utf-8"))
            row["ResourceCount"] = len(resources)
            row["PdfResourceCount"] = sum(1 for r in resources if r.kind == "application/pdf")
            row["ImageFullresCount"] = sum(1 for r in resources if r.kind == "image-fullres")

            for resource_index, resource in enumerate(resources, start=1):
                rrow = {
                    "PageOrder": page_index,
                    "PageTitle": title,
                    "ResourceIndex": resource_index,
                    "Tag": resource.tag,
                    "Kind": resource.kind,
                    "Alt": resource.alt or "",
                    "DownloadAttempted": False,
                    "DownloadOk": "",
                    "Bytes": "",
                    "Error": "",
                    "Url": resource.url,
                }
                if resource.kind == "application/pdf":
                    rrow["DownloadAttempted"] = True
                    try:
                        data = graph.get_bytes(resource.url)
                        b = len(data)
                        rrow["DownloadOk"] = True
                        rrow["Bytes"] = b
                        row["PdfDownloadOkCount"] += 1
                        row["PdfBytes"] += b
                        total_pdf_bytes += b
                        total_pdf_downloaded += 1
                    except Exception as exc:  # noqa: BLE001
                        rrow["DownloadOk"] = False
                        rrow["Error"] = str(exc)[:500]
                        failures.append({"page": title, "resource": resource_index, "error": str(exc)})
                resource_rows.append(rrow)
        except Exception as exc:  # noqa: BLE001
            row["Error"] = str(exc)[:500]
            failures.append({"page": title, "error": str(exc)})
        page_rows.append(row)
        time.sleep(0.15)

    pages_csv = ROOT / "onenote_retry_ref_2nd_nonlinear_graph_page_content_audit.csv"
    with pages_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(page_rows[0].keys()))
        writer.writeheader()
        writer.writerows(page_rows)

    resources_csv = ROOT / "onenote_retry_ref_2nd_nonlinear_graph_resource_download_audit.csv"
    with resources_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(resource_rows[0].keys()))
        writer.writeheader()
        writer.writerows(resource_rows)

    summary = {
        "validatedAccount": me.get("userPrincipalName"),
        "notebook": samira.get("displayName"),
        "section": TARGET_SECTION,
        "pageCount": len(pages),
        "htmlFetchOkPages": sum(1 for r in page_rows if r["HtmlFetchOk"]),
        "htmlFetchFailedPages": sum(1 for r in page_rows if not r["HtmlFetchOk"]),
        "pagesWithPdfResource": sum(1 for r in page_rows if r["PdfResourceCount"] > 0),
        "pdfResourceCount": sum(r["PdfResourceCount"] for r in page_rows),
        "pdfDownloadOkCount": total_pdf_downloaded,
        "pdfDownloadFailedCount": sum(1 for r in resource_rows if r["DownloadAttempted"] and r["DownloadOk"] == False),
        "pdfDownloadedBytes": total_pdf_bytes,
        "pdfDownloadedMB": round(total_pdf_bytes / 1024 / 1024, 2),
        "totalResourceCount": len(resource_rows),
        "totalFullresImageCount": sum(r["ImageFullresCount"] for r in page_rows),
        "targetFailedPage": next((r for r in page_rows if r["Title"] == TARGET_PAGE), None),
        "failures": failures,
        "files": {
            "pagesCsv": str(pages_csv),
            "resourcesCsv": str(resources_csv),
        },
    }

    summary_json = ROOT / "onenote_retry_ref_2nd_nonlinear_graph_deep_audit.json"
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Graph Deep Audit: RETRY ref.2nd nonlinear 20260927 2336",
        "",
        f"Validated account: `{summary['validatedAccount']}`",
        f"Notebook: `{summary['notebook']}`",
        f"Section: `{summary['section']}`",
        "",
        "## Results",
        "",
        f"- Page count: {summary['pageCount']}",
        f"- Pages with Graph HTML fetched: {summary['htmlFetchOkPages']}",
        f"- Pages with Graph HTML fetch failures: {summary['htmlFetchFailedPages']}",
        f"- Pages with PDF resource: {summary['pagesWithPdfResource']}",
        f"- PDF resources detected: {summary['pdfResourceCount']}",
        f"- PDF resources downloaded successfully: {summary['pdfDownloadOkCount']}",
        f"- PDF resource download failures: {summary['pdfDownloadFailedCount']}",
        f"- Downloaded PDF total: {summary['pdfDownloadedMB']:.2f} MB",
        f"- Total resources detected: {summary['totalResourceCount']}",
        f"- Full-resolution printout images detected: {summary['totalFullresImageCount']}",
        "",
        "## Previously failing page",
        "",
    ]
    target = summary["targetFailedPage"]
    if target:
        md.extend([
            f"- Title: `{target['Title']}`",
            f"- Graph HTML fetched: {target['HtmlFetchOk']}",
            f"- HTML size: {target['HtmlBytes']} bytes",
            f"- Resources: {target['ResourceCount']}",
            f"- PDF resources: {target['PdfResourceCount']}",
            f"- PDF downloads OK: {target['PdfDownloadOkCount']}",
            f"- PDF bytes: {target['PdfBytes']} bytes",
        ])
    else:
        md.append("- Target page not found in deep audit rows.")
    md.extend(["", "## Failures", ""])
    if failures:
        md.extend(f"- `{f}`" for f in failures)
    else:
        md.append("- None.")
    md.extend([
        "",
        "## Files",
        "",
        f"- Page content audit CSV: `{pages_csv}`",
        f"- Resource download audit CSV: `{resources_csv}`",
        f"- Raw summary JSON: `{summary_json}`",
    ])
    md_path = ROOT / "onenote_retry_ref_2nd_nonlinear_graph_deep_audit.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
