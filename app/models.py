from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CourseStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


class CourseRecord(BaseModel):
    name: str
    credits: float
    semester: str | None = None
    grade: str | None = None
    category: str | None = None
    department: str | None = None
    notes: str | None = None
    status: CourseStatus = CourseStatus.PASSED
    source: str = "manual"
    raw: dict[str, Any] = Field(default_factory=dict)


class RequirementResult(BaseModel):
    key: str
    title: str
    required_credits: float
    earned_credits: float
    missing_credits: float
    matched_courses: list[CourseRecord] = Field(default_factory=list)
    missing_courses: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditResult(BaseModel):
    profile: str
    total_required_credits: float
    total_earned_credits: float
    requirements: list[RequirementResult]
    in_progress: list[CourseRecord] = Field(default_factory=list)
    needs_review: list[CourseRecord] = Field(default_factory=list)
    excluded: list[CourseRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditRequest(BaseModel):
    include_chem_double_major: bool = True
    include_cs_double_major: bool = True
    include_cs_minor: bool = False
    earth_bio_domain: str = "earth_environment"
