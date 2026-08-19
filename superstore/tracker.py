#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

from auth import PcidAuthError, TokenManager

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "data"
STATUS_PATH = DATA_DIR / "status.json"
EVENTS_PATH = DATA_DIR / "events.json"
HISTORY_PATH = DATA_DIR / "history.ndjson"
TOKEN_STATE_PATH = ROOT / ".state" / "pcid_token_state.json"

BASE = "https://api.pcexpress.ca/pcx-bff/api/v1"
API_KEY = "C1xujSegT5j3ap3yexJjqhOfELwGKYvz"

# These transitions are considered a restock/improvement and create an alert event.
QUALIFYING = {
    ("OUT", "LOW"),
    ("OUT", "OK"),
    ("LOW", "OK"),
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_status(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if text in {"OK", "IN_STOCK", "AVAILABLE"}:
        return "OK"
    if "LOW" in text:
        return "LOW"
    if text in {"OUT", "OUT_OF_STOCK", "OOS", "UNAVAILABLE"} or "OUT_OF_STOCK" in text:
        return "OUT"
    return text or None


class PCExpressClient:
    def __init__(self, tokens: TokenManager, banner: str):
        self.tokens = tokens
        self.banner = banner
        self.session = requests.Session()

    def headers(self, access_token: str) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en",
            "Authorization": f"Bearer {access_token}",
            "Business-User-Agent": "PCXWEB",
            "Content-Type": "application/json",
            "Origin": "https://www.realcanadiansuperstore.ca",
            "Referer": "https://www.realcanadiansuperstore.ca/",
            "Site-Banner": self.banner,
            "x-apikey": API_KEY,
            "x-application-type": "Web",
            "x-loblaw-tenant-id": "ONLINE_GROCERIES",
            "baseSiteId": self.banner,
            "is-helios-account": "true",
        }

    def search(self, store_id: str, term: str) -> dict[str, Any]:
        payload = {
            "lang": "en",
            "term": term,
            "storeId": store_id,
            "banner": self.banner,
            "pagination": {"from": 0, "size": 48},
        }

        token = self.tokens.get_access_token()
        response = self.session.post(
            f"{BASE}/products/search",
            headers=self.headers(token),
            json=payload,
            timeout=30,
        )
        if response.status_code == 401:
            token = self.tokens.get_access_token(force=True)
            response = self.session.post(
                f"{BASE}/products/search",
                headers=self.headers(token),
                json=payload,
                timeout=30,
            )

        response.raise_for_status()
        return response.json()


def find_product(results: list[dict[str, Any]], product_code: str) -> dict[str, Any] | None:
    for item in results:
        code = str(item.get("code") or item.get("articleNumber") or "")
        if code == product_code:
            return item
    return None


def initial_state(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "product": config["product"],
        "checked_at": None,
        "known_store_count": 0,
        "fresh_store_count": 0,
        "last_run_alert": None,
        "stores": {
            s["store_id"]: {
                **s,
                "status": None,
                "raw_status": None,
                "previous_status": None,
                "fresh": False,
                "last_success_at": None,
                "last_observation": None,
                "last_error": None,
            }
            for s in config["stores"]
        },
    }


def make_event_id(checked_at: str, changes: list[dict[str, Any]]) -> str:
    canonical = checked_at + "|" + "|".join(
        f"{c['store_id']}:{c['previous']}->{c['current']}" for c in changes
    )
    return checked_at.replace("-", "").replace(":", "") + "-" + hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:10]


def main() -> int:
    config = read_json(CONFIG_PATH, None)
    if not config:
        print("Missing config.json", file=sys.stderr)
        return 2

    product = config["product"]
    previous = read_json(STATUS_PATH, initial_state(config))
    current = initial_state(config)
    checked_at = now_iso()
    current["checked_at"] = checked_at

    # Preserve last known good status by default.
    previous_stores = previous.get("stores", {})
    for sid in current["stores"]:
        old = previous_stores.get(sid, {})
        for field in ("status", "raw_status", "last_success_at"):
            current["stores"][sid][field] = old.get(field)

    try:
        tokens = TokenManager(TOKEN_STATE_PATH)
        client = PCExpressClient(tokens, product["banner"])
    except PcidAuthError as exc:
        print(f"AUTH ERROR: {exc}", file=sys.stderr)
        return 3

    changes: list[dict[str, Any]] = []
    run_errors: dict[str, str] = {}

    for store in config["stores"]:
        sid = store["store_id"]
        old_status = previous_stores.get(sid, {}).get("status")
        entry = current["stores"][sid]
        entry["previous_status"] = old_status

        try:
            payload = client.search(sid, product["search_term"])
            results = payload.get("results", [])
            item = find_product(results, product["code"])

            if item is None:
                # A successful search that doesn't return the product is deliberately
                # not treated as OUT. Keep the last known good status.
                entry["fresh"] = False
                entry["last_observation"] = "NOT_RETURNED"
                entry["last_error"] = None
                run_errors[sid] = "Product not returned by successful search"
            else:
                raw = item.get("stockStatus")
                new_status = normalize_status(raw)

                if new_status is None:
                    entry["fresh"] = False
                    entry["last_observation"] = "NO_STATUS"
                    run_errors[sid] = "Product returned without stockStatus"
                else:
                    entry["status"] = new_status
                    entry["raw_status"] = raw
                    entry["fresh"] = True
                    entry["last_success_at"] = checked_at
                    entry["last_observation"] = new_status
                    entry["last_error"] = None

                    if old_status is not None and (old_status, new_status) in QUALIFYING:
                        changes.append(
                            {
                                "store_id": sid,
                                "store_name": store["name"],
                                "area": store["area"],
                                "region": store["region"],
                                "address": store["address"],
                                "previous": old_status,
                                "current": new_status,
                            }
                        )

        except (requests.RequestException, ValueError, RuntimeError, PcidAuthError) as exc:
            entry["fresh"] = False
            entry["last_observation"] = "ERROR"
            entry["last_error"] = str(exc)[:500]
            run_errors[sid] = str(exc)[:500]

        time.sleep(0.4)

    current["fresh_store_count"] = sum(1 for x in current["stores"].values() if x["fresh"])
    current["known_store_count"] = sum(1 for x in current["stores"].values() if x["status"] is not None)
    current["errors"] = run_errors

    events = read_json(EVENTS_PATH, {"schema_version": 1, "events": []})
    if not isinstance(events, dict) or not isinstance(events.get("events"), list):
        events = {"schema_version": 1, "events": []}

    if changes:
        event = {
            "event_id": make_event_id(checked_at, changes),
            "checked_at": checked_at,
            "product": product,
            "changes": changes,
        }
        current["last_run_alert"] = event
        events["events"].append(event)
        events["events"] = events["events"][-200:]
    else:
        current["last_run_alert"] = None

    write_json(STATUS_PATH, current)
    write_json(EVENTS_PATH, events)

    history = {
        "checked_at": checked_at,
        "fresh_store_count": current["fresh_store_count"],
        "known_store_count": current["known_store_count"],
        "statuses": {sid: x["status"] for sid, x in current["stores"].items()},
        "observations": {sid: x["last_observation"] for sid, x in current["stores"].items()},
        "alerts": changes,
        "errors": run_errors,
    }
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(history, ensure_ascii=False) + "\n")

    print(
        f"Checked {current['fresh_store_count']}/{len(config['stores'])} stores; "
        f"known={current['known_store_count']}; restock events={len(changes)}"
    )

    # Baseline can be partial; only fail if nothing is known and nothing fresh succeeded.
    if current["known_store_count"] == 0 and current["fresh_store_count"] == 0:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
