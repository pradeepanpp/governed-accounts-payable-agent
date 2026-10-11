import argparse
from pathlib import Path
from time import perf_counter

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.invoice_extraction import (
    InvoiceIntakeError,
    case_from_invoice_text,
    render_invoice_text,
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
    parser = argparse.ArgumentParser(description="Governed accounts-payable agent demonstration.")

    parser.add_argument(
        "--mode",
        choices=("mock", "live"),
        default="mock",
    )

    parser.add_argument(
        "--model",
        default=None,
    )

    parser.add_argument(
        "--allow-paid-api",
        action="store_true",
        help="Explicitly authorize chargeable live model calls.",
    )

    parser.add_argument(
        "--scenario",
        choices=("all", "legitimate", "bank", "duplicate"),
        default="all",
    )

    parser.add_argument(
        "--input",
        choices=("structured", "text"),
        default="structured",
        help="Choose structured or locally parsed text input.",
    )

    parser.add_argument(
        "--invoice-file",
        type=Path,
        default=None,
        help="Read one labeled invoice text file.",
    )

    args = parser.parse_args()

    if args.mode == "live":
        if not args.allow_paid_api:
            parser.error("Live mode spends API credits. Explicit --allow-paid-api is required.")

        if not args.model:
            parser.error("--model is required in live mode")

    if args.invoice_file is not None:
        if args.input != "text":
            parser.error("--invoice-file requires --input text")

        if args.scenario == "all":
            parser.error("Choose one --scenario when using --invoice-file")

    agent = create_agent(args.mode, args.model)
    examples = create_examples()

    selected = examples.keys() if args.scenario == "all" else (args.scenario,)

    print(f"Provider mode: {args.mode}")
    print(f"Input mode: {args.input}")
    print("Synthetic accounts-payable decision demonstration.")

    for name in selected:
        case = examples[name]

        if args.input == "text":
            try:
                if args.invoice_file is not None:
                    source_text = args.invoice_file.read_text(encoding="utf-8")
                else:
                    source_text = render_invoice_text(case.invoice)

                case = case_from_invoice_text(
                    case,
                    source_text,
                )

            except (
                InvoiceIntakeError,
                OSError,
                UnicodeError,
            ) as error:
                print(f"\nSCENARIO: {name.upper()}")
                print("Intake disposition: ESCALATE")
                print("Reason: INVOICE_INTAKE_FAILURE")
                print(f"Detail: {error}")
                print("Agent invoked: NO")
                print("Payment executed: NO")
                continue

            print(f"\nText extraction completed: {name}")

        show_result(name, case, agent)


if __name__ == "__main__":
    main()
