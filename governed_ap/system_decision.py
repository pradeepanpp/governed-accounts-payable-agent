from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from governed_ap.schemas import ExpectedAction


class SystemName(str, Enum):
    DETERMINISTIC_BASELINE = "deterministic_baseline"
    NAIVE_LLM = "naive_llm"
    GOVERNED_AGENT = "governed_agent"


class SystemDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_name: SystemName
    action: ExpectedAction

    reason_codes: list[str] = Field(default_factory=list)

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
