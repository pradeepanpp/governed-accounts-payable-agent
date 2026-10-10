from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from governed_ap.llm_provider import TextCompletionProvider

CostBasis = Literal["unknown", "estimated", "provider_reported"]
CallStatus = Literal["COMPLETED", "FAILED"]


@dataclass(frozen=True)
class CompletionWithUsage:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
    cost_basis: CostBasis = "unknown"
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        for value in (self.input_tokens, self.output_tokens):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("Token counts must be nonnegative integers.")

        if self.cost_usd is not None:
            if (
                not isinstance(self.cost_usd, Decimal)
                or not self.cost_usd.is_finite()
                or self.cost_usd < 0
            ):
                raise ValueError("Cost must be a finite nonnegative Decimal.")

        if (self.cost_usd is None) != (self.cost_basis == "unknown"):
            raise ValueError("Cost and cost basis must agree.")


@dataclass(frozen=True)
class LLMCallUsage:
    role: str
    status: CallStatus
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None
    cost_basis: CostBasis = "unknown"
    provider: str | None = None
    model: str | None = None
    error_type: str | None = None


class UsageCollector:
    def __init__(self) -> None:
        self._events: list[LLMCallUsage] = []

    def record(self, event: LLMCallUsage) -> None:
        self._events.append(event)

    def mark(self) -> int:
        return len(self._events)

    def since(self, mark: int) -> tuple[LLMCallUsage, ...]:
        if mark < 0 or mark > len(self._events):
            raise ValueError("Invalid usage collector mark.")
        return tuple(self._events[mark:])


class MeteredTextProvider:
    def __init__(
        self,
        provider: TextCompletionProvider,
        collector: UsageCollector,
        *,
        role: str,
    ) -> None:
        if not role.strip():
            raise ValueError("Call role cannot be empty.")

        self.provider = provider
        self.collector = collector
        self.role = role

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        try:
            measured_method = getattr(self.provider, "complete_with_usage", None)

            if callable(measured_method):
                result = measured_method(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )

                if not isinstance(result, CompletionWithUsage):
                    raise TypeError("Expected CompletionWithUsage.")

            else:
                text = self.provider.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )

                if not isinstance(text, str):
                    raise TypeError("Provider must return text.")

                result = CompletionWithUsage(text=text)

        except Exception as exc:
            self.collector.record(
                LLMCallUsage(
                    role=self.role,
                    status="FAILED",
                    error_type=type(exc).__name__,
                )
            )
            raise

        self.collector.record(
            LLMCallUsage(
                role=self.role,
                status="COMPLETED",
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                cost_basis=result.cost_basis,
                provider=result.provider,
                model=result.model,
            )
        )

        return result.text
