from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.governance_contracts import (
    LayerExecutionStatus,
)
from governed_ap.guardrail_layer import (
    LLMGuardrailLayer,
    build_guardrail_user_prompt,
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


def test_clean_text_can_pass_guardrail():
    example = generate_legitimate_example(
        seed=700,
        case_type="C1",
    )

    provider = FakeProvider(
        """
        {
            "flagged": false,
            "reason_codes": []
        }
        """
    )

    result = LLMGuardrailLayer(provider).evaluate(example.case)

    assert result.status == LayerExecutionStatus.PASS


def test_instruction_text_can_fire_guardrail():
    example = generate_development_attack_example(
        seed=701,
        attack_subtype="T1.1",
    )

    provider = FakeProvider(
        """
        {
            "flagged": true,
            "reason_codes": [
                "INSTRUCTION_TEXT"
            ]
        }
        """
    )

    result = LLMGuardrailLayer(provider).evaluate(example.case)

    assert result.minimum_action == ExpectedAction.ESCALATE

    assert "INSTRUCTION_TEXT" in result.reason_codes


def test_payment_redirection_can_fire_guardrail():
    example = generate_development_attack_example(
        seed=702,
        attack_subtype="T2.1",
    )

    provider = FakeProvider(
        """
        {
            "flagged": true,
            "reason_codes": [
                "PAYMENT_REDIRECTION_REQUEST"
            ]
        }
        """
    )

    result = LLMGuardrailLayer(provider).evaluate(example.case)

    assert result.status == LayerExecutionStatus.FIRED


def test_malformed_response_fails_closed():
    example = generate_legitimate_example(
        seed=703,
        case_type="C1",
    )

    provider = FakeProvider("not-json")

    result = LLMGuardrailLayer(provider).evaluate(example.case)

    assert result.minimum_action == ExpectedAction.ESCALATE

    assert result.reason_codes == ["SYSTEM_GUARDRAIL_FAILURE"]


def test_provider_failure_fails_closed():
    example = generate_legitimate_example(
        seed=704,
        case_type="C1",
    )

    result = LLMGuardrailLayer(FailingProvider()).evaluate(example.case)

    assert result.minimum_action == ExpectedAction.ESCALATE

    assert result.reason_codes == ["SYSTEM_GUARDRAIL_FAILURE"]


def test_flagged_response_requires_reason():
    example = generate_legitimate_example(
        seed=705,
        case_type="C1",
    )

    provider = FakeProvider(
        """
        {
            "flagged": true,
            "reason_codes": []
        }
        """
    )

    result = LLMGuardrailLayer(provider).evaluate(example.case)

    assert result.reason_codes == ["SYSTEM_GUARDRAIL_FAILURE"]


def test_guardrail_prompt_contains_invoice_text():
    example = generate_development_attack_example(
        seed=706,
        attack_subtype="T1.1",
    )

    prompt = build_guardrail_user_prompt(example.case)

    assert example.case.invoice.raw_text in prompt


def test_guardrail_prompt_does_not_leak_labels():
    example = generate_development_attack_example(
        seed=707,
        attack_subtype="T1.1",
    )

    prompt = build_guardrail_user_prompt(example.case)

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
