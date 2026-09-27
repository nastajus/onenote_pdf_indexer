from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from .auth import get_access_token
from . import cache
from .config import PROJECT_ROOT, load_config
from .graph import GraphClient
from .page_html import extract_resources
from .pdf_text import extract_pdf_text


WEB_ROOT = PROJECT_ROOT / "web"


class OneNoteWebHandler(BaseHTTPRequestHandler):
    server_version = "OneNotePDFIndexer/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path.startswith("/api/"):
            self._handle_api(parsed.path, parse_qs(parsed.query))
            return

        self._handle_static(parsed.path)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            db = cache.connect()
            force = query.get("refresh", ["0"])[0] == "1"
            graph: GraphClient | None = None

            def get_graph() -> GraphClient:
                nonlocal graph
                if graph is None:
                    graph = _graph_client()
                return graph

            if path == "/api/whoami":
                self._send_json(get_graph().me())
                return

            if path == "/api/notebooks":
                notebooks = cache.get_collection(db, "notebooks")
                if force or not notebooks:
                    notebooks = get_graph().notebooks()
                    cache.replace_collection(db, "notebooks", notebooks)
                self._send_json(notebooks)
                return

            if path == "/api/sections":
                sections = cache.get_collection(db, "sections")
                if force or not sections:
                    sections = get_graph().sections()
                    cache.replace_collection(db, "sections", sections)
                self._send_json(sections)
                return

            if path == "/api/pages":
                section_id = query.get("section_id", [""])[0]
                if not section_id:
                    self._send_json({"error": "Missing section_id"}, status=400)
                    return

                pages = cache.get_pages(db, section_id)
                if force or not pages:
                    pages = get_graph().pages_for_section(section_id)
                    section = _section_from_cache(db, section_id)
                    for page in pages:
                        page["_section"] = section
                    cache.replace_pages(db, section_id, pages)
                for page in pages:
                    page["_cache"] = {
                        "resource_count": cache.resource_count(db, page["id"]),
                    }
                self._send_json(pages)
                return

            if path == "/api/resources":
                page_id = query.get("page_id", [""])[0]
                if not page_id:
                    self._send_json({"error": "Missing page_id"}, status=400)
                    return
                resources = cache.get_resources(db, page_id)
                if force or not resources:
                    try:
                        html, diagnostics = _page_content_with_fallback(get_graph(), db, page_id)
                        resources = [resource.__dict__ for resource in extract_resources(html)]
                    except RuntimeError as exc:
                        if resources:
                            self._send_json(resources)
                            return
                        self._send_json([_unavailable_resource(db, page_id, str(exc))])
                        return
                    new_urls = {resource.get("url", "") for resource in resources}
                    cache.delete_missing_resource_data(db, page_id, new_urls)
                    cache.replace_resources(db, page_id, resources)
                self._send_json(resources)
                return

            if path == "/api/search":
                query_text = query.get("q", [""])[0].strip()
                section_id = query.get("section_id", [""])[0] or None
                limit = _int_query(query, "limit", 50)
                if len(query_text) < 2:
                    self._send_json({"results": [], "indexed_rows": cache.pdf_search_row_count(db)})
                    return

                if cache.pdf_search_row_count(db) == 0:
                    cache.rebuild_pdf_search_index(db)

                self._send_json(
                    {
                        "results": cache.search_pdf_text(db, query_text, section_id=section_id, limit=limit),
                        "indexed_rows": cache.pdf_search_row_count(db),
                    }
                )
                return

            if path == "/api/cache-metrics":
                self._send_json(cache.cache_metrics(db))
                return

            if path == "/api/resource-info":
                resource_url = query.get("resource_url", [""])[0]
                if not resource_url:
                    self._send_json({"error": "Missing resource_url"}, status=400)
                    return

                blob = cache.get_resource_blob(db, resource_url)
                if force or not blob:
                    try:
                        body = get_graph().get_bytes(resource_url)
                    except RuntimeError as exc:
                        if _is_graph_not_found(exc):
                            cache.delete_resource_url(db, resource_url)
                            self._send_json(
                                {
                                    "available": False,
                                    "message": "OneNote no longer exposes this embedded resource. Removed stale cached references.",
                                }
                            )
                            return
                        raise
                    content_type = _content_type_for_resource(resource_url, query)
                    blob = cache.put_resource_blob(db, resource_url, body, content_type)
                self._send_json(
                    {
                        "available": True,
                        "content_type": blob.get("content_type"),
                        "size": blob["size"],
                        "sha256": blob["sha256"],
                    }
                )
                return

            if path == "/api/resource":
                resource_url = query.get("resource_url", [""])[0]
                if not resource_url:
                    self._send_json({"error": "Missing resource_url"}, status=400)
                    return

                blob = cache.get_resource_blob(db, resource_url)
                if force or not blob:
                    try:
                        body = get_graph().get_bytes(resource_url)
                    except RuntimeError as exc:
                        if _is_graph_not_found(exc):
                            cache.delete_resource_url(db, resource_url)
                            self._send_json({"error": "OneNote no longer exposes this embedded resource."}, status=404)
                            return
                        raise
                    content_type = _content_type_for_resource(resource_url, query)
                    blob = cache.put_resource_blob(db, resource_url, body, content_type)
                self._send_bytes(
                    blob["body"],
                    content_type=blob.get("content_type") or "application/octet-stream",
                    headers={
                        "X-Cache-SHA256": blob["sha256"],
                        "X-Cache-Size": str(blob["size"]),
                    },
                )
                return

            if path == "/api/pdf-text":
                page_id = query.get("page_id", [""])[0]
                resource_url = query.get("resource_url", [""])[0]
                if not page_id or not resource_url:
                    self._send_json({"error": "Missing page_id or resource_url"}, status=400)
                    return

                text = cache.get_pdf_text(db, page_id, resource_url)
                if force or not text:
                    blob = cache.get_resource_blob(db, resource_url)
                    if force or not blob:
                        try:
                            body = get_graph().get_bytes(resource_url)
                        except RuntimeError as exc:
                            if _is_graph_not_found(exc):
                                cache.delete_resource_url(db, resource_url)
                                self._send_json(
                                    {"error": "OneNote no longer exposes this embedded PDF. Removed stale cached references."},
                                    status=404,
                                )
                                return
                            raise
                        blob = cache.put_resource_blob(db, resource_url, body, "application/pdf")
                    text = extract_pdf_text(blob["body"])
                    cache.put_pdf_text(db, page_id, resource_url, text)
                self._send_json(text)
                return

            self._send_json(
                {
                    "error": f"Unknown API route: {path}",
                    "module": __file__,
                    "known_routes": ["/api/cache-metrics", "/api/search", "/api/resources"],
                },
                status=404,
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (WEB_ROOT / relative).resolve()

        try:
            target.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self.send_error(404)
            return

        if not target.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: object, *, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, payload: bytes, *, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "private, max-age=31536000")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)


