import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import requests

BASE = "https://www.bukoli.com"
SERPAPI_URL = "https://serpapi.com/search.json"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.bukoli.com/",
})

_cities_cache = None

HELP = """\
Bukoli points:
  points city=Ankara
  points city=7
  points county=72
  points                    (all points; very large — use limit=20)
  point poi=14342           (full detail for one point)

Google phone lookup (SerpAPI — set SERPAPI_KEY or .env):
  phone poi=16437
  phone poi=16437 city=Ankara
  phones city=Ankara limit=5
  phones county=72 limit=10 delay=1.5 out=phones.json

Address hierarchy (forms only):
  city
  county city=Ankara
  district county=66
  neighborhood district=198

Other:
  help
  quit

Notes:
  - Use key=value pairs after the command name (spaces, not dashes).
  - city= accepts a numeric id or a city name (e.g. Ankara -> id 7).
  - points lists Bukoli noktaları; county= filters by ilçe id from 'county' command.
  - phone/phones search Google Maps via SerpAPI; each lookup uses 1 API credit.
  - Optional limit=50 on points/phones (default 50 for points, 10 for phones).
"""


def load_env_file():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get_serpapi_key():
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        print("Missing SERPAPI_KEY.")
        print("  PowerShell: $env:SERPAPI_KEY='your-key'")
        print("  Or create a .env file next to bukoli_cli.py (see .env.example)")
        return None
    return key


def get_cities():
    global _cities_cache
    if _cities_cache is None:
        r = session.get(f"{BASE}/ajax/city", timeout=20)
        r.raise_for_status()
        _cities_cache = r.json()
    return _cities_cache


def resolve_city(value):
    if str(value).isdigit():
        return int(value)

    key = value.strip().upper()
    for city in get_cities():
        if city["name"] == key:
            return city["id"]

    matches = [city for city in get_cities() if key in city["name"]]
    if len(matches) == 1:
        return matches[0]["id"]
    if matches:
        print("Ambiguous city:", ", ".join(city["name"] for city in matches))
    else:
        print("Unknown city:", value)
    return None


def city_label(value):
    city_id = resolve_city(value)
    if city_id is None:
        return None
    for city in get_cities():
        if city["id"] == city_id:
            return city["name"].title()
    return None


def fetch(path, params=None, timeout=20, quiet=False):
    url = BASE + path
    r = session.get(url, params=params or {}, timeout=timeout)
    if not quiet:
        print("\nURL:", r.url)
        print("STATUS:", r.status_code)
        print("CONTENT-TYPE:", r.headers.get("content-type"))
        print()
    r.raise_for_status()
    return r.json()


def fetch_poi(poi_id):
    return fetch("/ajax/poi-detail", {"poi": poi_id}, quiet=True)


def call(path, params=None):
    try:
        data = fetch(path, params)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"Request failed: {exc}")


def print_points(data, limit=50):
    total = len(data)
    print(f"Found {total} Bukoli point(s)")
    for poi in data[:limit]:
        print(f"  [{poi['id']}] {poi['name']}  ({poi['lat']}, {poi['lng']})")
    if total > limit:
        print(f"  ... and {total - limit} more (use limit= or point poi=<id>)")


def normalize_name(value):
    value = value.casefold()
    value = value.replace("i̇", "i")
    return re.sub(r"\s+", " ", value).strip()


def name_score(left, right):
    return SequenceMatcher(None, normalize_name(left), normalize_name(right)).ratio()


def pick_maps_match(poi_name, results):
    if not results:
        return None

    ranked = sorted(
        results,
        key=lambda item: (
            1 if item.get("phone") else 0,
            name_score(poi_name, item.get("title", "")),
        ),
        reverse=True,
    )
    best = ranked[0]
    best["match_score"] = round(name_score(poi_name, best.get("title", "")), 2)
    return best


