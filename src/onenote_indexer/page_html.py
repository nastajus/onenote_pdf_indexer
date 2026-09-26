from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


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

