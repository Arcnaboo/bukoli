import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

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

_cities_cache: list[dict[str, Any]] | None = None


class BukoliError(Exception):
    pass


class CityNotFoundError(BukoliError):
    pass


class AmbiguousCityError(BukoliError):
    def __init__(self, matches: list[str]):
        self.matches = matches
        super().__init__(f"Ambiguous city: {', '.join(matches)}")


class SerpApiKeyMissingError(BukoliError):
    pass


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get_serpapi_key() -> str:
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        raise SerpApiKeyMissingError(
            "SERPAPI_KEY is not set. Add it to Render environment variables or a local .env file."
        )
    return key


def get_cities() -> list[dict[str, Any]]:
    global _cities_cache
    if _cities_cache is None:
        r = session.get(f"{BASE}/ajax/city", timeout=20)
        r.raise_for_status()
        _cities_cache = r.json()
    return _cities_cache


def resolve_city(value: str | int) -> int:
    if str(value).isdigit():
        return int(value)

    key = str(value).strip().upper()
    for city in get_cities():
        if city["name"] == key:
            return city["id"]

    matches = [city for city in get_cities() if key in city["name"]]
    if len(matches) == 1:
        return matches[0]["id"]
    if matches:
        raise AmbiguousCityError([city["name"] for city in matches])
    raise CityNotFoundError(f"Unknown city: {value}")


def city_label(value: str | int) -> str:
    city_id = resolve_city(value)
    for city in get_cities():
        if city["id"] == city_id:
            return city["name"].title()
    raise CityNotFoundError(f"Unknown city id: {city_id}")


def fetch(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    r = session.get(f"{BASE}{path}", params=params or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def get_counties(city: str | int) -> list[dict[str, Any]]:
    city_id = resolve_city(city)
    return fetch("/ajax/county", {"city": city_id})


def get_districts(county_id: int) -> list[dict[str, Any]]:
    return fetch("/ajax/district", {"county": county_id})


def get_neighborhoods(district_id: int) -> list[dict[str, Any]]:
    return fetch("/ajax/neighborhood", {"district": district_id})


def get_poi(poi_id: int) -> dict[str, Any]:
    return fetch("/ajax/poi-detail", {"poi": poi_id})


def enrich_points_with_phones(
    points: list[dict[str, Any]],
    *,
    city_name: str | None = None,
    delay: float = 1.5,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []

    for index, poi in enumerate(points, start=1):
        try:
            lookup = lookup_phone_on_maps(
                poi["name"],
                poi["lat"],
                poi["lng"],
                city_name=city_name,
            )
            enriched.append({
                "id": poi["id"],
                "name": poi["name"],
                "lat": poi["lat"],
                "lng": poi["lng"],
                "phone": lookup.get("phone"),
                "google_title": lookup.get("google_title"),
                "match_score": lookup.get("match_score"),
                "phone_status": lookup.get("status"),
            })
        except Exception as exc:
            enriched.append({
                "id": poi["id"],
                "name": poi["name"],
                "lat": poi["lat"],
                "lng": poi["lng"],
                "phone": None,
                "google_title": None,
                "match_score": None,
                "phone_status": "error",
                "phone_error": str(exc),
            })

        if index < len(points):
            time.sleep(delay)

    return enriched


def get_points(
    *,
    city: str | int | None = None,
    county_id: int | None = None,
    limit: int = 50,
    include_phone: bool = False,
    delay: float = 1.5,
) -> dict[str, Any]:
    if include_phone and limit > 25:
        raise ValueError("limit must be <= 25 when include_phone=true")

    if city is not None:
        city_id = resolve_city(city)
        data = fetch("/ajax/pois-by-city", {"city": city_id}, timeout=60)
    elif county_id is not None:
        data = fetch("/ajax/pois-by-county", {"county": county_id}, timeout=60)
    else:
        data = fetch("/ajax/all-pois", timeout=120)

    total = len(data)
    points = data[:limit]
    phones_found = None

    if include_phone:
        city_name = city_label(city) if city is not None else None
        points = enrich_points_with_phones(points, city_name=city_name, delay=delay)
        phones_found = sum(1 for point in points if point.get("phone"))

    return {
        "total": total,
        "limit": limit,
        "count": len(points),
        "phones_found": phones_found,
        "points": points,
    }


def normalize_name(value: str) -> str:
    value = value.casefold()
    value = value.replace("i̇", "i")
    return re.sub(r"\s+", " ", value).strip()


def name_score(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_name(left), normalize_name(right)).ratio()


def pick_maps_match(poi_name: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
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


def lookup_phone_on_maps(
    poi_name: str,
    lat: str | float,
    lng: str | float,
    city_name: str | None = None,
) -> dict[str, Any]:
    api_key = get_serpapi_key()
    query = f"{poi_name} {city_name}" if city_name else poi_name

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


def lookup_poi_phone(poi_id: int, city: str | int | None = None) -> dict[str, Any]:
    poi = get_poi(poi_id)
    city_name = city_label(city) if city is not None else None
    lookup = lookup_phone_on_maps(poi["name"], poi["lat"], poi["lng"], city_name=city_name)
    return {"poi": poi, "lookup": lookup}


def lookup_phones_batch(
    *,
    city: str | int | None = None,
    county_id: int | None = None,
    limit: int = 10,
    delay: float = 1.5,
) -> dict[str, Any]:
    if limit < 1 or limit > 25:
        raise ValueError("limit must be between 1 and 25")

    city_name = None
    if city is not None:
        city_name = city_label(city)
        city_id = resolve_city(city)
        pois = fetch("/ajax/pois-by-city", {"city": city_id}, timeout=60)
    elif county_id is not None:
        pois = fetch("/ajax/pois-by-county", {"county": county_id}, timeout=60)
    else:
        raise ValueError("Provide city or county_id")

    selected = pois[:limit]
    enriched = enrich_points_with_phones(selected, city_name=city_name, delay=delay)
    results = []
    for point in enriched:
        item = {
            "id": point["id"],
            "name": point["name"],
            "lat": point["lat"],
            "lng": point["lng"],
            "phone": point.get("phone"),
            "google_title": point.get("google_title"),
            "match_score": point.get("match_score"),
            "status": point.get("phone_status", "error"),
        }
        if point.get("phone_error"):
            item["error"] = point["phone_error"]
        results.append(item)

    found = sum(1 for item in results if item.get("phone"))
    return {
        "requested": len(selected),
        "total_available": len(pois),
        "phones_found": found,
        "results": results,
    }