def lookup_phone_on_maps(poi_name, lat, lng, city_name=None):
    api_key = get_serpapi_key()
    if not api_key:
        return None

    query = poi_name
    if city_name:
        query = f"{poi_name} {city_name}"

    params = {
        "engine": "google_maps",
        "q": query,
        "ll": f"@{lat},{lng},17z",
        "type": "search",
        "hl": "tr",
        "api_key": api_key,
    }

    r = requests.get(SERPAPI_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"])

    match = pick_maps_match(poi_name, data.get("local_results", []))
    if not match:
        return {
            "query": query,
            "phone": None,
            "google_title": None,
            "address": None,
            "website": None,
            "match_score": 0,
            "status": "not_found",
        }

    return {
        "query": query,
        "phone": match.get("phone"),
        "google_title": match.get("title"),
        "address": match.get("address"),
        "website": match.get("website"),
        "match_score": match.get("match_score", 0),
        "status": "ok" if match.get("phone") else "no_phone",
    }


def print_phone_lookup(poi, lookup):
    print(f"[{poi['id']}] {poi['name']}")
    print(f"  Bukoli: ({poi['lat']}, {poi['lng']})")
    print(f"  Google query: {lookup['query']}")
    if lookup.get("google_title"):
        print(f"  Google match: {lookup['google_title']} (score {lookup['match_score']})")
    if lookup.get("address"):
        print(f"  Address: {lookup['address']}")
    if lookup.get("phone"):
        print(f"  Phone: {lookup['phone']}")
    else:
        print("  Phone: not found")
    if lookup.get("website"):
        print(f"  Website: {lookup['website']}")


def run_phone_lookup(poi_id, city_name=None):
    poi = fetch_poi(poi_id)
    lookup = lookup_phone_on_maps(poi["name"], poi["lat"], poi["lng"], city_name=city_name)
    if lookup is None:
        return None
    print_phone_lookup(poi, lookup)
    return {"poi": poi, "lookup": lookup}


def run_phones_batch(params):
    limit = int(params.pop("limit", 10))
    delay = float(params.pop("delay", 1.5))
    out_file = params.pop("out", None)
    city_name = None

    if "city" in params:
        city_name = city_label(params["city"])
        if city_name is None:
            return
        city_id = resolve_city(params["city"])
        pois = fetch("/ajax/pois-by-city", {"city": city_id}, timeout=60, quiet=True)
    elif "county" in params:
        pois = fetch("/ajax/pois-by-county", {"county": params["county"]}, timeout=60, quiet=True)
    else:
        print("Missing filter: city=<name|id> or county=<id>")
        return

    selected = pois[:limit]
    print(f"Looking up phones for {len(selected)} / {len(pois)} Bukoli point(s)...")
    results = []

    for index, poi in enumerate(selected, start=1):
        print(f"\n--- {index}/{len(selected)} ---")
        try:
            lookup = lookup_phone_on_maps(
                poi["name"],
                poi["lat"],
                poi["lng"],
                city_name=city_name,
            )
            if lookup is None:
                return
            print_phone_lookup(poi, lookup)
            results.append({
                "id": poi["id"],
                "name": poi["name"],
                "lat": poi["lat"],
                "lng": poi["lng"],
                **lookup,
            })
        except Exception as exc:
            print(f"[{poi['id']}] {poi['name']}")
            print(f"  Lookup failed: {exc}")
            results.append({
                "id": poi["id"],
                "name": poi["name"],
                "lat": poi["lat"],
                "lng": poi["lng"],
                "status": "error",
                "error": str(exc),
            })

        if index < len(selected):
            time.sleep(delay)

    found = sum(1 for item in results if item.get("phone"))
    print(f"\nDone. Phones found for {found}/{len(results)} point(s).")

    if out_file:
        with open(out_file, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2)
        print(f"Saved: {out_file}")


def parse_params(parts):
    params = {}
    for part in parts:
        if "=" not in part:
            print(f"Ignored token (expected key=value): {part}")
            continue
        key, value = part.split("=", 1)
        params[key] = value
    return params


def main():
    load_env_file()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("Bukoli AJAX CLI")
    print(HELP)

    while True:
        cmd = input("\nbukoli> ").strip()
        if not cmd:
            continue
        if cmd in ("q", "quit", "exit"):
            break
        if cmd == "help":
            print(HELP)
            continue

        parts = cmd.split()
        name = parts[0]
        params = parse_params(parts[1:])

        if name == "city":
            call("/ajax/city")
        elif name == "county":
            if "city" not in params:
                print("Missing parameter: city=<id or name>")
                continue
            city_id = resolve_city(params["city"])
            if city_id is None:
                continue
            call("/ajax/county", {"city": city_id})
        elif name == "district":
            if "county" not in params:
                print("Missing parameter: county=<id>")
                continue
            call("/ajax/district", {"county": params["county"]})
        elif name == "neighborhood":
            if "district" not in params:
                print("Missing parameter: district=<id>")
                continue
            call("/ajax/neighborhood", {"district": params["district"]})
        elif name == "points":
            limit = int(params.pop("limit", 50))
            try:
                if "city" in params:
                    city_id = resolve_city(params["city"])
                    if city_id is None:
                        continue
                    data = fetch("/ajax/pois-by-city", {"city": city_id}, timeout=60)
                elif "county" in params:
                    data = fetch("/ajax/pois-by-county", {"county": params["county"]}, timeout=60)
                else:
                    data = fetch("/ajax/all-pois", timeout=120)
                print_points(data, limit=limit)
            except Exception as exc:
                print(f"Request failed: {exc}")
        elif name in ("point", "poi"):
            if "poi" not in params:
                print("Missing parameter: poi=<id>")
                continue
            call("/ajax/poi-detail", {"poi": params["poi"]})
        elif name == "phone":
            if "poi" not in params:
                print("Missing parameter: poi=<id>")
                continue
            city_name = city_label(params["city"]) if "city" in params else None
            try:
                run_phone_lookup(params["poi"], city_name=city_name)
            except Exception as exc:
                print(f"Lookup failed: {exc}")
        elif name == "phones":
            try:
                run_phones_batch(params)
            except Exception as exc:
                print(f"Batch lookup failed: {exc}")
        else:
            print("Unknown command. Type 'help' for usage.")


if __name__ == "__main__":
    main()
