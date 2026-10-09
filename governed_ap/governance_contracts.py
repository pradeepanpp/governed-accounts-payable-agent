from decimal import Decimal
from enum import Enum
from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
)


class GovernanceLayerName(str, Enum):
    DETERMINISTIC_CHECKS = "deterministic_checks"
    GUARDRAIL = "guardrail"
    HISTORY_SEQUENCE_RISK = "history_sequence_risk"
    POLICY_ENGINE = "policy_engine"


class LayerExecutionStatus(str, Enum):
    PASS = "PASS"
    FIRED = "FIRED"
    NOT_EVALUATED = "NOT_EVALUATED"


class LayerTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: float | None = Field(
        default=None,
        ge=0,
    )

    input_tokens: int | None = Field(
        default=None,
        ge=0,
    )

    output_tokens: int | None = Field(
        default=None,
        ge=0,
    )

    estimated_cost_usd: Decimal | None = Field(
        default=None,
        ge=0,
    )

    provider: str | None = None
    model: str | None = None


class GovernanceLayerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: GovernanceLayerName

    status: LayerExecutionStatus

    minimum_action: ExpectedAction | None = None

    reason_codes: list[str] = Field(default_factory=list)

    telemetry: LayerTelemetry = Field(default_factory=LayerTelemetry)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(
        cls,
        value: list[str],
    ) -> list[str]:
        cleaned = [reason.strip() for reason in value]

        if any(not reason for reason in cleaned):
            raise ValueError("Reason codes cannot be empty.")

        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Reason codes must be unique.")

        return cleaned

    @model_validator(mode="after")
    def validate_status_contract(
        self,
    ) -> "GovernanceLayerResult":
        if self.status == LayerExecutionStatus.FIRED:
            if self.minimum_action not in {
                ExpectedAction.ESCALATE,
                ExpectedAction.BLOCK,
            }:
                raise ValueError("A fired governance layer must require ESCALATE or BLOCK.")

            if not self.reason_codes:
                raise ValueError("A fired governance layer must provide at least one reason code.")

            return self

        if self.minimum_action is not None:
            raise ValueError("A non-fired governance layer cannot require an action.")

        if self.reason_codes:
            raise ValueError("A non-fired governance layer cannot provide reason codes.")

        return self


class DecisionAgentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ExpectedAction

    reason_codes: list[str] = Field(default_factory=list)

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )

    telemetry: LayerTelemetry = Field(default_factory=LayerTelemetry)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(
        cls,
        value: list[str],
    ) -> list[str]:
        cleaned = [reason.strip() for reason in value]

        if any(not reason for reason in cleaned):
            raise ValueError("Reason codes cannot be empty.")

        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Reason codes must be unique.")

        return cleaned


class GovernanceLayer(Protocol):
    def evaluate(
        self,
        case: BenchmarkCase,
    ) -> GovernanceLayerResult: ...


class DecisionAgent(Protocol):
    def recommend(
        self,
        case: BenchmarkCase,
    ) -> DecisionAgentRecommendation: ...
