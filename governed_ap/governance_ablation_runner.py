import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from governed_ap.evaluation_bootstrap import (
    BootstrapInterval,
    bootstrap_paired_differences,
)
from governed_ap.experiment_execution import ExperimentRun, run_experiment
from governed_ap.governance_ablation import (
    AblationConfig,
    AblationLangGraphAgent,
    ablation_plan,
)
from governed_ap.llm_provider import TextCompletionProvider
from governed_ap.llm_usage import MeteredTextProvider, UsageCollector
from governed_ap.schemas import BenchmarkExample
from governed_ap.system_decision import SystemName

ProviderFactory = Callable[
    [AblationConfig],
    tuple[TextCompletionProvider, TextCompletionProvider],
]


@dataclass(frozen=True)
class AblationResult:
    config: AblationConfig
    executed_as: str
    run: ExperimentRun

    @property
    def reused(self) -> bool:
        return self.config.name != self.executed_as


@dataclass(frozen=True)
class AblationSuite:
    results: tuple[AblationResult, ...]

    def by_name(self, name: str) -> AblationResult:
        for result in self.results:
            if result.config.name == name:
                return result
        raise KeyError(f"Unknown ablation condition: {name}")

    @property
    def unique_execution_count(self) -> int:
        return len({result.run.run_id for result in self.results})


def run_ablation_suite(
    scenarios: list[list[BenchmarkExample]],
    providers_for: ProviderFactory,
    *,
    configurations: tuple[AblationConfig, ...] | None = None,
    run_prefix: str = "dev-abl",
    repository: str | Path = ".",
) -> AblationSuite:
    """
    Execute offline development ablations.

    Identical enabled-layer configurations share the same execution.
    No real payment operation is performed.
    """
    plan = configurations if configurations is not None else ablation_plan()

    if not plan:
        raise ValueError("Ablation plan cannot be empty.")

    if len({config.name for config in plan}) != len(plan):
        raise ValueError("Ablation configuration names must be unique.")

    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,15}", run_prefix) is None:
        raise ValueError("Invalid ablation run prefix.")

    cache: dict[frozenset, AblationResult] = {}
    results: list[AblationResult] = []

    for config in plan:
        key = config.enabled_layers

        if key in cache:
            canonical = cache[key]

            results.append(
                AblationResult(
                    config=config,
                    executed_as=canonical.config.name,
                    run=canonical.run,
                )
            )
            continue

        run_id = f"{run_prefix}_{config.name}"

        if len(run_id) > 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id):
            raise ValueError("Invalid generated run ID.")

        guardrail_provider, decision_provider = providers_for(config)
        collector = UsageCollector()

        agent = AblationLangGraphAgent(
            config=config,
            guardrail_provider=MeteredTextProvider(
                guardrail_provider,
                collector,
                role="guardrail",
            ),
            decision_provider=MeteredTextProvider(
                decision_provider,
                collector,
                role="decision",
            ),
        )

        run = run_experiment(
            scenarios,
            agent.process,
            run_id=run_id,
            system_name=SystemName.GOVERNED_AGENT,
            execution_mode="test_double",
            repository=repository,
            usage_collector=collector,
        )

        result = AblationResult(
            config=config,
            executed_as=config.name,
            run=run,
        )

        cache[key] = result
        results.append(result)

    return AblationSuite(results=tuple(results))


def compare_ablations_to_full(
    suite: AblationSuite,
    *,
    repetitions: int = 200,
    seed: int = 2026,
) -> dict[str, dict[str, BootstrapInterval]]:
    """Return each condition minus full governance."""
    full = suite.by_name("full_governance")

    comparisons = {}

    for result in suite.results:
        if result.config.name == "full_governance":
            continue

        comparisons[result.config.name] = bootstrap_paired_differences(
            result.run.evaluated,
            full.run.evaluated,
            repetitions=repetitions,
            seed=seed,
        )

    return comparisons
