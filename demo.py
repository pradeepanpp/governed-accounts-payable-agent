import argparse
from time import perf_counter

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.langgraph_agent import LangGraphGovernedAPAgent


class MockProvider:
    """Fixed responses for a free, reproducible demonstration."""

    def __init__(self, response: str):
        self.response = response

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response


def create_agent(mode: str, model: str | None):
    if mode == "mock":
        return LangGraphGovernedAPAgent(
            guardrail_provider=MockProvider('{"flagged":false,"reason_codes":[]}'),
            decision_provider=MockProvider(
                '{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.9}'
            ),
        )

    if not model:
        raise ValueError("Live mode requires --model.")

    from governed_ap.litellm_provider import LiteLLMTextProvider

    return LangGraphGovernedAPAgent(
        guardrail_provider=LiteLLMTextProvider(model),
        decision_provider=LiteLLMTextProvider(model),
    )


def create_examples():
    return {
        "legitimate": generate_legitimate_example(
            seed=1100,
            case_type="C1",
        ).case,
        "bank": generate_development_attack_example(
            seed=1105,
            attack_subtype="T2.1",
        ).case,
        "duplicate": generate_development_attack_example(
            seed=1103,
            attack_subtype="T3.3",
        ).case,
    }


def show_result(name, case, agent):
    started = perf_counter()
    trace = agent.process(case)
    elapsed_ms = (perf_counter() - started) * 1000

    print(f"\n{'=' * 55}")
    print(f"SCENARIO: {name.upper()}")
    print(f"{'=' * 55}")

    print(f"Invoice ID: {case.invoice.invoice_id}")
    print(f"Invoice amount: {case.invoice.total_amount} {case.invoice.currency}")
    print(f"Invoice bank: {case.invoice.invoice_bank_account}")

    if case.vendor is not None:
        print(f"Trusted vendor bank: {case.vendor.approved_bank_account}")

    print(f"\nLLM recommendation: {trace.recommendation.action.value}")
    print(f"Final enforced action: {trace.final_action.value}")

    print("\nGovernance layers:")

    for result in trace.layer_results:
        reasons = ", ".join(result.reason_codes) or "none"
        print(f"  {result.layer.value}: {result.status.value} ({reasons})")

    reasons = ", ".join(trace.enforcement.reason_codes) or "none"
    print(f"\nFinal reasons: {reasons}")
    print(f"Execution time: {elapsed_ms:.2f} ms")
    print("Payment executed: NO (offline simulation)")

    return trace.final_action.value


def main():
    parser = argparse.ArgumentParser(description="Offline governed accounts-payable agent demo.")
    parser.add_argument(
        "--mode",
        choices=("mock", "live"),
        default="mock",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LiteLLM model identifier for live mode.",
    )
    parser.add_argument(
        "--scenario",
        choices=("all", "legitimate", "bank", "duplicate"),
        default="all",
    )

    args = parser.parse_args()

    if args.mode == "live" and not args.model:
        parser.error("--model is required in live mode")

    agent = create_agent(args.mode, args.model)
    examples = create_examples()

    selected = examples.keys() if args.scenario == "all" else (args.scenario,)

    print(f"Provider mode: {args.mode}")
    print("Structured-input, offline decision demonstration.")

    for name in selected:
        show_result(name, examples[name], agent)


if __name__ == "__main__":
    main()
