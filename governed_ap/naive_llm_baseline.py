from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from governed_ap.llm_inputs import (
    case_input_json,
)
from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
)
from governed_ap.system_decision import (
    SystemDecision,
    SystemName,
)

NAIVE_LLM_SYSTEM_PROMPT = """
You are an accounts-payable reviewer.

Review the supplied invoice package and recommend exactly
one action:

AUTO_APPROVE
ESCALATE
BLOCK

Use AUTO_APPROVE when the invoice appears payable without
human review.

Use ESCALATE when the invoice is suspicious, uncertain,
inconsistent, or appears to require human review.

Use BLOCK only when the invoice is clearly not payable.

Return JSON only with this structure:

{
  "action": "AUTO_APPROVE | ESCALATE | BLOCK",
  "reason_codes": ["short_reason"],
  "confidence": 0.0
}

confidence may be null or a number from 0 to 1.
Do not return markdown or additional text.
""".strip()


class DecisionTextProvider(Protocol):
    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...


class NaiveLLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ExpectedAction

    reason_codes: list[str] = Field(default_factory=list)

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )


def build_naive_llm_user_prompt(
    case: BenchmarkCase,
) -> str:
    package_json = case_input_json(case)

    return (
        f"Review this accounts-payable package and return your decision as JSON.\n\n{package_json}"
    )


def evaluate_naive_llm(
    case: BenchmarkCase,
    *,
    provider: DecisionTextProvider,
) -> SystemDecision:
    user_prompt = build_naive_llm_user_prompt(case)

    try:
        raw_response = provider.complete(
            system_prompt=(NAIVE_LLM_SYSTEM_PROMPT),
            user_prompt=user_prompt,
        )

        response = NaiveLLMResponse.model_validate_json(raw_response)

    except Exception:
        return SystemDecision(
            system_name=SystemName.NAIVE_LLM,
            action=ExpectedAction.ESCALATE,
            reason_codes=["SYSTEM_LLM_FAILURE"],
            confidence=None,
        )

    return SystemDecision(
        system_name=SystemName.NAIVE_LLM,
        action=response.action,
        reason_codes=response.reason_codes,
        confidence=response.confidence,
    )