def _graph_client() -> GraphClient:
    config = load_config()
    token = get_access_token(config)
    return GraphClient(token)


def _section_from_cache(db, section_id: str) -> dict[str, str | None]:
    for section in cache.get_collection(db, "sections"):
        if section.get("id") == section_id:
            return {
                "id": section.get("id"),
                "displayName": section.get("displayName"),
            }
    return {
        "id": section_id,
        "displayName": None,
    }


def _content_type_for_resource(resource_url: str, query: dict[str, list[str]]) -> str:
    kind = query.get("kind", [""])[0]
    if kind == "application/pdf" or resource_url.lower().endswith(".pdf"):
        return "application/pdf"
    if kind.startswith("image/"):
        return kind
    if "application/pdf" in kind:
        return "application/pdf"
    return "application/octet-stream"


def _page_content_with_fallback(graph: GraphClient, db, page_id: str) -> tuple[str, list[dict[str, str]]]:
    attempts: list[dict[str, str]] = []

    def try_get(label: str, url: str) -> str | None:
        try:
            html = graph.get_text(url)
            attempts.append({"source": label, "status": "ok"})
            return html
        except RuntimeError as exc:
            attempts.append({"source": label, "status": "failed", "error": _short_error(exc)})
            return None

    html = try_get("page id content endpoint", f"/me/onenote/pages/{quote(page_id, safe='')}/content")
    if html:
        return html, attempts

    page = cache.get_page(db, page_id) or {}
    content_url = page.get("contentUrl")
    if content_url:
        html = try_get("cached page contentUrl", content_url)
        if html:
            return html, attempts

    self_url = page.get("self")
    if self_url:
        html = try_get("cached page self/content", f"{self_url.rstrip('/')}/content")
        if html:
            return html, attempts

    raise RuntimeError(f"Graph could not return OneNote page content after fallback attempts: {attempts}")


def _unavailable_resource(db, page_id: str, error: str) -> dict[str, Any]:
    page = cache.get_page(db, page_id) or {}
    web_url = (((page.get("links") or {}).get("oneNoteWebUrl") or {}).get("href"))
    return {
        "tag": "status",
        "kind": "unavailable",
        "url": "",
        "message": "OneNote did not return this page's resources after retrying alternate content URLs.",
        "details": "Try opening the page in OneNote Online once, confirm it has finished syncing, then use Refresh Selected here.",
        "diagnostics": [
            {"label": "Page id", "value": page_id},
            {"label": "Graph error", "value": _short_text(error, 500)},
            {"label": "Content URL cached", "value": "yes" if page.get("contentUrl") else "no"},
            {"label": "Self URL cached", "value": "yes" if page.get("self") else "no"},
        ],
        "oneNoteWebUrl": web_url,
    }


def _short_error(exc: RuntimeError) -> str:
    return _short_text(str(exc), 300)


def _short_text(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."


def _int_query(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(query.get(key, [str(default)])[0])
    except ValueError:
        return default


def _is_graph_not_found(exc: RuntimeError) -> bool:
    return "HTTP 404" in str(exc) or "'code': '20102'" in str(exc) or '"code": "20102"' in str(exc)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Run the OneNote PDF Indexer browser UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    address = (args.host, args.port)
    print(f"Starting OneNote PDF Indexer web server on {args.host}:{args.port}", flush=True)

    httpd = ThreadingHTTPServer(address, OneNoteWebHandler)
    print(f"Serving OneNote PDF Indexer at http://{args.host}:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
