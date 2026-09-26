from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
                self._send_json(pages)
                return

            if path == "/api/resources":
                page_id = query.get("page_id", [""])[0]
                if not page_id:
                    self._send_json({"error": "Missing page_id"}, status=400)
                    return
                resources = cache.get_resources(db, page_id)
                if force or not resources:
                    old_urls = {resource.get("url", "") for resource in resources}
                    resources = [resource.__dict__ for resource in extract_resources(get_graph().page_content(page_id))]
                    new_urls = {resource.get("url", "") for resource in resources}
                    cache.delete_missing_resource_data(db, page_id, new_urls)
                    cache.replace_resources(db, page_id, resources)
                    for stale_url in old_urls - new_urls:
                        cache.delete_missing_resource_data(db, page_id, new_urls | {stale_url})
                self._send_json(resources)
                return

            if path == "/api/resource":
                resource_url = query.get("resource_url", [""])[0]
                if not resource_url:
                    self._send_json({"error": "Missing resource_url"}, status=400)
                    return

                blob = cache.get_resource_blob(db, resource_url)
                if force or not blob:
                    body = get_graph().get_bytes(resource_url)
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
                        body = get_graph().get_bytes(resource_url)
                        blob = cache.put_resource_blob(db, resource_url, body, "application/pdf")
                    text = extract_pdf_text(blob["body"])
                    cache.put_pdf_text(db, page_id, resource_url, text)
                self._send_json(text)
                return

            self._send_json({"error": f"Unknown API route: {path}"}, status=404)
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
