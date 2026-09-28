from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from urllib.parse import quote

from onenote_indexer.auth import get_access_token
from onenote_indexer.config import load_config
from onenote_indexer.graph import GraphClient
from onenote_indexer.page_html import extract_resources


def audit_once(section_name: str, source_titles: list[str], out_dir: Path, prefix: str) -> dict:
    graph = GraphClient(get_access_token(load_config()))
    me = graph.me()
    notebook = next(n for n in graph.notebooks() if n.get("displayName") == "Samira")
    sections = graph.collection(
        f"/me/onenote/notebooks/{quote(notebook['id'], safe='')}/sections",
        **{"$top": 100},
    )
    matches = [s for s in sections if s.get("displayName") == section_name]

    summary: dict = {
        "validatedAccount": me.get("userPrincipalName"),
        "section": section_name,
        "sectionCount": len(matches),
        "localSourcePageCount": len(source_titles),
        "graphPageCount": 0,
        "titleOrderMatches": False,
        "titleMultisetMatches": False,
        "htmlFetchOkPages": 0,
        "htmlFetchFailedPages": 0,
        "pdfResourceCount": 0,
        "pdfDownloadOkCount": 0,
        "pdfDownloadFailedCount": 0,
        "pdfDownloadedMB": 0.0,
        "totalFullresImageCount": 0,
        "success": False,
        "failures": [],
    }
    if len(matches) != 1:
        summary["failures"].append(
            {"section": section_name, "error": f"Expected exactly one section; found {len(matches)}"}
        )
        return write_outputs(summary, [], out_dir, prefix)

    section = matches[0]
    pages = graph.collection(
        f"/me/onenote/sections/{quote(section['id'], safe='')}/pages",
        **{"$top": 100, "pagelevel": "true"},
    )
    pages = sorted(pages, key=lambda p: p.get("order", 999999))
    graph_titles = [p.get("title", "") for p in pages]
    summary["graphPageCount"] = len(pages)
    summary["titleOrderMatches"] = source_titles == graph_titles
    summary["titleMultisetMatches"] = sorted(source_titles) == sorted(graph_titles)

    page_rows: list[dict] = []
    pdf_bytes = 0
    pdf_count = 0
    pdf_ok = 0
    fullres_count = 0
    html_ok = 0
    failures: list[dict] = []

    for index, page in enumerate(pages, start=1):
        title = page.get("title", "")
        row = {
            "Order": index,
            "GraphOrder": page.get("order", ""),
            "Title": title,
            "PageId": page.get("id", ""),
            "HtmlOk": False,
            "HtmlBytes": 0,
            "ResourceCount": 0,
            "PdfResourceCount": 0,
            "PdfDownloadOkCount": 0,
            "PdfBytes": 0,
            "ImageFullresCount": 0,
            "Error": "",
        }
        try:
            html = graph.page_content(page["id"])
            html_ok += 1
            row["HtmlOk"] = True
            row["HtmlBytes"] = len(html.encode("utf-8"))
            resources = extract_resources(html)
            row["ResourceCount"] = len(resources)
            for resource in resources:
                if resource.kind == "image-fullres":
                    row["ImageFullresCount"] += 1
                    fullres_count += 1
                if resource.kind == "application/pdf":
                    row["PdfResourceCount"] += 1
                    pdf_count += 1
                    try:
                        data = graph.get_bytes(resource.url)
                        size = len(data)
                        row["PdfDownloadOkCount"] += 1
                        row["PdfBytes"] += size
                        pdf_ok += 1
                        pdf_bytes += size
                    except Exception as exc:  # noqa: BLE001
                        failures.append({"page": title, "error": str(exc)[:800]})
        except Exception as exc:  # noqa: BLE001
            row["Error"] = str(exc)[:800]
            failures.append({"page": title, "error": str(exc)[:800]})
        page_rows.append(row)
        time.sleep(0.1)

    summary.update(
        {
            "htmlFetchOkPages": html_ok,
            "htmlFetchFailedPages": len(pages) - html_ok,
            "pdfResourceCount": pdf_count,
            "pdfDownloadOkCount": pdf_ok,
            "pdfDownloadFailedCount": pdf_count - pdf_ok,
            "pdfDownloadedMB": round(pdf_bytes / 1024 / 1024, 2),
            "totalFullresImageCount": fullres_count,
            "failures": failures,
        }
    )
    summary["success"] = (
        summary["sectionCount"] == 1
        and summary["graphPageCount"] == len(source_titles)
        and summary["titleOrderMatches"]
        and summary["htmlFetchFailedPages"] == 0
        and summary["pdfDownloadFailedCount"] == 0
    )
    return write_outputs(summary, page_rows, out_dir, prefix)


def write_outputs(summary: dict, page_rows: list[dict], out_dir: Path, prefix: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{prefix}_graph_audit.json"
    md_path = out_dir / f"{prefix}_graph_audit.md"
    pages_csv = out_dir / f"{prefix}_graph_pages.csv"

    if page_rows:
        with pages_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(page_rows[0].keys()))
            writer.writeheader()
            writer.writerows(page_rows)
        summary["pagesCsv"] = str(pages_csv)

    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [
        f"# Graph Audit: {summary['section']}",
        "",
        f"Validated account: `{summary.get('validatedAccount')}`",
        "",
        "## Results",
        "",
        f"- Section count: {summary['sectionCount']}",
        f"- Local UofT source page count: {summary['localSourcePageCount']}",
        f"- Graph page count: {summary['graphPageCount']}",
        f"- Title order matches: {summary['titleOrderMatches']}",
        f"- Title multiset matches: {summary['titleMultisetMatches']}",
        f"- Pages with Graph HTML fetched: {summary['htmlFetchOkPages']}",
        f"- Pages with Graph HTML fetch failures: {summary['htmlFetchFailedPages']}",
        f"- PDF resources detected: {summary['pdfResourceCount']}",
        f"- PDF resources downloaded successfully: {summary['pdfDownloadOkCount']}",
        f"- PDF resource download failures: {summary['pdfDownloadFailedCount']}",
        f"- Downloaded PDF total: {summary['pdfDownloadedMB']:.2f} MB",
        f"- Full-resolution printout images detected: {summary['totalFullresImageCount']}",
        f"- Success: {summary['success']}",
        "",
        "## Failures",
        "",
    ]
    failures = summary.get("failures") or []
    if failures:
        md.extend(f"- `{failure}`" for failure in failures[:50])
    else:
        md.append("- None.")
    md_path.write_text("\n".join(md), encoding="utf-8")
    summary["jsonPath"] = str(json_path)
    summary["markdownPath"] = str(md_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", required=True)
    parser.add_argument("--source-order-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--prefix", default="audit")
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--delay-seconds", type=int, default=180)
    args = parser.parse_args()

    source_titles = json.loads(Path(args.source_order_json).read_text(encoding="utf-8-sig"))
    out_dir = Path(args.out_dir)
    last_summary: dict | None = None
    for attempt in range(1, args.max_attempts + 1):
        summary = audit_once(args.section, source_titles, out_dir, f"{args.prefix}_attempt_{attempt:02d}")
        summary["attempt"] = attempt
        (out_dir / f"{args.prefix}_latest_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
        last_summary = summary
        if summary.get("success"):
            return
        if attempt < args.max_attempts:
            time.sleep(args.delay_seconds)

    raise SystemExit(0 if last_summary and last_summary.get("success") else 2)


if __name__ == "__main__":
    main()
