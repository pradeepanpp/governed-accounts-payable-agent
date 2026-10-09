from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from governed_ap.decision_agent import (
    LLMDecisionAgent,
)
from governed_ap.deterministic_checks_layer import (
    DeterministicChecksLayer,
)
from governed_ap.enforcement_gate import (
    EnforcementGateDecision,
    enforce_decision,
)
from governed_ap.governance_contracts import (
    DecisionAgentRecommendation,
    GovernanceLayerName,
    GovernanceLayerResult,
    LayerExecutionStatus,
)
from governed_ap.guardrail_layer import (
    LLMGuardrailLayer,
)
from governed_ap.history_risk_layer import (
    HistorySequenceRiskLayer,
)
from governed_ap.llm_provider import (
    TextCompletionProvider,
)
from governed_ap.policy_engine_layer import (
    PolicyEngineLayer,
)
from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
)


class GovernedAgentTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer_results: list[GovernanceLayerResult] = Field(default_factory=list)

    recommendation: DecisionAgentRecommendation

    enforcement: EnforcementGateDecision

    @property
    def final_action(
        self,
    ) -> ExpectedAction:
        return self.enforcement.final_action


def _layer_failure_result(
    layer: GovernanceLayerName,
    reason_code: str,
) -> GovernanceLayerResult:
    return GovernanceLayerResult(
        layer=layer,
        status=LayerExecutionStatus.FIRED,
        minimum_action=(ExpectedAction.ESCALATE),
        reason_codes=[reason_code],
    )


def _evaluate_deterministic(
    case: BenchmarkCase,
) -> GovernanceLayerResult:
    try:
        return DeterministicChecksLayer().evaluate(case)

    except Exception:
        return _layer_failure_result(
            GovernanceLayerName.DETERMINISTIC_CHECKS,
            ("SYSTEM_DETERMINISTIC_CHECKS_FAILURE"),
        )


def _evaluate_history(
    case: BenchmarkCase,
) -> GovernanceLayerResult:
    try:
        return HistorySequenceRiskLayer().evaluate(case)

    except Exception:
        return _layer_failure_result(
            GovernanceLayerName.HISTORY_SEQUENCE_RISK,
            "SYSTEM_HISTORY_RISK_FAILURE",
        )


def _evaluate_policy(
    case: BenchmarkCase,
) -> GovernanceLayerResult:
    try:
        return PolicyEngineLayer().evaluate(case)

    except Exception:
        return _layer_failure_result(
            GovernanceLayerName.POLICY_ENGINE,
            "SYSTEM_POLICY_ENGINE_FAILURE",
        )


class GovernedAPAgent:
    def __init__(
        self,
        *,
        guardrail_provider: (TextCompletionProvider),
        decision_provider: (TextCompletionProvider),
    ) -> None:
        self.guardrail = LLMGuardrailLayer(guardrail_provider)

        self.decision_agent = LLMDecisionAgent(decision_provider)

    def _evaluate_guardrail(
        self,
        case: BenchmarkCase,
    ) -> GovernanceLayerResult:
        try:
            return self.guardrail.evaluate(case)

        except Exception:
            return _layer_failure_result(
                GovernanceLayerName.GUARDRAIL,
                "SYSTEM_GUARDRAIL_FAILURE",
            )

    def process(
        self,
        case: BenchmarkCase,
    ) -> GovernedAgentTrace:
        layer_results = [
            _evaluate_deterministic(case),
            self._evaluate_guardrail(case),
            _evaluate_history(case),
            _evaluate_policy(case),
        ]

        try:
            recommendation = self.decision_agent.recommend(case)

        except Exception:
            recommendation = DecisionAgentRecommendation(
                action=(ExpectedAction.ESCALATE),
                reason_codes=[("SYSTEM_DECISION_AGENT_FAILURE")],
                confidence=None,
            )

        enforcement = enforce_decision(
            case,
            recommendation=recommendation,
            layer_results=layer_results,
        )

        return GovernedAgentTrace(
            layer_results=layer_results,
            recommendation=recommendation,
            enforcement=enforcement,
        )
