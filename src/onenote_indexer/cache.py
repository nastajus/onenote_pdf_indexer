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
    try:
        db.execute(
            """
            create virtual table if not exists pdf_pages_fts using fts5(
                page_id unindexed,
                resource_url unindexed,
                pdf_page_number unindexed,
                text
            )
            """
        )
    except sqlite3.OperationalError:
        pass
    db.commit()


def get_collection(db: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = db.execute(f"select data from {table} order by rowid").fetchall()
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
        "select data from pages where section_id = ? order by rowid",
        (section_id,),
    ).fetchall()
    return [json.loads(row["data"]) for row in rows]


def get_page(db: sqlite3.Connection, page_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "select data from pages where id = ?",
        (page_id,),
    ).fetchone()
    return json.loads(row["data"]) if row else None


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
        _replace_pdf_pages_fts(db, page_id, resource_url, data)


def _replace_pdf_pages_fts(db: sqlite3.Connection, page_id: str, resource_url: str, data: dict[str, Any]) -> None:
    try:
        db.execute(
            "delete from pdf_pages_fts where page_id = ? and resource_url = ?",
            (page_id, resource_url),
        )
        db.executemany(
            """
            insert into pdf_pages_fts (page_id, resource_url, pdf_page_number, text)
            values (?, ?, ?, ?)
            """,
            [
                (page_id, resource_url, page.get("page_number"), page.get("text") or "")
                for page in data.get("pages", [])
                if (page.get("text") or "").strip()
            ],
        )
    except sqlite3.OperationalError:
        return


def rebuild_pdf_search_index(db: sqlite3.Connection) -> int:
    try:
        db.execute("delete from pdf_pages_fts")
    except sqlite3.OperationalError:
        return 0

    rows = db.execute("select page_id, resource_url, data from pdf_text").fetchall()
    count = 0
    with db:
        for row in rows:
            data = json.loads(row["data"])
            _replace_pdf_pages_fts(db, row["page_id"], row["resource_url"], data)
            count += len([page for page in data.get("pages", []) if (page.get("text") or "").strip()])
    return count


def search_pdf_text(db: sqlite3.Connection, query: str, *, section_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    match_query = _fts_query(query)
    if not match_query:
        return []

    try:
        sql = """
            select
                f.page_id,
                f.resource_url,
                f.pdf_page_number,
                snippet(pdf_pages_fts, 3, '[', ']', ' ... ', 18) as snippet,
                p.data as page_data
            from pdf_pages_fts f
            left join pages p on p.id = f.page_id
            where f.text match ?
        """
        params: list[Any] = [match_query]
        if section_id:
            sql += " and p.section_id = ?"
            params.append(section_id)
        sql += " limit ?"
        params.append(limit)
        rows = db.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        rows = _search_pdf_text_like(db, query, section_id=section_id, limit=limit)

    results: list[dict[str, Any]] = []
    for row in rows:
        page_data = json.loads(row["page_data"]) if row["page_data"] else {}
        results.append(
            {
                "page_id": row["page_id"],
                "resource_url": row["resource_url"],
                "pdf_page_number": row["pdf_page_number"],
                "snippet": row["snippet"],
                "page": page_data,
            }
        )
    return results


def pdf_search_row_count(db: sqlite3.Connection) -> int:
    try:
        row = db.execute("select count(*) as count from pdf_pages_fts").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row["count"] if row else 0)


def _search_pdf_text_like(db: sqlite3.Connection, query: str, *, section_id: str | None, limit: int) -> list[sqlite3.Row]:
    sql = """
        select
            f.page_id,
            f.resource_url,
            f.pdf_page_number,
            substr(f.text, 1, 500) as snippet,
            p.data as page_data
        from pdf_pages_fts f
        left join pages p on p.id = f.page_id
        where f.text like ?
    """
    params: list[Any] = [f"%{query}%"]
    if section_id:
        sql += " and p.section_id = ?"
        params.append(section_id)
    sql += " limit ?"
    params.append(limit)
    return db.execute(sql, params).fetchall()


def _fts_query(query: str) -> str:
    terms = [term.strip().replace('"', '""') for term in query.split() if term.strip()]
    return " ".join(f'"{term}"' for term in terms)


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
            try:
                db.execute("delete from pdf_pages_fts where resource_url = ?", (url,))
            except sqlite3.OperationalError:
                pass


def delete_resource_url(db: sqlite3.Connection, url: str) -> None:
    with db:
        db.execute("delete from resource_blobs where url = ?", (url,))
        db.execute("delete from pdf_text where resource_url = ?", (url,))
        db.execute("delete from resources where url = ?", (url,))
        try:
            db.execute("delete from pdf_pages_fts where resource_url = ?", (url,))
        except sqlite3.OperationalError:
            pass


def cache_metrics(db: sqlite3.Connection) -> dict[str, Any]:
    row = db.execute(
        """
        select
            (select count(*) from sections) as sections,
            (select count(*) from pages) as pages,
            (select count(*) from resources) as resources,
            (select count(*) from resources where json_extract(data, '$.kind') = 'application/pdf') as pdf_resources,
            (select count(*) from resource_blobs) as blobs,
            (select count(*) from resource_blobs where content_type = 'application/pdf') as pdf_blobs,
            (select coalesce(sum(size), 0) from resource_blobs) as bytes,
            (select count(*) from pdf_text) as pdf_texts
        """
    ).fetchone()
    pdf_resources = int(row["pdf_resources"] or 0)
    pdf_blobs = int(row["pdf_blobs"] or 0)
    percent = round((pdf_blobs / pdf_resources) * 100, 1) if pdf_resources else 0
    remaining = max(pdf_resources - pdf_blobs, 0)
    return {
        "sections": int(row["sections"] or 0),
        "pages": int(row["pages"] or 0),
        "resources": int(row["resources"] or 0),
        "pdf_resources": pdf_resources,
        "pdf_blobs": pdf_blobs,
        "resource_blobs": int(row["blobs"] or 0),
        "bytes": int(row["bytes"] or 0),
        "pdf_texts": int(row["pdf_texts"] or 0),
        "percent": percent,
        "remaining_pdf_resources": remaining,
        "estimated_minutes_1_5s_throttle": round((remaining * 4.0) / 60, 1),
        "estimated_minutes_3s_throttle": round((remaining * 6.0) / 60, 1),
        "scope_note": "This is not the whole OneDrive storage total. It covers original PDF resources discovered from cached OneNote page metadata; printout images, note markup, stale copies, and undiscovered pages can make OneDrive report much more storage.",
    }
