from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import bukoli_service as svc

app = FastAPI(
    title="Bukoli API",
    description="Bukoli delivery points with optional Google phone lookup via SerpAPI.",
    version="1.0.0",
)


@app.on_event("startup")
def startup() -> None:
    svc.load_env_file()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Bukoli API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cities")
def list_cities() -> list[dict[str, Any]]:
    return svc.get_cities()


@app.get("/counties")
def list_counties(city: str = Query(..., description="City name or numeric id, e.g. Ankara or 7")):
    try:
        return svc.get_counties(city)
    except svc.AmbiguousCityError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "matches": exc.matches})
    except svc.CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/districts")
def list_districts(county_id: int = Query(..., description="County / ilçe id")):
    return svc.get_districts(county_id)


@app.get("/neighborhoods")
def list_neighborhoods(district_id: int = Query(..., description="District / semt id")):
    return svc.get_neighborhoods(district_id)


@app.get("/points")
def list_points(
    city: str | None = Query(None, description="City name or id"),
    county_id: int | None = Query(None, description="County / ilçe id"),
    limit: int = Query(50, ge=1, le=500),
):
    try:
        return svc.get_points(city=city, county_id=county_id, limit=limit)
    except svc.AmbiguousCityError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "matches": exc.matches})
    except svc.CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/points/{poi_id}")
def get_point(poi_id: int):
    return svc.get_poi(poi_id)


@app.get("/points/{poi_id}/phone")
def get_point_phone(
    poi_id: int,
    city: str | None = Query(None, description="Optional city hint for Google search"),
):
    try:
        return svc.lookup_poi_phone(poi_id, city=city)
    except svc.SerpApiKeyMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except svc.AmbiguousCityError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "matches": exc.matches})
    except svc.CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


class PhoneBatchRequest(BaseModel):
    city: str | None = Field(None, description="City name or id")
    county_id: int | None = Field(None, description="County / ilçe id")
    limit: int = Field(10, ge=1, le=25)
    delay: float = Field(1.5, ge=0, le=5)


@app.post("/points/phones/lookup")
def lookup_phones_batch(body: PhoneBatchRequest):
    try:
        return svc.lookup_phones_batch(
            city=body.city,
            county_id=body.county_id,
            limit=body.limit,
            delay=body.delay,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except svc.SerpApiKeyMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except svc.AmbiguousCityError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "matches": exc.matches})
    except svc.CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
