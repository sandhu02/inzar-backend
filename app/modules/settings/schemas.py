from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GlobalSettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_search_radius_km: int = Field(default=50, ge=1, le=200)
    allowed_radius_options_km: list[int] = Field(default=[1, 3, 5, 10, 25, 50])
    fuzz_distance_m: int = Field(default=200, ge=50, le=1000)
    max_reports_per_user_per_hour: int = Field(default=5, ge=1, le=50)
    max_description_length: int = Field(default=1000, ge=100, le=5000)
    review_mode: Literal["auto_approve", "manual"] = "auto_approve"
    abuse_flag_hide_threshold: int = Field(default=3, ge=1, le=20)
    alert_digest_threshold: int = Field(default=3, ge=2, le=20)
    alert_digest_window_minutes: int = Field(default=30, ge=5, le=180)
    min_account_age_minutes_to_report: int = Field(default=0, ge=0, le=10080)


class GlobalSettingsUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_search_radius_km: int | None = Field(default=None, ge=1, le=200)
    allowed_radius_options_km: list[int] | None = None
    fuzz_distance_m: int | None = Field(default=None, ge=50, le=1000)
    max_reports_per_user_per_hour: int | None = Field(default=None, ge=1, le=50)
    max_description_length: int | None = Field(default=None, ge=100, le=5000)
    review_mode: Literal["auto_approve", "manual"] | None = None
    abuse_flag_hide_threshold: int | None = Field(default=None, ge=1, le=20)
    alert_digest_threshold: int | None = Field(default=None, ge=2, le=20)
    alert_digest_window_minutes: int | None = Field(default=None, ge=5, le=180)
    min_account_age_minutes_to_report: int | None = Field(default=None, ge=0, le=10080)


class PublicConfigResponse(BaseModel):
    max_search_radius_km: int
    allowed_radius_options_km: list[int]
    max_description_length: int
    fuzz_distance_m: int


class SettingItemResponse(BaseModel):
    key: str
    value: Any
    description: str | None
