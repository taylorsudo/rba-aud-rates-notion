#!/usr/bin/env python3
import os, json, time, urllib.request
from urllib.error import HTTPError, URLError

NOTION_TOKEN = os.environ["NOTION_API_TOKEN"]
LATEST_DB_ID = os.environ["NOTION_LATEST_DATABASE_ID"]
RATES_URL = os.environ.get("RATES_JSON_URL")
PAGES_DEFAULT = os.environ.get("PAGES_RATES_URL")
RAW_DEFAULT = os.environ.get("RAW_RATES_URL")
FILTER = os.environ.get("CURRENCY_FILTER")  # e.g., "USD,EUR,JPY"

NOTION_VER = "2022-06-28"

def _read_json(resp):
    return json.loads(resp.read().decode("utf-8"))

def http_json(method, url, payload=None, extra_headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
    req.add_header("Notion-Version", NOTION_VER)
    req.add_header("Content-Type", "application/json")
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return _read_json(r)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"[Notion] HTTPError {e.code} on {url}")
        print(f"[Notion] Request payload: {json.dumps(payload, ensure_ascii=False)}")
        print(f"[Notion] Response body: {body}")
        raise
    except URLError as e:
        print(f"[Notion] URLError on {url}: {e}")
        raise

def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return _read_json(r)

def get_latest_rates():
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

def get_db_schema(db_id):
    return http_json("GET", f"https://api.notion.com/v1/databases/{db_id}")

def _norm(s):
    return "".join(ch.lower() for ch in s if ch.isalnum())

def resolve_props(schema):
    """
    Detect actual property names by type/name, and return a mapping:
      title_name            -> Title property name
      currency_name         -> 'Currency' Select name if present (else None)
      updated_name          -> Date property for Updated
      aud_per_unit_name     -> Number property that matches 'aud per unit' (case/space-insensitive)
      per_aud_name          -> Number property that matches 'per aud'
    """
    props = schema.get("properties", {})
    title_name = None
    currency_name = None
    updated_name = None
    aud_per_unit_name = None
    per_aud_name = None

    # First pass: find by type and fuzzy name
    for name, meta in props.items():
        ptype = meta.get("type")
        n = _norm(name)
        if ptype == "title":
            title_name = name
        if ptype == "select" and name == "Currency":
            currency_name = name
        if ptype == "date" and (n == "updated" or "updated" in n):
            updated_name = name
        if ptype == "number":
            if n == "audperunit" or "audperunit" in n:
                aud_per_unit_name = name
            elif n == "peraud" or "peraud" in n:
                per_aud_name = name

    # Fallbacks
    if not updated_name:
        date_props = [n for n, m in props.items() if m.get("type") == "date"]
        if len(date_props) == 1:
            updated_name = date_props[0]

    if not title_name:
        raise RuntimeError("No Title property found in the Notion database.")

    if not aud_per_unit_name or not per_aud_name:
        raise RuntimeError(
            "Could not resolve Number fields. Ensure your DB has Number properties "
            "named like 'AUD per unit' and 'Per AUD' (case/spacing doesn't matter)."
        )
    if not updated_name:
        raise RuntimeError("Could not resolve the 'Updated' Date property. Add a Date property named 'Updated'.")

    return {
        "title_name": title_name,
        "currency_name": currency_name,   # may be None
        "updated_name": updated_name,
        "aud_per_unit_name": aud_per_unit_name,
        "per_aud_name": per_aud_name,
    }

def find_row(db_id, title_name, currency_name, code):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    if currency_name:
        payload = {"filter": {"property": currency_name, "select": {"equals": code}}, "page_size": 1}
    else:
        payload = {"filter": {"property": title_name, "title": {"equals": code}}, "page_size": 1}
    res = http_json("POST", url, payload)
    results = res.get("results", [])
    return results[0]["id"] if results else None

def make_props(names, date_iso, code, aud_per_unit, per_aud):
    props = {
        names["title_name"]: {"title": [ {"text": {"content": code}} ]},
        names["aud_per_unit_name"]: {"number": aud_per_unit},
        names["per_aud_name"]: {"number": per_aud},
        names["updated_name"]: {"date": {"start": date_iso}},
    }
    if names["currency_name"]:
        props[names["currency_name"]] = {"select": {"name": code}}
    return props

def update_page(page_id, props):
    return http_json("PATCH", f"https://api.notion.com/v1/pages/{page_id}", {"properties": props})

def create_page(db_id, props):
    payload = {"parent": {"database_id": db_id}, "properties": props}
    return http_json("POST", "https://api.notion.com/v1/pages", payload)

def main():
    latest = get_latest_rates()
    date_iso = latest.get("date")
    rates = latest.get("rates", [])

    allow = None
    if FILTER:
        allow = {c.strip().upper() for c in FILTER.split(",") if c.strip()}

    schema = get_db_schema(LATEST_DB_ID)
    names = resolve_props(schema)

    print(f"[Info] Using props -> Title:{names['title_name']} Currency:{names['currency_name']} "
          f"Updated:{names['updated_name']} AUD per unit:{names['aud_per_unit_name']} Per AUD:{names['per_aud_name']}")

    pushed = 0
    for r in rates:
        code = (r.get("code") or "").upper()
        if not code or (allow and code not in allow):
            continue

        per_aud = float(r["per_aud"])
        apu = r.get("aud_per_unit")
        if apu is None and per_aud != 0:
            apu = 1.0 / per_aud
        apu = float(apu)

        props = make_props(names, date_iso, code, apu, per_aud)
        page_id = find_row(LATEST_DB_ID, names["title_name"], names["currency_name"], code)
        if page_id:
            update_page(page_id, props)
        else:
            create_page(LATEST_DB_ID, props)
        pushed += 1

    print(f"[Done] Upserted {pushed} currencies for {date_iso}")

if __name__ == "__main__":
    for k in ("NOTION_API_TOKEN", "NOTION_LATEST_DATABASE_ID"):
        if k not in os.environ:
            raise SystemExit(f"Missing env: {k}")
    main()
