from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Strict):
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    quote: str = Field(min_length=3)


class Requirement(Strict):
    id: str
    original_id: str
    summary: str
    kind: Literal["functional", "nonfunctional", "interface", "acceptance", "data"]
    evidence: Evidence


class Inventory(Strict):
    requirements: list[Requirement] = Field(min_length=1)
    limitations: list[str]


class Finding(Strict):
    id: str
    title: str
    category: Literal["contradiction", "ambiguity", "missing", "unverifiable", "design", "traceability"]
    severity: Literal["critical", "high", "medium", "low"]
    requirement_ids: list[str] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    explanation: str
    scenario: str
    question: str
    repair_options: list[str] = Field(min_length=1)


class Assessment(Strict):
    requirement_id: str
    clarity: Literal["pass", "issue", "unknown"]
    completeness: Literal["pass", "issue", "unknown"]
    verifiability: Literal["pass", "issue", "unknown"]
    atomicity: Literal["pass", "issue", "unknown"]
    note: str


class Audit(Strict):
    findings: list[Finding]
    assessments: list[Assessment]
    set_assessment: str
    limitations: list[str]


class Decision(Strict):
    finding_id: str
    verdict: Literal["supported", "needs_clarification", "rejected"]
    reason: str


class Review(Strict):
    decisions: list[Decision]


class Expr(Strict):
    # Deliberately limited language: one integer variable plus an offset, or a constant.
    variable: str | None
    offset: int = Field(ge=-(10**12), le=10**12)


class Predicate(Strict):
    left: Expr
    op: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    right: Expr


class Variable(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    description: str
    minimum: int = Field(ge=-(10**12), le=10**12)
    maximum: int = Field(ge=-(10**12), le=10**12)


class Interpretation(Strict):
    requirement_id: str
    guard: list[Predicate]
    output: Expr
    explanation: str


class WitnessModel(Strict):
    finding_id: str
    output_name: str
    variables: list[Variable] = Field(min_length=1, max_length=20)
    assumptions: list[str] = Field(min_length=1)
    left: Interpretation
    right: Interpretation


class Formalizations(Strict):
    models: list[WitnessModel] = Field(max_length=30)
