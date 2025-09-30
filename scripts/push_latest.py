#!/usr/bin/env python3
import os
import json
import time
import urllib.request

NOTION_TOKEN = os.environ["NOTION_API_TOKEN"]
LATEST_DB_ID = os.environ["NOTION_LATEST_DATABASE_ID"]
RATES_URL = os.environ.get("RATES_JSON_URL")
PAGES_DEFAULT = os.environ.get("PAGES_RATES_URL")
RAW_DEFAULT = os.environ.get("RAW_RATES_URL")
FILTER = os.environ.get("CURRENCY_FILTER")  # e.g., "USD,EUR,JPY"

NOTION_VER = "2022-06-28"

def http_json(method, url, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
    req.add_header("Notion-Version", NOTION_VER)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def get_latest_rates():
    # Try resolved URL, then Pages default, then RAW default, with tiny retries.
    candidates = [u for u in [RATES_URL, PAGES_DEFAULT, RAW_DEFAULT] if u]
    last_err = None
    for url in candidates:
        for attempt in range(3):
            try:
                return fetch_json(url)
            except Exception as e:
                last_err = e
                time.sleep(0.5 * (attempt + 1))
    raise last_err

def find_row_by_currency(code):
    url = f"https://api.notion.com/v1/databases/{LATEST_DB_ID}/query"
    payload = {
        "filter": {"property": "Currency", "select": {"equals": code}},
        "page_size": 1
    }
    res = http_json("POST", url, payload)
    results = res.get("results", [])
    return results[0]["id"] if results else None

def make_props(date_iso, code, aud_per_unit, per_aud):
    return {
        "Name": { "title": [ { "text": { "content": code } } ] },
        "Currency": { "select": { "name": code } },
        "AUD per unit": { "number": aud_per_unit },
        "Per AUD": { "number": per_aud },
        "Updated": { "date": { "start": date_iso } }
    }

def update_page(page_id, props):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": props}
    return http_json("PATCH", url, payload)

def create_page(props):
    url = "https://api.notion.com/v1/pages"
    payload = {"parent": {"database_id": LATEST_DB_ID}, "properties": props}
    return http_json("POST", url, payload)

def main():
    latest = get_latest_rates()
    date_iso = latest.get("date")  # "YYYY-MM-DD" from feed period
    rates = latest.get("rates", [])

    allow = None
    if FILTER:
        allow = {c.strip().upper() for c in FILTER.split(",") if c.strip()}

    pushed = 0
    for r in rates:
        code = (r.get("code") or "").upper()
        if not code:
            continue
        if allow and code not in allow:
            continue

        per_aud = float(r["per_aud"])
        aud_per_unit = r.get("aud_per_unit")
        if aud_per_unit is None and per_aud != 0:
            aud_per_unit = 1.0 / per_aud
        aud_per_unit = float(aud_per_unit)

        props = make_props(date_iso, code, aud_per_unit, per_aud)

        page_id = find_row_by_currency(code)
        if page_id:
            update_page(page_id, props)
        else:
            create_page(props)
        pushed += 1

    print(f"Upserted {pushed} currencies for {date_iso}")

if __name__ == "__main__":
    for k in ("NOTION_API_TOKEN", "NOTION_LATEST_DATABASE_ID"):
        if k not in os.environ:
            raise SystemExit(f"Missing env: {k}")
    main()
