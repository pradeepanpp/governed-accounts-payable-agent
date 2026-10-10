from decimal import Decimal

from governed_ap.llm_usage import CompletionWithUsage


class LiteLLMTextProvider:
    """Optional live-provider adapter compatible with MeteredTextProvider."""

    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        estimate_cost: bool = True,
    ) -> None:
        if not model.strip():
            raise ValueError("Model name is required.")

        if timeout_seconds <= 0:
            raise ValueError("Timeout must be positive.")

        if not 0 <= temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2.")

        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.estimate_cost = estimate_cost

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        return self.complete_with_usage(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        ).text

    def complete_with_usage(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> CompletionWithUsage:
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("Install requirements-llm.txt to use LiteLLM.") from exc

        response = litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            timeout=self.timeout_seconds,
            stream=False,
        )

        content = response.choices[0].message.content

        if not isinstance(content, str) or not content.strip():
            raise ValueError("Provider returned no textual completion.")

        usage = getattr(response, "usage", None)

        input_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None

        cost = None
        cost_basis = "unknown"

        if self.estimate_cost and input_tokens is not None and output_tokens is not None:
            try:
                calculated = litellm.completion_cost(
                    completion_response=response,
                    model=self.model,
                )

                if calculated is not None:
                    candidate = Decimal(str(calculated))

                    # A zero quote may indicate unavailable pricing.
                    # Do not silently treat an unknown model as free.
                    if candidate.is_finite() and candidate > 0:
                        cost = candidate
                        cost_basis = "estimated"
            except (ValueError, TypeError, LookupError):
                # The completion succeeded, but cost is unknown.
                pass

        return CompletionWithUsage(
            text=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            cost_basis=cost_basis,
            provider=(self.model.split("/", 1)[0] if "/" in self.model else None),
            model=self.model,
        )
