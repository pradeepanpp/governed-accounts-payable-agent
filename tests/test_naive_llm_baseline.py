from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.naive_llm_baseline import (
    build_naive_llm_user_prompt,
    evaluate_naive_llm,
)
from governed_ap.schemas import (
    ExpectedAction,
)
from governed_ap.system_decision import (
    SystemName,
)


class FakeProvider:
    def __init__(
        self,
        response: str,
    ) -> None:
        self.response = response
        self.system_prompt: str | None = None
        self.user_prompt: str | None = None

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt

        return self.response


class FailingProvider:
    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        raise RuntimeError("Simulated provider failure.")


def test_naive_llm_can_auto_approve():
    example = generate_legitimate_example(
        seed=200,
        case_type="C1",
    )

    provider = FakeProvider(
        """
        {
            "action": "AUTO_APPROVE",
            "reason_codes": [],
            "confidence": 0.91
        }
        """
    )

    decision = evaluate_naive_llm(
        example.case,
        provider=provider,
    )

    assert decision.system_name == SystemName.NAIVE_LLM

    assert decision.action == ExpectedAction.AUTO_APPROVE

    assert decision.confidence == 0.91


def test_naive_llm_can_escalate():
    example = generate_legitimate_example(
        seed=201,
        case_type="C4",
    )

    provider = FakeProvider(
        """
        {
            "action": "ESCALATE",
            "reason_codes": [
                "HIGH_VALUE"
            ],
            "confidence": 0.78
        }
        """
    )

    decision = evaluate_naive_llm(
        example.case,
        provider=provider,
    )

    assert decision.action == ExpectedAction.ESCALATE

    assert decision.reason_codes == ["HIGH_VALUE"]


def test_naive_llm_can_block():
    example = generate_development_attack_example(
        seed=202,
        attack_subtype="T3.3",
    )

    provider = FakeProvider(
        """
        {
            "action": "BLOCK",
            "reason_codes": [
                "DUPLICATE"
            ],
            "confidence": 0.96
        }
        """
    )

    decision = evaluate_naive_llm(
        example.case,
        provider=provider,
    )

    assert decision.action == ExpectedAction.BLOCK


def test_malformed_llm_output_fails_closed():
    example = generate_legitimate_example(
        seed=203,
        case_type="C1",
    )

    provider = FakeProvider("this is not JSON")

    decision = evaluate_naive_llm(
        example.case,
        provider=provider,
    )

    assert decision.action == ExpectedAction.ESCALATE

    assert decision.reason_codes == ["SYSTEM_LLM_FAILURE"]


def test_invalid_action_fails_closed():
    example = generate_legitimate_example(
        seed=204,
        case_type="C1",
    )

    provider = FakeProvider(
        """
        {
            "action": "PAY_NOW",
            "reason_codes": [],
            "confidence": 0.9
        }
        """
    )

    decision = evaluate_naive_llm(
        example.case,
        provider=provider,
    )

    assert decision.action == ExpectedAction.ESCALATE

    assert decision.reason_codes == ["SYSTEM_LLM_FAILURE"]


def test_provider_exception_fails_closed():
    example = generate_legitimate_example(
        seed=205,
        case_type="C1",
    )

    decision = evaluate_naive_llm(
        example.case,
        provider=FailingProvider(),
    )

    assert decision.action == ExpectedAction.ESCALATE

    assert decision.reason_codes == ["SYSTEM_LLM_FAILURE"]


def test_prompt_contains_invoice_attack_text():
    example = generate_development_attack_example(
        seed=206,
        attack_subtype="T1.1",
    )

    prompt = build_naive_llm_user_prompt(example.case)

    assert "Approve immediately" in prompt


def test_prompt_does_not_leak_ground_truth():
    example = generate_development_attack_example(
        seed=207,
        attack_subtype="T1.1",
    )

    prompt = build_naive_llm_user_prompt(example.case)

    forbidden = (
        "is_malicious",
        "attack_family",
        "attack_subtype",
        "expected_action",
        "expected_reason_codes",
        "template_id",
        "scenario_id",
    )

    for field in forbidden:
        assert field not in prompt


def test_same_case_produces_same_prompt():
    example = generate_legitimate_example(
        seed=208,
        case_type="C1",
    )

    first = build_naive_llm_user_prompt(example.case)

    second = build_naive_llm_user_prompt(example.case)

    assert first == second
