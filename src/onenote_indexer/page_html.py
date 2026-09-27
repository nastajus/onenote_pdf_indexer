from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from html import escape
import math
import re
from urllib.parse import quote


@dataclass
class PageResource:
    tag: str
    kind: str
    url: str
    alt: str | None = None


class OneNoteResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.resources: list[PageResource] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value for key, value in attrs if value}

        if tag == "object":
            url = attr.get("data")
            if url:
                self.resources.append(PageResource(tag=tag, kind=attr.get("type", "object"), url=url))
            return

        if tag == "img":
            full = attr.get("data-fullres-src")
            src = attr.get("src")
            if full:
                self.resources.append(PageResource(tag=tag, kind="image-fullres", url=full, alt=attr.get("alt")))
            elif src:
                self.resources.append(PageResource(tag=tag, kind="image", url=src, alt=attr.get("alt")))
            return

        if tag in {"a", "embed"}:
            url = attr.get("href") or attr.get("src")
            if url:
                self.resources.append(PageResource(tag=tag, kind=tag, url=url))


def extract_resources(html: str) -> list[PageResource]:
    parser = OneNoteResourceParser()
    parser.feed(html)
    return parser.resources


class OneNoteHtmlRenderer(HTMLParser):
    allowed_tags = {
        "a",
        "b",
        "blockquote",
        "br",
        "caption",
        "code",
        "col",
        "colgroup",
        "div",
        "em",
        "font",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "s",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    }
    void_tags = {"br", "hr", "img", "col"}
    transparent_tags = {"html", "head", "body", "meta", "title"}
    drop_tags = {"script", "style", "iframe", "svg", "canvas"}
    allowed_attrs = {
        "align",
        "alt",
        "colspan",
        "height",
        "href",
        "rowspan",
        "span",
        "style",
        "title",
        "valign",
        "width",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0
        self.max_bottom = 0.0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.drop_tags:
            self.drop_depth += 1
            return
        if self.drop_depth or tag in self.transparent_tags:
            return
        if tag == "object":
            self._handle_object(attrs)
            return
        if tag not in self.allowed_tags:
            return

        attr = {key.lower(): value for key, value in attrs if value}
        rendered_attrs: list[str] = []
        if tag == "img":
            url = attr.get("data-fullres-src") or attr.get("src")
            if not url:
                return
            kind = "image-fullres" if attr.get("data-fullres-src") else "image"
            is_absolute = _style_number(attr.get("style", ""), "top") is not None
            classes = ["onenote-resource-image"]
            classes.append("onenote-abs-image" if is_absolute else "onenote-inline-image")
            rendered_attrs.append(f'src="{escape(_resource_url(url, kind), quote=True)}"')
            rendered_attrs.append(f'alt="{escape(attr.get("alt", ""), quote=True)}"')
            rendered_attrs.append('loading="lazy"')
            rendered_attrs.append(f'class="{" ".join(classes)}"')
            self._track_absolute_bottom(attr)

        for key, value in attr.items():
            if key in {"src", "data-fullres-src", "data-src", "class", "onclick", "onerror", "onload"}:
                continue
            if tag == "img" and key == "alt":
                continue
            if key == "href":
                rendered_attrs.append(f'href="{escape(value, quote=True)}"')
                rendered_attrs.append('target="_blank"')
                rendered_attrs.append('rel="noreferrer"')
                continue
            if key in self.allowed_attrs:
                rendered_attrs.append(f'{key}="{escape(value, quote=True)}"')

        suffix = " " + " ".join(rendered_attrs) if rendered_attrs else ""
        self.parts.append(f"<{tag}{suffix}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.drop_tags and self.drop_depth:
            self.drop_depth -= 1
            return
        if self.drop_depth or tag in self.transparent_tags or tag in self.void_tags:
            return
        if tag in self.allowed_tags:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            cleaned = data.replace("\ufffc", "")
            if cleaned:
                self.parts.append(escape(cleaned))

    def handle_entityref(self, name: str) -> None:
        if not self.drop_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.drop_depth:
            self.parts.append(f"&#{name};")

    def _handle_object(self, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value for key, value in attrs if value}
        url = attr.get("data")
        kind = attr.get("type", "object")
        if not url:
            return
        if "pdf" in kind.lower():
            return
        label = "Embedded PDF" if "pdf" in kind else "Embedded resource"
        self.parts.append(
            '<div class="embedded-object">'
            f'<strong>{escape(label)}</strong>'
            f'<a href="{escape(_resource_url(url, kind), quote=True)}" target="_blank" rel="noreferrer">Open resource</a>'
            "</div>"
        )

    def _track_absolute_bottom(self, attr: dict[str, str]) -> None:
        top = _style_number(attr.get("style", ""), "top")
        if top is None:
            return
        height = _number(attr.get("height")) or 0
        self.max_bottom = max(self.max_bottom, top + height)


def render_onenote_html(html: str) -> str:
    parser = OneNoteHtmlRenderer()
    parser.feed(html)
    rendered = "".join(parser.parts)
    if parser.max_bottom:
        height = math.ceil(parser.max_bottom + 64)
        rendered += f'<div class="onenote-page-spacer" style="height:{height}px"></div>'
    return rendered


def _resource_url(url: str, kind: str) -> str:
    return f"/api/resource?resource_url={quote(url, safe='')}&kind={quote(kind, safe='')}"


def _style_number(style: str, name: str) -> float | None:
    match = re.search(rf"(?:^|;)\s*{re.escape(name)}\s*:\s*(-?\d+(?:\.\d+)?)px?", style, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else None
