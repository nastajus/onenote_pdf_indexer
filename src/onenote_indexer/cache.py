from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from .config import DATA_DIR


CACHE_PATH = DATA_DIR / "cache.sqlite3"


def connect(path: Path = CACHE_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    _init(db)
    return db


def _init(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        create table if not exists notebooks (
            id text primary key,
            data text not null,
            fetched_at text not null default current_timestamp
        );

        create table if not exists sections (
            id text primary key,
            data text not null,
            fetched_at text not null default current_timestamp
        );

        create table if not exists pages (
            id text primary key,
            section_id text not null,
            data text not null,
            fetched_at text not null default current_timestamp
        );

        create index if not exists pages_section_id_idx on pages(section_id);

        create table if not exists resources (
            page_id text not null,
            url text not null,
            data text not null,
            fetched_at text not null default current_timestamp,
            primary key (page_id, url)
        );

        create table if not exists pdf_text (
            page_id text not null,
            resource_url text not null,
            data text not null,
            fetched_at text not null default current_timestamp,
            primary key (page_id, resource_url)
        );

        create table if not exists resource_blobs (
            url text primary key,
            content_type text,
            size integer not null,
            sha256 text not null,
            body blob not null,
            fetched_at text not null default current_timestamp
        );
        """
    )
    db.commit()


def get_collection(db: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = db.execute(f"select data from {table} order by json_extract(data, '$.displayName'), json_extract(data, '$.title')").fetchall()
    return [json.loads(row["data"]) for row in rows]


def replace_collection(db: sqlite3.Connection, table: str, items: list[dict[str, Any]]) -> None:
    with db:
        db.execute(f"delete from {table}")
        db.executemany(
            f"insert into {table} (id, data) values (?, ?)",
            [(item["id"], json.dumps(item, ensure_ascii=False)) for item in items],
        )


def get_pages(db: sqlite3.Connection, section_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "select data from pages where section_id = ? order by json_extract(data, '$.title')",
        (section_id,),
    ).fetchall()
    return [json.loads(row["data"]) for row in rows]


def replace_pages(db: sqlite3.Connection, section_id: str, pages: list[dict[str, Any]]) -> None:
    with db:
        db.execute("delete from pages where section_id = ?", (section_id,))
        db.executemany(
            "insert into pages (id, section_id, data) values (?, ?, ?)",
            [(page["id"], section_id, json.dumps(page, ensure_ascii=False)) for page in pages],
        )


def get_resources(db: sqlite3.Connection, page_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "select data from resources where page_id = ? order by rowid",
        (page_id,),
    ).fetchall()
    return [json.loads(row["data"]) for row in rows]


def resource_count(db: sqlite3.Connection, page_id: str) -> int:
    row = db.execute(
        "select count(*) as count from resources where page_id = ?",
        (page_id,),
    ).fetchone()
    return int(row["count"] if row else 0)


def replace_resources(db: sqlite3.Connection, page_id: str, resources: list[dict[str, Any]]) -> None:
    with db:
        db.execute("delete from resources where page_id = ?", (page_id,))
        db.executemany(
            "insert into resources (page_id, url, data) values (?, ?, ?)",
            [(page_id, resource["url"], json.dumps(resource, ensure_ascii=False)) for resource in resources],
        )


def get_pdf_text(db: sqlite3.Connection, page_id: str, resource_url: str) -> dict[str, Any] | None:
    row = db.execute(
        "select data from pdf_text where page_id = ? and resource_url = ?",
        (page_id, resource_url),
    ).fetchone()
    return json.loads(row["data"]) if row else None


def has_pdf_text(db: sqlite3.Connection, page_id: str, resource_url: str) -> bool:
    row = db.execute(
        "select 1 from pdf_text where page_id = ? and resource_url = ?",
        (page_id, resource_url),
    ).fetchone()
    return row is not None


def put_pdf_text(db: sqlite3.Connection, page_id: str, resource_url: str, data: dict[str, Any]) -> None:
    with db:
        db.execute(
            """
            insert or replace into pdf_text (page_id, resource_url, data, fetched_at)
            values (?, ?, ?, current_timestamp)
            """,
            (page_id, resource_url, json.dumps(data, ensure_ascii=False)),
        )


def get_resource_blob(db: sqlite3.Connection, url: str) -> dict[str, Any] | None:
    row = db.execute(
        "select url, content_type, size, sha256, body from resource_blobs where url = ?",
        (url,),
    ).fetchone()
    if not row:
        return None
    return {
        "url": row["url"],
        "content_type": row["content_type"],
        "size": row["size"],
        "sha256": row["sha256"],
        "body": row["body"],
    }


def get_resource_blob_info(db: sqlite3.Connection, url: str) -> dict[str, Any] | None:
    row = db.execute(
        "select url, content_type, size, sha256 from resource_blobs where url = ?",
        (url,),
    ).fetchone()
    if not row:
        return None
    return {
        "url": row["url"],
        "content_type": row["content_type"],
        "size": row["size"],
        "sha256": row["sha256"],
    }


def has_resource_blob(db: sqlite3.Connection, url: str) -> bool:
    return get_resource_blob_info(db, url) is not None


def total_resource_blob_bytes(db: sqlite3.Connection) -> int:
    row = db.execute("select coalesce(sum(size), 0) as size from resource_blobs").fetchone()
    return int(row["size"] if row else 0)


def put_resource_blob(db: sqlite3.Connection, url: str, body: bytes, content_type: str | None = None) -> dict[str, Any]:
    digest = hashlib.sha256(body).hexdigest()
    with db:
        db.execute(
            """
            insert or replace into resource_blobs (url, content_type, size, sha256, body, fetched_at)
            values (?, ?, ?, ?, ?, current_timestamp)
            """,
            (url, content_type, len(body), digest, body),
        )
    return {
        "url": url,
        "content_type": content_type,
        "size": len(body),
        "sha256": digest,
        "body": body,
    }


def delete_missing_resource_data(db: sqlite3.Connection, page_id: str, valid_urls: set[str]) -> None:
    rows = db.execute("select url from resources where page_id = ?", (page_id,)).fetchall()
    stale_urls = {row["url"] for row in rows if row["url"] not in valid_urls}
    if not stale_urls:
        return

    with db:
        for url in stale_urls:
            db.execute("delete from resource_blobs where url = ?", (url,))
            db.execute("delete from pdf_text where resource_url = ?", (url,))


def delete_resource_url(db: sqlite3.Connection, url: str) -> None:
    with db:
        db.execute("delete from resource_blobs where url = ?", (url,))
        db.execute("delete from pdf_text where resource_url = ?", (url,))
        db.execute("delete from resources where url = ?", (url,))
