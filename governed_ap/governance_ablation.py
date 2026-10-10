from dataclasses import dataclass

from governed_ap.governance_contracts import (
    GovernanceLayerName,
    GovernanceLayerResult,
    LayerExecutionStatus,
)
from governed_ap.langgraph_agent import (
    GovernedGraphState,
    LangGraphGovernedAPAgent,
)
from governed_ap.llm_provider import TextCompletionProvider

LAYER_ORDER = (
    GovernanceLayerName.DETERMINISTIC_CHECKS,
    GovernanceLayerName.GUARDRAIL,
    GovernanceLayerName.HISTORY_SEQUENCE_RISK,
    GovernanceLayerName.POLICY_ENGINE,
)

ALL_LAYERS = frozenset(LAYER_ORDER)


@dataclass(frozen=True)
class AblationConfig:
    name: str
    enabled_layers: frozenset[GovernanceLayerName]

    def __post_init__(self) -> None:
        if not self.name or not self.name.isidentifier():
            raise ValueError("Invalid ablation configuration name.")

        if not isinstance(self.enabled_layers, frozenset):
            raise ValueError("Enabled layers must be a frozenset.")

        if not self.enabled_layers.issubset(ALL_LAYERS):
            raise ValueError("Unknown governance layer.")


def ablation_plan() -> tuple[AblationConfig, ...]:
    """Additive ladder followed by leave-one-layer-out conditions."""
    configurations = [AblationConfig("decision_and_gate_only", frozenset())]

    enabled = frozenset()

    for index, layer in enumerate(LAYER_ORDER, start=1):
        enabled = enabled | {layer}

        name = "full_governance" if index == len(LAYER_ORDER) else f"ladder_{index}_{layer.value}"

        configurations.append(AblationConfig(name, enabled))

    for layer in LAYER_ORDER:
        configurations.append(
            AblationConfig(
                name=f"without_{layer.value}",
                enabled_layers=ALL_LAYERS - {layer},
            )
        )

    return tuple(configurations)


def _not_evaluated(
    layer: GovernanceLayerName,
) -> GovernanceLayerResult:
    return GovernanceLayerResult(
        layer=layer,
        status=LayerExecutionStatus.NOT_EVALUATED,
    )


class AblationLangGraphAgent(LangGraphGovernedAPAgent):
    """
    Counterfactual research-only agent.

    Existing decision and enforcement nodes are inherited.
    Only selected governance checks are executed.
    """

    def __init__(
        self,
        *,
        config: AblationConfig,
        guardrail_provider: TextCompletionProvider,
        decision_provider: TextCompletionProvider,
    ) -> None:
        self.config = config

        super().__init__(
            guardrail_provider=guardrail_provider,
            decision_provider=decision_provider,
        )

    def _enabled(self, layer: GovernanceLayerName) -> bool:
        return layer in self.config.enabled_layers

    def _deterministic_node(
        self,
        state: GovernedGraphState,
    ) -> dict[str, GovernanceLayerResult]:
        layer = GovernanceLayerName.DETERMINISTIC_CHECKS

        if not self._enabled(layer):
            return {"deterministic_result": _not_evaluated(layer)}

        return super()._deterministic_node(state)

    def _guardrail_node(
        self,
        state: GovernedGraphState,
    ) -> dict[str, GovernanceLayerResult]:
        layer = GovernanceLayerName.GUARDRAIL

        if not self._enabled(layer):
            return {"guardrail_result": _not_evaluated(layer)}

        return super()._guardrail_node(state)

    def _history_node(
        self,
        state: GovernedGraphState,
    ) -> dict[str, GovernanceLayerResult]:
        layer = GovernanceLayerName.HISTORY_SEQUENCE_RISK

        if not self._enabled(layer):
            return {"history_result": _not_evaluated(layer)}

        return super()._history_node(state)

    def _policy_node(
        self,
        state: GovernedGraphState,
    ) -> dict[str, GovernanceLayerResult]:
        layer = GovernanceLayerName.POLICY_ENGINE

        if not self._enabled(layer):
            return {"policy_result": _not_evaluated(layer)}

        return super()._policy_node(state)
