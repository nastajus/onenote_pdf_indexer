from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from . import cache
from .graph import GraphClient
from .page_html import extract_resources
from .pdf_text import extract_pdf_text


@dataclass
class WarmCacheOptions:
    max_pages: int = 100
    max_bytes: int = 750 * 1024 * 1024
    delay_seconds: float = 1.0
    section_filter: str | None = None
    extract_text: bool = True
    include_images: bool = False
    refresh_metadata: bool = False


@dataclass
class WarmCacheStats:
    sections_seen: int = 0
    pages_seen: int = 0
    pages_with_resources: int = 0
    resources_seen: int = 0
    resources_downloaded: int = 0
    bytes_downloaded: int = 0
    pdf_text_extracted: int = 0
    skipped_existing: int = 0
    not_found: int = 0
    errors: int = 0
    stopped_reason: str = "completed"


def warm_cache(
    graph: GraphClient,
    options: WarmCacheOptions,
    *,
    log: Callable[[str], None] = print,
) -> WarmCacheStats:
    db = cache.connect()
    stats = WarmCacheStats()

    sections = cache.get_collection(db, "sections")
    if options.refresh_metadata or not sections:
        log("Fetching sections from Graph...")
        sections = graph.sections()
        cache.replace_collection(db, "sections", sections)
        _sleep(options)

    if options.section_filter:
        needle = options.section_filter.lower()
        sections = [section for section in sections if needle in (section.get("displayName") or "").lower()]

    for section in sections:
        stats.sections_seen += 1
        section_name = section.get("displayName") or "(untitled section)"
        log(f"Section: {section_name}")

        pages = cache.get_pages(db, section["id"])
        if options.refresh_metadata or not pages:
            try:
                pages = graph.pages_for_section(section["id"])
                for page in pages:
                    page["_section"] = {
                        "id": section.get("id"),
                        "displayName": section.get("displayName"),
                    }
                cache.replace_pages(db, section["id"], pages)
                _sleep(options)
            except RuntimeError as exc:
                stats.errors += 1
                log(f"  Could not list pages: {_short_error(exc)}")
                continue

        for page in pages:
            if stats.pages_seen >= options.max_pages:
                stats.stopped_reason = f"page limit reached ({options.max_pages})"
                return stats
            if stats.bytes_downloaded >= options.max_bytes:
                stats.stopped_reason = f"byte limit reached ({_format_bytes(options.max_bytes)})"
                return stats

            stats.pages_seen += 1
            page_title = page.get("title") or "(untitled page)"

            resources = cache.get_resources(db, page["id"])
            if options.refresh_metadata or not resources:
                try:
                    resources = [resource.__dict__ for resource in extract_resources(graph.page_content(page["id"]))]
                    cache.replace_resources(db, page["id"], resources)
                    _sleep(options)
                except RuntimeError as exc:
                    if _is_graph_not_found(exc):
                        stats.not_found += 1
                        log(f"  Missing page resources: {page_title}")
                        continue
                    stats.errors += 1
                    log(f"  Resource listing failed for {page_title}: {_short_error(exc)}")
                    continue

            if resources:
                stats.pages_with_resources += 1

            for resource in resources:
                kind = resource.get("kind") or ""
                url = resource.get("url") or ""
                if not url:
                    continue
                if kind != "application/pdf" and not (options.include_images and kind.startswith("image")):
                    continue

                stats.resources_seen += 1
                if cache.has_resource_blob(db, url):
                    stats.skipped_existing += 1
                    if kind == "application/pdf" and options.extract_text and not cache.has_pdf_text(db, page["id"], url):
                        _extract_existing_pdf_text(db, page["id"], url, stats, log)
                    continue

                if stats.bytes_downloaded >= options.max_bytes:
                    stats.stopped_reason = f"byte limit reached ({_format_bytes(options.max_bytes)})"
                    return stats

                try:
                    body = graph.get_bytes(url)
                    _sleep(options)
                except RuntimeError as exc:
                    if _is_graph_not_found(exc):
                        cache.delete_resource_url(db, url)
                        stats.not_found += 1
                        log(f"  Missing resource removed from cache refs: {page_title}")
                        continue
                    stats.errors += 1
                    log(f"  Download failed for {page_title}: {_short_error(exc)}")
                    continue

                content_type = "application/pdf" if kind == "application/pdf" else "image/*"
                cache.put_resource_blob(db, url, body, content_type)
                stats.resources_downloaded += 1
                stats.bytes_downloaded += len(body)
                log(f"  Cached {kind}: {page_title} ({_format_bytes(len(body))})")

                if kind == "application/pdf" and options.extract_text:
                    try:
                        text = extract_pdf_text(body)
                        cache.put_pdf_text(db, page["id"], url, text)
                        stats.pdf_text_extracted += 1
                    except Exception as exc:
                        stats.errors += 1
                        log(f"  Text extraction failed for {page_title}: {exc}")

    return stats


def _extract_existing_pdf_text(db, page_id: str, url: str, stats: WarmCacheStats, log: Callable[[str], None]) -> None:
    blob = cache.get_resource_blob(db, url)
    if not blob:
        return
    try:
        text = extract_pdf_text(blob["body"])
        cache.put_pdf_text(db, page_id, url, text)
        stats.pdf_text_extracted += 1
        log("  Extracted text from cached PDF")
    except Exception as exc:
        stats.errors += 1
        log(f"  Text extraction failed from cached PDF: {exc}")


def _sleep(options: WarmCacheOptions) -> None:
    if options.delay_seconds > 0:
        time.sleep(options.delay_seconds)


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _is_graph_not_found(exc: RuntimeError) -> bool:
    message = str(exc)
    return "HTTP 404" in message or "'code': '20102'" in message or '"code": "20102"' in message


def _short_error(exc: RuntimeError) -> str:
    message = str(exc)
    return message[:500] + ("..." if len(message) > 500 else "")

