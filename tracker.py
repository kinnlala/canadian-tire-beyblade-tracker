#!/usr/bin/env python3
"""
Canadian Tire BeyBlade X Starter Pack stock tracker.

Source:
  Canadian Tire's own public web API (PriceAvailability)
Target:
  Canadian Tire product #150-1281-6 / StockTrack SKU 1501281

Behavior:
  - Checks GTA-wide Canadian Tire retail stores plus Peterborough and Barrie.
  - Establishes a baseline separately for each store the first time that store
    is successfully read.
  - Never treats missing/failed data as zero.
  - Creates an alert event only when:
      current - previous >= 3
    (this also covers 0 -> 3+ explicitly).
  - Keeps the most recent known quantity for stores affected by a failed fetch.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

SKU = "1501281"
PRODUCT = "BeyBlade X Starter Pack"
CANADIAN_TIRE_ITEM = "150-1281-6"
BASE_URL = "https://www.canadiantire.ca"
PRICE_AVAILABILITY_PATH = "/api/v1/product/api/v2/product/sku/PriceAvailability"
PCODE = SKU.lower() + "p"

# Public client key embedded in Canadian Tire's web frontend.
# If Canadian Tire rotates it, replace this value.
CT_SUBSCRIPTION_KEY = (
    os.getenv("CT_SUBSCRIPTION_KEY")
    or "c01ef3612328420c9f5cd9277e815a0e"
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
INVENTORY_PATH = DATA_DIR / "inventory.json"
EVENTS_PATH = DATA_DIR / "events.json"
HISTORY_PATH = DATA_DIR / "history.ndjson"

GROUPS: dict[str, list[str]] = {
    "Durham": [
        "0187", "0460", "0075", "0336", "0160",
        "0324", "0170", "0127", "0226",
    ],
    "York Region": [
        "0164", "0087", "0697", "0399", "0653", "0237",
        "0321", "0189", "0069", "0280", "0134",
    ],
    "Toronto West + Central": [
        "0019", "0070", "0119", "0126", "0150",
        "0182", "0214", "0294", "0600", "0621",
    ],
    "Toronto East + North": [
        "0030", "0175", "0192", "0209", "0264",
        "0273", "0427", "0459", "0654",
    ],
    "Peel Region": [
        "0010", "0152", "0169", "0197", "0241",
        "0305", "0346", "0411", "0497", "0675",
    ],
    "Halton Region": [
        "0122", "0140", "0143", "0159", "0412", "0424", "0429",
    ],
    "Peterborough + Barrie": ["0081", "0660", "0006", "0444"],
}

STORES: dict[str, dict[str, str]] = {
    # Durham Region
    "0187": {"name": "Whitby South", "area": "Whitby", "region": "Durham"},
    "0460": {"name": "Whitby North", "area": "Whitby", "region": "Durham"},
    "0075": {"name": "Oshawa Mid", "area": "Oshawa", "region": "Durham"},
    "0336": {"name": "Oshawa North", "area": "Oshawa", "region": "Durham"},
    "0160": {"name": "Ajax", "area": "Ajax", "region": "Durham"},
    "0324": {"name": "Pickering", "area": "Pickering", "region": "Durham"},
    "0170": {"name": "Bowmanville", "area": "Bowmanville", "region": "Durham"},
    "0127": {"name": "Uxbridge", "area": "Uxbridge", "region": "Durham"},
    "0226": {"name": "Port Perry", "area": "Port Perry", "region": "Durham"},

    # York Region
    "0164": {"name": "Markham", "area": "Markham", "region": "York Region"},
    "0087": {"name": "Richmond Hill", "area": "Richmond Hill", "region": "York Region"},
    "0697": {"name": "Richmond Hill North", "area": "Richmond Hill", "region": "York Region"},
    "0399": {"name": "Markham East", "area": "Markham", "region": "York Region"},
    "0653": {"name": "Maple (Vaughan)", "area": "Vaughan", "region": "York Region"},
    "0237": {"name": "Woodbridge", "area": "Woodbridge / Vaughan", "region": "York Region"},
    "0321": {"name": "Dufferin & 407 (Thornhill)", "area": "Thornhill", "region": "York Region"},
    "0189": {"name": "Aurora", "area": "Aurora", "region": "York Region"},
    "0069": {"name": "Newmarket", "area": "Newmarket", "region": "York Region"},
    "0280": {"name": "Stouffville", "area": "Stouffville", "region": "York Region"},
    "0134": {"name": "Keswick", "area": "Keswick", "region": "York Region"},

    # City of Toronto (including Scarborough, North York, Etobicoke)
    "0019": {"name": "Lawrence & Allen Expwy", "area": "Toronto", "region": "Toronto"},
    "0030": {"name": "Warden & Eglinton", "area": "Scarborough", "region": "Toronto"},
    "0070": {"name": "The Queensway", "area": "Etobicoke", "region": "Toronto"},
    "0119": {"name": "Islington & 401", "area": "Etobicoke", "region": "Toronto"},
    "0126": {"name": "Yonge & Steeles", "area": "North York", "region": "Toronto"},
    "0150": {"name": "Yonge & Church", "area": "Toronto", "region": "Toronto"},
    "0175": {"name": "Cedarbrae", "area": "Scarborough", "region": "Toronto"},
    "0182": {"name": "West Toronto (Stockyards)", "area": "Toronto", "region": "Toronto"},
    "0192": {"name": "Sheppard Ave.", "area": "North York", "region": "Toronto"},
    "0209": {"name": "Kingston Rd", "area": "Scarborough", "region": "Toronto"},
    "0214": {"name": "Eglinton & Caledonia", "area": "Toronto", "region": "Toronto"},
    "0264": {"name": "Agincourt", "area": "Scarborough", "region": "Toronto"},
    "0273": {"name": "Main & Danforth", "area": "Toronto", "region": "Toronto"},
    "0294": {"name": "Albion & Kipling", "area": "Etobicoke", "region": "Toronto"},
    "0427": {"name": "Scarborough East (Rylander)", "area": "Scarborough", "region": "Toronto"},
    "0459": {"name": "Eglinton & Laird", "area": "Toronto", "region": "Toronto"},
    "0600": {"name": "Toronto Eaton Centre", "area": "Toronto", "region": "Toronto"},
    "0621": {"name": "Liberty Village", "area": "Toronto", "region": "Toronto"},
    "0654": {"name": "Leslie & Lake Shore", "area": "Toronto", "region": "Toronto"},

    # Peel Region
    "0010": {"name": "Brampton Shoppers World", "area": "Brampton", "region": "Peel Region"},
    "0152": {"name": "Dixie & Dundas", "area": "Mississauga", "region": "Peel Region"},
    "0169": {"name": "Meadowvale", "area": "Mississauga", "region": "Peel Region"},
    "0197": {"name": "Bolton", "area": "Caledon / Bolton", "region": "Peel Region"},
    "0241": {"name": "Southdown", "area": "Mississauga", "region": "Peel Region"},
    "0305": {"name": "Bramalea", "area": "Brampton", "region": "Peel Region"},
    "0346": {"name": "Mavis & Dundas", "area": "Mississauga", "region": "Peel Region"},
    "0411": {"name": "Trinity Common", "area": "Brampton", "region": "Peel Region"},
    "0497": {"name": "Heartland", "area": "Mississauga", "region": "Peel Region"},
    "0675": {"name": "McLaughlin Road", "area": "Brampton", "region": "Peel Region"},

    # Halton Region
    "0122": {"name": "Burlington Fairview", "area": "Burlington", "region": "Halton Region"},
    "0140": {"name": "Milton", "area": "Milton", "region": "Halton Region"},
    "0143": {"name": "Oakville", "area": "Oakville", "region": "Halton Region"},
    "0159": {"name": "Georgetown", "area": "Halton Hills / Georgetown", "region": "Halton Region"},
    "0412": {"name": "Burlington North", "area": "Burlington", "region": "Halton Region"},
    "0424": {"name": "Winston Churchill", "area": "Oakville", "region": "Halton Region"},
    "0429": {"name": "Oakville North", "area": "Oakville", "region": "Halton Region"},

    # Outside GTA retained from the original watch
    "0081": {"name": "Peterborough", "area": "Peterborough", "region": "Peterborough"},
    "0660": {"name": "Peterborough North", "area": "Peterborough", "region": "Peterborough"},
    "0006": {"name": "Barrie", "area": "Barrie", "region": "Barrie"},
    "0444": {"name": "Barrie South", "area": "Barrie", "region": "Barrie"},
}

QTY_KEYS = {
    "quantity", "qty", "stock", "stocklevel", "stock_level",
    "availablequantity", "available_quantity", "availableqty", "inventory",
}
STORE_KEYS = {
    "store", "storeid", "store_id", "storenumber", "store_number",
    "location", "locationid", "location_id",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def normal_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value).strip().lower())


def normal_store_id(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return f"{value:04d}"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):04d}"

    text = str(value).strip()
    if re.fullmatch(r"\d{1,4}", text):
        return text.zfill(4)

    # Common forms such as "Store 0187" or "#187".
    match = re.fullmatch(r"(?:store\s*|#\s*)?(\d{1,4})", text, re.I)
    if match:
        return match.group(1).zfill(4)
    return None


def to_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    text = str(value).strip()
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.0+", text):
        return int(float(text))
    return None


def direct_quantity(node: dict[str, Any]) -> int | None:
    for key, value in node.items():
        if normal_key(key) in QTY_KEYS:
            qty = to_int(value)
            if qty is not None:
                return qty
    return None


def nested_quantity(node: Any, depth: int = 0) -> int | None:
    if depth > 4:
        return None
    if isinstance(node, dict):
        qty = direct_quantity(node)
        if qty is not None:
            return qty
        for value in node.values():
            qty = nested_quantity(value, depth + 1)
            if qty is not None:
                return qty
    elif isinstance(node, list):
        for value in node:
            qty = nested_quantity(value, depth + 1)
            if qty is not None:
                return qty
    return None


def extract_quantities(payload: Any, wanted: set[str]) -> dict[str, int]:
    """
    Tolerates common JSON layouts:
      {"0187": {"Quantity": 4}}
      [{"storeNumber": "0187", "Quantity": 4}]
      {"stores": [{"storeId": 187, "quantity": 4}]}

    Missing stores are deliberately omitted rather than converted to zero.
    """
    found: dict[str, int] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            # Layout where the store number itself is the object key.
            for key, value in node.items():
                sid = normal_store_id(key)
                if sid in wanted:
                    qty = nested_quantity(value)
                    if qty is not None:
                        found[sid] = qty

            qty = direct_quantity(node)

            # Layout with an explicit store-id field in the same object.
            if qty is not None:
                for key, value in node.items():
                    if normal_key(key) in STORE_KEYS:
                        sid = normal_store_id(value)
                        if sid in wanted:
                            found[sid] = qty

                # Fallback for APIs that use an unexpected store-id key but put
                # a recognizable 4-digit store id beside Quantity.
                for value in node.values():
                    sid = normal_store_id(value)
                    if sid in wanted:
                        found.setdefault(sid, qty)

            for value in node.values():
                walk(value)

        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def canadian_tire_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) "
            "Gecko/20100101 Firefox/144.0"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en;q=0.9",
        "ocp-apim-subscription-key": CT_SUBSCRIPTION_KEY,
        "basesiteid": "CTR",
        "bannerid": "CTR",
        "service-client": "ctr/web",
        "service-version": "v1",
        "Referer": "https://www.canadiantire.ca/",
        "Origin": "https://www.canadiantire.ca",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def fetch_store_quantity(store_id: str) -> int:
    """
    Read exact store quantity from Canadian Tire's PriceAvailability API.

    Current Canadian Tire web response:
      skus[0].fulfillment.availability.quantity
    """
    params = urllib.parse.urlencode(
        {
            "lang": "en_CA",
            "storeId": store_id,
            "cache": "true",
            "pCode": PCODE,
        }
    )
    url = f"{BASE_URL}{PRICE_AVAILABILITY_PATH}?{params}"
    body = json.dumps(
        {"skus": [{"code": SKU, "lowStockThreshold": 0}]}
    ).encode("utf-8")

    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers=canadian_tire_headers(),
            )

            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                payload = json.loads(raw.decode(charset, errors="replace"))

            skus = payload.get("skus")
            if not isinstance(skus, list) or not skus:
                raise ValueError("PriceAvailability returned no SKU data")

            sku_data = skus[0]
            if not isinstance(sku_data, dict):
                raise ValueError("PriceAvailability SKU data was malformed")

            fulfillment = sku_data.get("fulfillment")
            if not isinstance(fulfillment, dict):
                raise ValueError("PriceAvailability returned no fulfillment data")

            availability = fulfillment.get("availability")
            if not isinstance(availability, dict):
                raise ValueError("PriceAvailability returned no availability data")

            qty = to_int(availability.get("quantity"))
            if qty is None:
                raise ValueError("PriceAvailability returned no numeric store quantity")

            return qty

        except urllib.error.HTTPError as exc:
            last_error = exc

            if exc.code == 401:
                raise RuntimeError(
                    "Canadian Tire API returned HTTP 401. "
                    "The public API subscription key may have rotated."
                ) from exc

            if attempt < 3:
                time.sleep(2 ** attempt)

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            last_error = exc

            if attempt < 3:
                time.sleep(2 ** attempt)

    assert last_error is not None
    raise RuntimeError(f"store {store_id}: {last_error}")


def fetch_group(group: str, store_ids: list[str]) -> tuple[dict[str, int], str]:
    """
    Query Canadian Tire directly, preserving partial success.

    Missing/failed stores are omitted. main() therefore retains their previous
    known quantity instead of treating a failed request as zero.
    """
    quantities: dict[str, int] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=min(4, len(store_ids))) as executor:
        futures = {
            executor.submit(fetch_store_quantity, store_id): store_id
            for store_id in store_ids
        }

        for future in as_completed(futures):
            store_id = futures[future]
            try:
                quantities[store_id] = future.result()
            except Exception as exc:
                errors.append(f"{store_id}: {exc}")

    if not quantities:
        detail = "; ".join(errors[:5])
        raise RuntimeError(
            f"{group}: all Canadian Tire API requests failed"
            + (f" ({detail})" if detail else "")
        )

    source = (
        f"{BASE_URL}{PRICE_AVAILABILITY_PATH} "
        f"(per-store POST; {len(quantities)}/{len(store_ids)} succeeded)"
    )
    return quantities, source


def initial_inventory() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "sku": SKU,
        "canadian_tire_item": CANADIAN_TIRE_ITEM,
        "product": PRODUCT,
        "source": "Canadian Tire PriceAvailability API",
        "checked_at": None,
        "baseline_complete": False,
        "fresh_store_count": 0,
        "known_store_count": 0,
        "last_run_alert": None,
        "errors": {},
        "stores": {
            sid: {
                **meta,
                "quantity": None,
                "previous_quantity": None,
                "delta": None,
                "fresh": False,
                "last_success_at": None,
            }
            for sid, meta in STORES.items()
        },
    }


def event_id(checked_at: str, changes: list[dict[str, Any]]) -> str:
    canonical = checked_at + "|" + "|".join(
        f"{c['store_id']}:{c['previous']}->{c['current']}" for c in changes
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:10]
    compact = checked_at.replace("-", "").replace(":", "").replace("Z", "Z")
    return f"{compact}-{digest}"


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    checked_at = iso_z(now)

    previous = load_json(INVENTORY_PATH, initial_inventory())
    if previous.get("schema_version") != 1:
        previous = initial_inventory()

    current = initial_inventory()
    current["checked_at"] = checked_at

    # Preserve known state by default. Successful reads overwrite it.
    previous_stores = previous.get("stores", {})
    for sid in STORES:
        old = previous_stores.get(sid, {})
        current["stores"][sid]["quantity"] = old.get("quantity")
        current["stores"][sid]["last_success_at"] = old.get("last_success_at")

    errors: dict[str, str] = {}
    source_urls: dict[str, str] = {}
    read_now: dict[str, int] = {}

    for group, ids in GROUPS.items():
        try:
            quantities, url = fetch_group(group, ids)
            source_urls[group] = url
            read_now.update(quantities)

            missing = [sid for sid in ids if sid not in quantities]
            if missing:
                errors[group] = (
                    "Canadian Tire API did not return quantities for: "
                    + ", ".join(missing)
                )
        except Exception as exc:
            errors[group] = str(exc)

    alerts: list[dict[str, Any]] = []

    for sid, meta in STORES.items():
        old_qty = previous_stores.get(sid, {}).get("quantity")

        if sid in read_now:
            new_qty = read_now[sid]
            store = current["stores"][sid]
            store["previous_quantity"] = old_qty
            store["quantity"] = new_qty
            store["delta"] = None if old_qty is None else new_qty - old_qty
            store["fresh"] = True
            store["last_success_at"] = checked_at

            # First successful observation is a baseline for this store.
            if old_qty is not None:
                delta = new_qty - old_qty
                if delta >= 3 or (old_qty == 0 and new_qty >= 3):
                    alerts.append(
                        {
                            "store_id": sid,
                            "store_name": meta["name"],
                            "area": meta["area"],
                            "region": meta["region"],
                            "previous": old_qty,
                            "current": new_qty,
                            "delta": delta,
                        }
                    )
        else:
            # Failed/missing data retains the latest known quantity and is
            # explicitly marked stale. It is NEVER treated as zero.
            store = current["stores"][sid]
            store["previous_quantity"] = old_qty
            store["delta"] = None
            store["fresh"] = False

    current["errors"] = errors
    current["source_urls"] = source_urls
    current["fresh_store_count"] = sum(
        1 for store in current["stores"].values() if store["fresh"]
    )
    current["known_store_count"] = sum(
        1 for store in current["stores"].values() if store["quantity"] is not None
    )
    current["baseline_complete"] = current["known_store_count"] == len(STORES)

    events = load_json(EVENTS_PATH, {"schema_version": 1, "events": []})
    if not isinstance(events, dict) or not isinstance(events.get("events"), list):
        events = {"schema_version": 1, "events": []}

    if alerts:
        eid = event_id(checked_at, alerts)
        event = {
            "event_id": eid,
            "checked_at": checked_at,
            "sku": SKU,
            "canadian_tire_item": CANADIAN_TIRE_ITEM,
            "product": PRODUCT,
            "changes": alerts,
        }
        current["last_run_alert"] = event
        events["events"].append(event)
        events["events"] = events["events"][-200:]
    else:
        current["last_run_alert"] = None

    write_json(INVENTORY_PATH, current)
    write_json(EVENTS_PATH, events)

    history_record = {
        "checked_at": checked_at,
        "fresh_store_count": current["fresh_store_count"],
        "known_store_count": current["known_store_count"],
        "errors": errors,
        "quantities": {
            sid: current["stores"][sid]["quantity"] for sid in STORES
        },
        "alerts": alerts,
    }
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(history_record, ensure_ascii=False) + "\n")

    print(
        f"Checked {current['fresh_store_count']}/{len(STORES)} stores; "
        f"known={current['known_store_count']}; alerts={len(alerts)}"
    )
    if errors:
        for group, message in errors.items():
            print(f"WARNING {group}: {message}", file=sys.stderr)

    # Do not fail the workflow merely because one endpoint is temporarily down.
    # Fail only when we have never established any store baseline at all.
    if current["known_store_count"] == 0 and current["fresh_store_count"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
