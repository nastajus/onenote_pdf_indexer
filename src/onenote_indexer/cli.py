from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .auth import get_access_token
from .config import load_config
from .graph import GraphClient
from .page_html import extract_resources


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Connect to OneNote through Microsoft Graph.")
    parser.add_argument(
        "command",
        choices=["auth", "whoami", "notebooks", "sections", "pages", "resources"],
        help="Command to run.",
    )
    parser.add_argument("--page-id", help="OneNote page ID for commands that inspect a single page.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum pages to show for the pages command.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON.")
    parser.add_argument("--force-login", action="store_true", help="Ignore cached tokens and sign in again.")
    parser.add_argument("--device-code", action="store_true", help="Use a device-code login instead of browser callback.")
    args = parser.parse_args()

    config = load_config()
    token = get_access_token(
        config,
        force_interactive=args.force_login or args.command == "auth",
        device_code=args.device_code,
    )

    if args.command == "auth":
        print("Signed in successfully. Token cache saved locally.")
        return

    graph = GraphClient(token)

    if args.command == "whoami":
        print_json_or_table(graph.me(), args.json)
    elif args.command == "notebooks":
        print_json_or_table(graph.notebooks(), args.json, ["displayName", "id", "lastModifiedDateTime"])
    elif args.command == "sections":
        print_json_or_table(graph.sections(), args.json, ["displayName", "id", "lastModifiedDateTime"])
    elif args.command == "pages":
        print_json_or_table(graph.pages(limit=args.limit), args.json, ["_section.displayName", "title", "id", "lastModifiedDateTime"])
    elif args.command == "resources":
        if not args.page_id:
            raise SystemExit("--page-id is required for resources")
        resources = extract_resources(graph.page_content(args.page_id))
        if args.json:
            print(json.dumps([resource.__dict__ for resource in resources], indent=2, ensure_ascii=False))
        else:
            for index, resource in enumerate(resources, start=1):
                print(f"{index}. tag: {resource.tag} | kind: {resource.kind} | alt: {resource.alt} | url: {resource.url}")


def print_json_or_table(payload: Any, raw_json: bool, fields: list[str] | None = None) -> None:
    if raw_json or not isinstance(payload, list):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if fields is None:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    for index, item in enumerate(payload, start=1):
        selected = pick_fields_with_dots(item, fields)
        formatted = " | ".join(f"{key}: {value}" for key, value in selected.items())
        print(f"{index}. {formatted}")


def pick_fields_with_dots(item: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for field in fields:
        current: Any = item
        for part in field.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current is not None:
            selected[field] = current
    return selected
