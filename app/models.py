from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CourseStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


class DataQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class EarthBioDomain(StrEnum):
    EARTH_ENVIRONMENT = "earth_environment"
    LIFE_SCIENCE = "life_science"


class CourseRecord(BaseModel):
    name: str
    credits: float = Field(ge=0, le=30)
    semester: str | None = None
    grade: str | None = None
    category: str | None = None
    department: str | None = None
    notes: str | None = None
    status: CourseStatus = CourseStatus.PASSED
    source: str = "manual"
    raw: dict[str, Any] = Field(default_factory=dict)


class ParseDiagnostic(BaseModel):
    source: str
    quality: DataQuality
    total_candidates: int = 0
    parsed_count: int = 0
    unparsed_count: int = 0
    messages: list[str] = Field(default_factory=list)
    unparsed_samples: list[str] = Field(default_factory=list)


class ParsedCourses(BaseModel):
    courses: list[CourseRecord] = Field(default_factory=list)
    diagnostic: ParseDiagnostic


class RequirementResult(BaseModel):
    key: str
    title: str
    required_credits: float
    earned_credits: float
    missing_credits: float
    complete: bool
    verification_required: bool = False
    matched_courses: list[CourseRecord] = Field(default_factory=list)
    missing_courses: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditResult(BaseModel):
    profile: str
    rule_version: str
    source_title: str | None = None
    source_url: str | None = None
    reviewed_at: str | None = None
    provisional: bool = False
    complete: bool
    total_required_credits: float
    total_earned_credits: float
    requirements: list[RequirementResult]
    in_progress: list[CourseRecord] = Field(default_factory=list)
    needs_review: list[CourseRecord] = Field(default_factory=list)
    excluded: list[CourseRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditRequest(BaseModel):
    admission_year: int = 114
    include_chem_double_major: bool = False
    include_cs_double_major: bool = False
    include_cs_minor: bool = False
    earth_bio_domain: EarthBioDomain = EarthBioDomain.EARTH_ENVIRONMENT

    @field_validator("admission_year")
    @classmethod
    def validate_admission_year(cls, value: int) -> int:
        if value != 114:
            raise ValueError("目前只支援 114 學年度入學規則；其他年度不得套用本規則。")
        return value
