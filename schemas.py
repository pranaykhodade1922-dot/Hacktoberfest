"""Strict input, inventory and result contracts; times are Asia/Kolkata local."""
from datetime import date
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


def minutes(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("time must be HH:MM (00:00 through 23:59), Asia/Kolkata")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VerificationCheck(Contract):
    category: Literal["capacity", "software", "equipment", "booking", "time_window", "batch"]
    name: str
    status: Literal["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"]
    evidence: str
    details: str = ""


class Software(Contract):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    verified: bool = True

    @field_validator("name", "version")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class Session(Contract):
    practical_name: str | None = None
    date: str
    start: str
    end: str
    students: StrictInt = Field(gt=0)
    software: list[Software] = Field(min_length=1)
    equipment: list[str] = Field(default_factory=list)
    preferred_lab: str | None = None
    allow_batch_split: bool = False
    max_batches: StrictInt = 2
    allowed_window_start: str = "09:00"
    allowed_window_end: str = "17:00"

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("date must be YYYY-MM-DD")
        date.fromisoformat(value)
        return value

    @field_validator("start", "end", "allowed_window_start", "allowed_window_end")
    @classmethod
    def valid_time(cls, value):
        minutes(value)
        return value

    @field_validator("equipment")
    @classmethod
    def valid_equipment(cls, values):
        if any(not v.strip() for v in values):
            raise ValueError("equipment names must not be blank")
        return [v.strip() for v in values]

    @model_validator(mode="after")
    def ordered(self):
        if minutes(self.end) <= minutes(self.start):
            raise ValueError("end must be after start on the same date")
        if minutes(self.allowed_window_end) <= minutes(self.allowed_window_start):
            raise ValueError("allowed window end must be after window start")
        return self


class Search(Contract):
    session: Session
    opening: str = "09:00"
    closing: str = "17:00"

    @model_validator(mode="after")
    def hours(self):
        if minutes(self.closing) <= minutes(self.opening):
            raise ValueError("closing must be after opening")
        return self


class Lab(Contract):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    capacity: StrictInt = Field(gt=0)
    total_computers: StrictInt = Field(ge=0)
    working_computers: StrictInt = Field(ge=0)
    software: list[Software]
    equipment: list[str]
    unverified_software: list[str] = Field(default_factory=list)
    unverified_equipment: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def counts(self):
        if self.working_computers > self.total_computers:
            raise ValueError("working computers exceed total computers")
        return self


class Booking(Contract):
    id: str = Field(min_length=1)
    lab_id: str = Field(min_length=1)
    date: str
    start: str
    end: str

    @model_validator(mode="after")
    def interval(self):
        Session.valid_date(self.date)
        if minutes(self.end) <= minutes(self.start):
            raise ValueError("booking end must be after start")
        return self


class Evidence(Contract):
    lab_id: str
    lab_name: str
    status: Literal["READY", "BLOCKED", "UNVERIFIED"]
    reasons: list[str]
    capacity: StrictInt
    working_computers: StrictInt
    installed_software: list[Software]
    equipment: list[str]
    conflicting_booking_ids: list[str]
    checks: list[VerificationCheck] = Field(default_factory=list)


class Readiness(Contract):
    session: Session
    status: Literal["READY", "BLOCKED", "UNVERIFIED"]
    labs: list[Evidence]
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"


class Candidate(Contract):
    session: Session
    evidence: Evidence
    batches: list[Session] = Field(default_factory=list)
    batch_evidences: list[Evidence] = Field(default_factory=list)
    is_split: bool = False
    verification_status: Literal["READY", "BLOCKED", "UNVERIFIED"] = "READY"


class RejectedCandidate(Contract):
    candidate_type: str
    lab_id: str
    lab_name: str
    time_slot: str
    reasons: list[str]


class Alternatives(Contract):
    original: Session
    alternatives: list[Candidate]
    message: str
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"
