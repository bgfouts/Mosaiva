from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

HypothesisStatus = Literal["active", "parked", "refuted", "supported"]
InterventionCategory = Literal["medication", "lifestyle", "diet", "supplement", "therapy"]
InterventionStatus = Literal["active", "paused", "stopped", "ask_clinician"]


class HypothesisIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = ""
    why_it_fits: str = ""
    confidence: str = ""
    likely_role: str = ""
    domains: list[str] = []
    status: HypothesisStatus = "active"
    probability: float | None = None


class HypothesisPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    statement: str | None = None
    why_it_fits: str | None = None
    confidence: str | None = None
    likely_role: str | None = None
    domains: list[str] | None = None
    status: HypothesisStatus | None = None
    probability: float | None = None
    why_moved: str | None = None


class InterventionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: InterventionCategory
    dose: str = ""
    schedule: str = ""
    clinician_prescribed: bool = False
    status: InterventionStatus = "active"
    start_date: date | None = None
    stop_date: date | None = None
    hypothesis_ids: list[int] = []
    benefit: int | None = Field(default=None, ge=1, le=5)
    side_effect_burden: int | None = Field(default=None, ge=1, le=5)
    side_effect_notes: str = ""

    @model_validator(mode="after")
    def empty_dose_until_prescribed(self):
        if self.status == "ask_clinician" and self.dose.strip():
            raise ValueError("A medicine you are not taking cannot include a dose.")
        return self


class InterventionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: InterventionCategory | None = None
    dose: str | None = None
    schedule: str | None = None
    clinician_prescribed: bool | None = None
    status: InterventionStatus | None = None
    start_date: date | None = None
    stop_date: date | None = None
    hypothesis_ids: list[int] | None = None
    benefit: int | None = Field(default=None, ge=1, le=5)
    side_effect_burden: int | None = Field(default=None, ge=1, le=5)
    side_effect_notes: str | None = None
    clinician_task: str | None = None


class ResearchSearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    hypothesis_ids: list[int] = []
    intervention_ids: list[int] = []


class ResearchPatch(BaseModel):
    hypothesis_ids: list[int] | None = None
    intervention_ids: list[int] | None = None


class CoachEventIn(BaseModel):
    kind: Literal["transcript", "tool"]
    role: Literal["patient", "coach"] | None = None
    text: str | None = None
    tool_name: str | None = None
    payload: dict | None = None
    call_id: str | None = None


class SettingsPatch(BaseModel):
    timezone: str | None = None
    display_name: str | None = Field(default=None, max_length=120)


class MosaicDecisionIn(BaseModel):
    decision: Literal["accept", "dismiss"]
    name: str | None = Field(default=None, max_length=200)
    safety_note: str | None = None
    rationale: str | None = None


class HypothesisUpdateOut(BaseModel):
    hypothesis_id: int
    probability: float
    rationale: str = ""
    evidence_ids: list[int] = []
    paper_ids: list[int] = []
    previous_probability: float | None = None
    title: str | None = None


class StoredReview(BaseModel):
    id: int
    week_start: date
    status: str
    hypothesis_updates: list
    recommendation: dict
    created_at: datetime
