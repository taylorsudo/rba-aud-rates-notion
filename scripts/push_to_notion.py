#!/usr/bin/env python3
"""
Push AUD exchange rates from rba-aud-rates's JSON into a Notion database.

- No third-party dependencies (urllib, json only).
- Default filter: USD only (CURRENCY_FILTER=USD).
- Upsert key: (Date, Currency).
- Name property: "YYYY-MM-DD <CUR>→AUD" (e.g., "2025-09-29 USD→AUD").
"""

import os, sys, json, time, urllib.request, urllib.error

NOTION_TOKEN = os.environ.get("NOTION_API_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
RATES_URL = os.environ.get("RATES_JSON_URL")
FILTER = os.environ.get("CURRENCY_FILTER", "USD")  # e.g. "USD,EUR,JPY"

NOTION_VER = "2022-06-28"  # stable API version string

def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)

def http_json(method, url, payload=None, headers=None, retries=3, timeout=30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    for attempt in range(1, retries+1):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * attempt)
                continue
            die(f"[HTTPError {e.code}] {body}")
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(1.5 * attempt)
                continue
            die(f"[URLError] {e}")

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VER
    }

def get_latest_rates(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def find_page(date_iso, currency_code):
    """Query database for an existing page by (Date, Currency)."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "Date", "date": {"equals": date_iso}},
                {"property": "Currency", "select": {"equals": currency_code}}
            ]
        },
        "page_size": 1
    }
    res = http_json("POST", url, payload, headers=notion_headers())
    results = res.get("results", [])
    return results[0]["id"] if results else None

def update_page(page_id, props):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": props}
    return http_json("PATCH", url, payload, headers=notion_headers())

def create_page(props):
    url = "https://api.notion.com/v1/pages"
    payload = {"parent": {"database_id": DATABASE_ID}, "properties": props}
    return http_json("POST", url, payload, headers=notion_headers())

def make_props(date_iso, code, aud_per_unit, per_aud):
    """Map one rate row to Notion properties, including Name (Title)."""
    name = f"{date_iso} {code}→AUD"
    return {
        "Name": { "title": [ { "text": { "content": name } } ] },
        "Date": { "date": { "start": date_iso } },
        "Currency": { "select": { "name": code } },
        "AUD per unit": { "number": aud_per_unit },
        "Per AUD": { "number": per_aud }
    }

def main():
    if not NOTION_TOKEN: die("Missing env NOTION_API_TOKEN")
    if not DATABASE_ID: die("Missing env NOTION_DATABASE_ID")
    if not RATES_URL: die("Missing env RATES_JSON_URL (or repository_dispatch payload)")

    latest = get_latest_rates(RATES_URL)
    date_iso = latest.get("date")
    rates = latest.get("rates", [])
    if not date_iso or not rates:
        die("Latest rates JSON missing 'date' or 'rates'.")

    allow = {c.strip().upper() for c in FILTER.split(",") if c.strip()}
    pushed = 0

    for r in rates:
        code = (r.get("code") or "").upper()
        if allow and code not in allow:
            continue

        # We expect Repo A: per_aud = target per 1 AUD; aud_per_unit = 1 / per_aud
        try:
            per_aud = float(r["per_aud"])
            aud_per_unit = float(r["aud_per_unit"]) if r.get("aud_per_unit") is not None else None
        except Exception:
            continue

        if aud_per_unit is None:
            continue

        props = make_props(date_iso, code, aud_per_unit, per_aud)

        page_id = find_page(date_iso, code)
        if page_id:
            update_page(page_id, props)
        else:
            create_page(props)
        pushed += 1

    print(f"Pushed {pushed} row(s) for {date_iso} from {RATES_URL}")

if __name__ == "__main__":
    main()
