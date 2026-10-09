from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.decision_agent import (
    LLMDecisionAgent,
    build_decision_agent_user_prompt,
)
from governed_ap.schemas import (
    ExpectedAction,
)


class FakeProvider:
    def __init__(
        self,
        response: str,
    ) -> None:
        self.response = response

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        return self.response


class FailingProvider:
    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        raise RuntimeError("Simulated provider failure.")


def test_decision_agent_can_auto_approve():
    example = generate_legitimate_example(
        seed=800,
        case_type="C1",
    )

    provider = FakeProvider(
        """
        {
            "action": "AUTO_APPROVE",
            "reason_codes": [],
            "confidence": 0.92
        }
        """
    )

    recommendation = LLMDecisionAgent(provider).recommend(example.case)

    assert recommendation.action == ExpectedAction.AUTO_APPROVE

    assert recommendation.confidence == 0.92


def test_decision_agent_can_escalate():
    example = generate_development_attack_example(
        seed=801,
        attack_subtype="T1.1",
    )

    provider = FakeProvider(
        """
        {
            "action": "ESCALATE",
            "reason_codes": [
                "SUSPICIOUS_INSTRUCTION"
            ],
            "confidence": 0.88
        }
        """
    )

    recommendation = LLMDecisionAgent(provider).recommend(example.case)

    assert recommendation.action == ExpectedAction.ESCALATE


def test_malformed_decision_fails_closed():
    example = generate_legitimate_example(
        seed=802,
        case_type="C1",
    )

    recommendation = LLMDecisionAgent(FakeProvider("not-json")).recommend(example.case)

    assert recommendation.action == ExpectedAction.ESCALATE

    assert recommendation.reason_codes == ["SYSTEM_DECISION_AGENT_FAILURE"]


def test_provider_failure_fails_closed():
    example = generate_legitimate_example(
        seed=803,
        case_type="C1",
    )

    recommendation = LLMDecisionAgent(FailingProvider()).recommend(example.case)

    assert recommendation.action == ExpectedAction.ESCALATE


def test_decision_prompt_contains_invoice_text():
    example = generate_development_attack_example(
        seed=804,
        attack_subtype="T1.1",
    )

    prompt = build_decision_agent_user_prompt(example.case)

    assert example.case.invoice.raw_text in prompt


def test_decision_prompt_does_not_leak_truth():
    example = generate_development_attack_example(
        seed=805,
        attack_subtype="T1.1",
    )

    prompt = build_decision_agent_user_prompt(example.case)

    forbidden = (
        "is_malicious",
        "expected_action",
        "attack_family",
        "attack_subtype",
        "template_id",
        "scenario_id",
    )

    for field in forbidden:
        assert field not in prompt
