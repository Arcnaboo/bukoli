import json
import sys

import bukoli_service as svc

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
  - HTTP API: run `uvicorn main:app --reload` then open http://127.0.0.1:8000/docs
"""


def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def print_points(data, limit=50) -> None:
    total = data["total"]
    print(f"Found {total} Bukoli point(s)")
    for poi in data["points"]:
        print(f"  [{poi['id']}] {poi['name']}  ({poi['lat']}, {poi['lng']})")
    if total > limit:
        print(f"  ... and {total - limit} more (use limit= or point poi=<id>)")


def print_phone_lookup(poi, lookup) -> None:
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


def handle_city_error(exc: Exception) -> bool:
    if isinstance(exc, svc.AmbiguousCityError):
        print(str(exc))
        return True
    if isinstance(exc, svc.CityNotFoundError):
        print(str(exc))
        return True
    return False


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
    svc.load_env_file()
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

        try:
            if name == "city":
                print_json(svc.get_cities())
            elif name == "county":
                if "city" not in params:
                    print("Missing parameter: city=<id or name>")
                    continue
                print_json(svc.get_counties(params["city"]))
            elif name == "district":
                if "county" not in params:
                    print("Missing parameter: county=<id>")
                    continue
                print_json(svc.get_districts(int(params["county"])))
            elif name == "neighborhood":
                if "district" not in params:
                    print("Missing parameter: district=<id>")
                    continue
                print_json(svc.get_neighborhoods(int(params["district"])))
            elif name == "points":
                limit = int(params.pop("limit", 50))
                city = params.get("city")
                county_id = int(params["county"]) if "county" in params else None
                data = svc.get_points(city=city, county_id=county_id, limit=limit)
                print_points(data, limit=limit)
            elif name in ("point", "poi"):
                if "poi" not in params:
                    print("Missing parameter: poi=<id>")
                    continue
                print_json(svc.get_poi(int(params["poi"])))
            elif name == "phone":
                if "poi" not in params:
                    print("Missing parameter: poi=<id>")
                    continue
                city = params.get("city")
                result = svc.lookup_poi_phone(int(params["poi"]), city=city)
                print_phone_lookup(result["poi"], result["lookup"])
            elif name == "phones":
                limit = int(params.pop("limit", 10))
                delay = float(params.pop("delay", 1.5))
                out_file = params.pop("out", None)
                city = params.get("city")
                county_id = int(params["county"]) if "county" in params else None
                result = svc.lookup_phones_batch(
                    city=city,
                    county_id=county_id,
                    limit=limit,
                    delay=delay,
                )
                for item in result["results"]:
                    print_phone_lookup(
                        {"id": item["id"], "name": item["name"], "lat": item["lat"], "lng": item["lng"]},
                        item,
                    )
                    print()
                print(
                    f"Done. Phones found for {result['phones_found']}/{result['requested']} point(s)."
                )
                if out_file:
                    with open(out_file, "w", encoding="utf-8") as handle:
                        json.dump(result["results"], handle, ensure_ascii=False, indent=2)
                    print(f"Saved: {out_file}")
            else:
                print("Unknown command. Type 'help' for usage.")
        except svc.SerpApiKeyMissingError as exc:
            print(exc)
        except (svc.AmbiguousCityError, svc.CityNotFoundError, ValueError) as exc:
            print(exc)
        except Exception as exc:
            print(f"Request failed: {exc}")


if __name__ == "__main__":
    main()
