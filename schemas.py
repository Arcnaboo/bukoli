from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class ServiceInfo(BaseModel):
    service: str = Field(..., examples=["Bukoli API"])
    docs: str = Field(..., examples=["/docs"])
    health: str = Field(..., examples=["/health"])


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])


class CityDto(BaseModel):
    id: int = Field(..., examples=[7])
    name: str = Field(..., examples=["ANKARA"])
    lat: str = Field(..., examples=["39.92077"])
    lng: str = Field(..., examples=["32.85411"])


class CountyDto(BaseModel):
    id: int = Field(..., examples=[72])
    name: str = Field(..., examples=["ÇANKAYA"])


class DistrictDto(BaseModel):
    id: int = Field(..., examples=[198])
    name: str = Field(..., examples=["AKYURT"])


class NeighborhoodDto(BaseModel):
    id: int = Field(..., examples=[5138])
    name: str = Field(..., examples=["AHMETADİL MAH"])


class PointSummaryDto(BaseModel):
    id: int = Field(..., examples=[16437])
    name: str = Field(..., examples=["Ghn İletişim"])
    lat: str = Field(..., examples=["39.897254230305336"])
    lng: str = Field(..., examples=["32.79866974962879"])


class DayHoursDto(BaseModel):
    start: str = Field("", examples=["09:00"])
    end: str = Field("", examples=["18:00"])


class WorkingHoursDto(BaseModel):
    monday: DayHoursDto | None = None
    tuesday: DayHoursDto | None = None
    wednesday: DayHoursDto | None = None
    thursday: DayHoursDto | None = None
    friday: DayHoursDto | None = None
    saturday: DayHoursDto | None = None
    sunday: DayHoursDto | None = None


class PointDetailDto(BaseModel):
    id: int = Field(..., examples=[16437])
    name: str = Field(..., examples=["Ghn İletişim"])
    lat: str
    lng: str
    workingHours: WorkingHoursDto | None = None
    poiViewPhoto: str | None = Field(
        None,
        examples=["https://pathcdn01.s3.amazonaws.com/pudo/example.jpg"],
    )


class PointsPageDto(BaseModel):
    total: int = Field(..., examples=[922], description="Total points available for the filter")
    limit: int = Field(..., examples=[50], description="Requested page size")
    count: int = Field(..., examples=[50], description="Number of points returned")
    points: list[PointSummaryDto]


class PhoneLookupStatus(str, Enum):
    ok = "ok"
    no_phone = "no_phone"
    not_found = "not_found"
    error = "error"


class PhoneLookupDto(BaseModel):
    query: str = Field(..., examples=["Ghn İletişim Ankara"])
    phone: str | None = Field(None, examples=["0312 123 45 67"])
    google_title: str | None = Field(None, examples=["Ghn İletişim"])
    address: str | None = Field(None, examples=["Çankaya, Ankara"])
    website: str | None = Field(None, examples=["https://example.com"])
    match_score: float = Field(..., examples=[0.95])
    status: PhoneLookupStatus


class PointPhoneResponseDto(BaseModel):
    poi: PointDetailDto
    lookup: PhoneLookupDto


class PhoneBatchRequestDto(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {"city": "Ankara", "limit": 5, "delay": 1.5},
            {"county_id": 72, "limit": 10, "delay": 1.5},
        ]
    })

    city: str | None = Field(None, description="City name or id", examples=["Ankara", "7"])
    county_id: int | None = Field(None, description="County / ilçe id", examples=[72])
    limit: int = Field(10, ge=1, le=25, description="How many points to look up")
    delay: float = Field(1.5, ge=0, le=5, description="Seconds between SerpAPI calls")


class PhoneBatchResultItemDto(BaseModel):
    id: int
    name: str
    lat: str
    lng: str
    query: str | None = None
    phone: str | None = None
    google_title: str | None = None
    address: str | None = None
    website: str | None = None
    match_score: float | None = None
    status: PhoneLookupStatus
    error: str | None = None


class PhoneBatchResponseDto(BaseModel):
    requested: int = Field(..., examples=[5])
    total_available: int = Field(..., examples=[922])
    phones_found: int = Field(..., examples=[3])
    results: list[PhoneBatchResultItemDto]


class CountiesQuery(BaseModel):
    city: str = Field(..., description="City name or numeric id", examples=["Ankara", "7"])


class DistrictsQuery(BaseModel):
    county_id: int = Field(..., description="County / ilçe id", examples=[72])


class NeighborhoodsQuery(BaseModel):
    district_id: int = Field(..., description="District / semt id", examples=[198])


class PointsQuery(BaseModel):
    city: str | None = Field(None, description="City name or id", examples=["Ankara"])
    county_id: int | None = Field(None, description="County / ilçe id", examples=[72])
    limit: int = Field(50, ge=1, le=500, description="Max points to return")


class PointPhoneQuery(BaseModel):
    city: str | None = Field(
        None,
        description="Optional city hint for Google search",
        examples=["Ankara"],
    )
