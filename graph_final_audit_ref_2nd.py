from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import quote
from onenote_indexer.auth import get_access_token
from onenote_indexer.config import load_config
from onenote_indexer.graph import GraphClient
from onenote_indexer.page_html import extract_resources
ROOT = Path(r"C:\Users\USER\OneDrive - University of Toronto\Desktop\one note references")
graph = GraphClient(get_access_token(load_config()))
me = graph.me()
notebook = next(n for n in graph.notebooks() if n.get("displayName") == "Samira")
sections = graph.collection(f"/me/onenote/notebooks/{quote(notebook['id'], safe='')}/sections", **{"$top": 100})
ref_sections = [s for s in sections if s.get("displayName") == "ref.2nd nonlinear"]
retry_sections = [s for s in sections if "RETRY ref.2nd nonlinear" in s.get("displayName", "")]
if len(ref_sections) != 1:
    raise SystemExit(f"Expected exactly one ref.2nd nonlinear section, found {len(ref_sections)}")
section = ref_sections[0]
pages = sorted(graph.pages_for_section(section["id"]), key=lambda p: p.get("order", 999999))
page_rows=[]
resource_failures=[]
pdf_count=pdf_ok=pdf_bytes=html_ok=0
for p in pages:
    row={"Title":p.get("title",""),"HtmlOk":False,"PdfResourceCount":0,"PdfDownloadOkCount":0,"PdfBytes":0,"Error":""}
    try:
        html=graph.page_content(p["id"])
        html_ok += 1
        row["HtmlOk"] = True
        resources=extract_resources(html)
        for r in resources:
            if r.kind == "application/pdf":
                pdf_count += 1
                row["PdfResourceCount"] += 1
                try:
                    data=graph.get_bytes(r.url)
                    pdf_ok += 1
                    row["PdfDownloadOkCount"] += 1
                    row["PdfBytes"] += len(data)
                    pdf_bytes += len(data)
                except Exception as exc:
                    resource_failures.append({"page": row["Title"], "error": str(exc)[:500]})
    except Exception as exc:
        row["Error"] = str(exc)[:500]
    page_rows.append(row)
summary={
    "validatedAccount": me.get("userPrincipalName"),
    "notebook": notebook.get("displayName"),
    "refSectionCount": len(ref_sections),
    "retryPrefixedSectionCount": len(retry_sections),
    "sectionDisplayName": section.get("displayName"),
    "sectionId": section.get("id"),
    "pageCount": len(pages),
    "htmlFetchOkPages": html_ok,
    "pdfResourceCount": pdf_count,
    "pdfDownloadOkCount": pdf_ok,
    "pdfDownloadFailedCount": len(resource_failures),
    "pdfDownloadedMB": round(pdf_bytes/1024/1024,2),
    "failures": resource_failures,
}
(ROOT / "onenote_ref_2nd_nonlinear_final_graph_audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
md = ["# Final Graph Audit: ref.2nd nonlinear", "", f"Validated account: `{summary['validatedAccount']}`", "", "## Results", "", f"- `ref.2nd nonlinear` section count: {summary['refSectionCount']}", f"- retry-prefixed section count: {summary['retryPrefixedSectionCount']}", f"- Page count: {summary['pageCount']}", f"- Pages with Graph HTML fetched: {summary['htmlFetchOkPages']}", f"- PDF resources detected: {summary['pdfResourceCount']}", f"- PDF resources downloaded successfully: {summary['pdfDownloadOkCount']}", f"- PDF resource download failures: {summary['pdfDownloadFailedCount']}", f"- Downloaded PDF total: {summary['pdfDownloadedMB']:.2f} MB", "", "## Failures", ""]
if resource_failures:
    md.extend([f"- `{f}`" for f in resource_failures])
else:
    md.append("- None.")
(ROOT / "onenote_ref_2nd_nonlinear_final_graph_audit.md").write_text("\n".join(md), encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
