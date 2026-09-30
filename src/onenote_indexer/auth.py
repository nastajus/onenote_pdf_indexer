from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import msal

from .config import AppConfig, TOKEN_CACHE_PATH


def _load_cache(cache_path: Path = TOKEN_CACHE_PATH) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))
    return cache


def _save_cache(cache: msal.SerializableTokenCache, cache_path: Path = TOKEN_CACHE_PATH) -> None:
    if cache.has_state_changed:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(cache.serialize(), encoding="utf-8")


def _raise_auth_error(result: dict[str, Any]) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True)
    raise RuntimeError(f"Microsoft sign-in did not return an access token:\n{payload}")


def get_access_token(
    config: AppConfig,
    *,
    force_interactive: bool = False,
    device_code: bool = False,
    login_hint: str | None = None,
) -> str:
    cache = _load_cache()
    runtime_scopes = [
        scope
        for scope in config.scopes
        if scope not in {"offline_access", "openid", "profile"}
    ]
    app = msal.PublicClientApplication(
        client_id=config.client_id,
        authority=config.authority,
        token_cache=cache,
    )

    result: dict[str, Any] | None = None
    accounts = app.get_accounts()
    if accounts and not force_interactive:
        result = app.acquire_token_silent(runtime_scopes, account=accounts[0])

    if not result and device_code:
        flow = app.initiate_device_flow(scopes=runtime_scopes)
        if "user_code" not in flow:
            _raise_auth_error(flow)
        print(flow["message"], flush=True)
        result = app.acquire_token_by_device_flow(flow)

    if not result:
        interactive_options: dict[str, Any] = {}
        if force_interactive:
            interactive_options["prompt"] = "select_account"
        if login_hint:
            interactive_options["login_hint"] = login_hint
        result = app.acquire_token_interactive(scopes=runtime_scopes, **interactive_options)

    _save_cache(cache)

    if "access_token" not in result:
        _raise_auth_error(result)

    return str(result["access_token"])
