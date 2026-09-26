from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
DATA_DIR = PROJECT_ROOT / "data"
TOKEN_CACHE_PATH = DATA_DIR / "token_cache.bin"


@dataclass(frozen=True)
class AppConfig:
    client_id: str
    tenant_id: str
    authority: str
    scopes: list[str]


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    return AppConfig(
        client_id=raw["client_id"],
        tenant_id=raw["tenant_id"],
        authority=raw.get("authority", "https://login.microsoftonline.com/consumers"),
        scopes=list(raw.get("scopes", ["User.Read", "Notes.Read", "offline_access"])),
    )

