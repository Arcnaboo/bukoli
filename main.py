from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

import bukoli_service as svc
from schemas import (
    CityDto,
    CountiesQuery,
    CountyDto,
    DistrictDto,
    DistrictsQuery,
    HealthResponse,
    NeighborhoodDto,
    NeighborhoodsQuery,
    PhoneBatchRequestDto,
    PhoneBatchResponseDto,
    PhoneBatchResultItemDto,
    PhoneLookupDto,
    PointDetailDto,
    PointPhoneQuery,
    PointPhoneResponseDto,
    PointSummaryDto,
    PointsPageDto,
    PointsQuery,
    ServiceInfo,
)

app = FastAPI(
    title="Bukoli API",
    description="Bukoli delivery points with optional Google phone lookup via SerpAPI.",
    version="1.0.0",
)


@app.on_event("startup")
def startup() -> None:
    svc.load_env_file()


def city_http_errors(exc: Exception) -> None:
    if isinstance(exc, svc.AmbiguousCityError):
        raise HTTPException(status_code=400, detail={"error": str(exc), "matches": exc.matches})
    if isinstance(exc, svc.CityNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/", response_model=ServiceInfo)
def root() -> ServiceInfo:
    return ServiceInfo(service="Bukoli API", docs="/docs", health="/health")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/cities", response_model=list[CityDto])
def list_cities() -> list[CityDto]:
    return [CityDto.model_validate(city) for city in svc.get_cities()]


@app.get("/counties", response_model=list[CountyDto])
def list_counties(
    query: Annotated[CountiesQuery, Query()],
) -> list[CountyDto]:
    try:
        return [CountyDto.model_validate(county) for county in svc.get_counties(query.city)]
    except svc.BukoliError as exc:
        city_http_errors(exc)
        raise


@app.get("/districts", response_model=list[DistrictDto])
def list_districts(
    query: Annotated[DistrictsQuery, Query()],
) -> list[DistrictDto]:
    return [DistrictDto.model_validate(item) for item in svc.get_districts(query.county_id)]


@app.get("/neighborhoods", response_model=list[NeighborhoodDto])
def list_neighborhoods(
    query: Annotated[NeighborhoodsQuery, Query()],
) -> list[NeighborhoodDto]:
    return [
        NeighborhoodDto.model_validate(item)
        for item in svc.get_neighborhoods(query.district_id)
    ]


@app.get("/points", response_model=PointsPageDto)
def list_points(
    query: Annotated[PointsQuery, Query()],
) -> PointsPageDto:
    try:
        data = svc.get_points(
            city=query.city,
            county_id=query.county_id,
            limit=query.limit,
        )
        return PointsPageDto(
            total=data["total"],
            limit=data["limit"],
            count=data["count"],
            points=[PointSummaryDto.model_validate(point) for point in data["points"]],
        )
    except svc.BukoliError as exc:
        city_http_errors(exc)
        raise


@app.get("/points/{poi_id}", response_model=PointDetailDto)
def get_point(poi_id: int) -> PointDetailDto:
    return PointDetailDto.model_validate(svc.get_poi(poi_id))


@app.get("/points/{poi_id}/phone", response_model=PointPhoneResponseDto)
def get_point_phone(
    poi_id: int,
    query: Annotated[PointPhoneQuery, Query()],
) -> PointPhoneResponseDto:
    try:
        data = svc.lookup_poi_phone(poi_id, city=query.city)
        return PointPhoneResponseDto(
            poi=PointDetailDto.model_validate(data["poi"]),
            lookup=PhoneLookupDto.model_validate(data["lookup"]),
        )
    except svc.SerpApiKeyMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except svc.BukoliError as exc:
        city_http_errors(exc)
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/points/phones/lookup", response_model=PhoneBatchResponseDto)
def lookup_phones_batch(body: PhoneBatchRequestDto) -> PhoneBatchResponseDto:
    try:
        data = svc.lookup_phones_batch(
            city=body.city,
            county_id=body.county_id,
            limit=body.limit,
            delay=body.delay,
        )
        return PhoneBatchResponseDto(
            requested=data["requested"],
            total_available=data["total_available"],
            phones_found=data["phones_found"],
            results=[PhoneBatchResultItemDto.model_validate(item) for item in data["results"]],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except svc.SerpApiKeyMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except svc.BukoliError as exc:
        city_http_errors(exc)
        raise
