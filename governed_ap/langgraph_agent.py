from typing import NotRequired, TypedDict

from langgraph.graph import (
    END,
    START,
    StateGraph,
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
    enforcement_failure_decision,
)
from governed_ap.governance_contracts import (
    DecisionAgentRecommendation,
    GovernanceLayerName,
    GovernanceLayerResult,
    governance_layer_failure,
)
from governed_ap.governed_agent import (
    GovernedAgentTrace,
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


class GovernedGraphState(TypedDict):
    case: BenchmarkCase

    deterministic_result: NotRequired[GovernanceLayerResult]

    guardrail_result: NotRequired[GovernanceLayerResult]

    history_result: NotRequired[GovernanceLayerResult]

    policy_result: NotRequired[GovernanceLayerResult]

    recommendation: NotRequired[DecisionAgentRecommendation]

    enforcement: NotRequired[EnforcementGateDecision]


class LangGraphGovernedAPAgent:
    def __init__(
        self,
        *,
        guardrail_provider: TextCompletionProvider,
        decision_provider: TextCompletionProvider,
    ) -> None:
        self.guardrail = LLMGuardrailLayer(guardrail_provider)

        self.decision_agent = LLMDecisionAgent(decision_provider)

        self.graph = self._build_graph()

    def _deterministic_node(
        self,
        state: GovernedGraphState,
    ) -> dict[
        str,
        GovernanceLayerResult,
    ]:
        try:
            result = DeterministicChecksLayer().evaluate(state["case"])

        except Exception:
            result = governance_layer_failure(
                GovernanceLayerName.DETERMINISTIC_CHECKS,
                ("SYSTEM_DETERMINISTIC_CHECKS_FAILURE"),
            )

        return {"deterministic_result": result}

    def _guardrail_node(
        self,
        state: GovernedGraphState,
    ) -> dict[
        str,
        GovernanceLayerResult,
    ]:
        try:
            result = self.guardrail.evaluate(state["case"])

        except Exception:
            result = governance_layer_failure(
                GovernanceLayerName.GUARDRAIL,
                "SYSTEM_GUARDRAIL_FAILURE",
            )

        return {"guardrail_result": result}

    def _history_node(
        self,
        state: GovernedGraphState,
    ) -> dict[
        str,
        GovernanceLayerResult,
    ]:
        try:
            result = HistorySequenceRiskLayer().evaluate(state["case"])

        except Exception:
            result = governance_layer_failure(
                GovernanceLayerName.HISTORY_SEQUENCE_RISK,
                ("SYSTEM_HISTORY_RISK_FAILURE"),
            )

        return {"history_result": result}

    def _policy_node(
        self,
        state: GovernedGraphState,
    ) -> dict[
        str,
        GovernanceLayerResult,
    ]:
        try:
            result = PolicyEngineLayer().evaluate(state["case"])

        except Exception:
            result = governance_layer_failure(
                GovernanceLayerName.POLICY_ENGINE,
                ("SYSTEM_POLICY_ENGINE_FAILURE"),
            )

        return {"policy_result": result}

    def _decision_node(
        self,
        state: GovernedGraphState,
    ) -> dict[
        str,
        DecisionAgentRecommendation,
    ]:
        try:
            recommendation = self.decision_agent.recommend(state["case"])

        except Exception:
            recommendation = DecisionAgentRecommendation(
                action=(ExpectedAction.ESCALATE),
                reason_codes=[("SYSTEM_DECISION_AGENT_FAILURE")],
                confidence=None,
            )

        return {"recommendation": recommendation}

    def _enforcement_node(
        self,
        state: GovernedGraphState,
    ) -> dict[
        str,
        EnforcementGateDecision,
    ]:
        layer_results = [
            state["deterministic_result"],
            state["guardrail_result"],
            state["history_result"],
            state["policy_result"],
        ]

        try:
            enforcement = enforce_decision(
                state["case"],
                recommendation=(state["recommendation"]),
                layer_results=layer_results,
            )

        except Exception:
            enforcement = enforcement_failure_decision(state["recommendation"])

        return {"enforcement": enforcement}

    def _build_graph(self):
        workflow = StateGraph(GovernedGraphState)

        workflow.add_node(
            "deterministic_checks",
            self._deterministic_node,
        )

        workflow.add_node(
            "guardrail",
            self._guardrail_node,
        )

        workflow.add_node(
            "history_sequence_risk",
            self._history_node,
        )

        workflow.add_node(
            "policy_engine",
            self._policy_node,
        )

        workflow.add_node(
            "decision_agent",
            self._decision_node,
        )

        workflow.add_node(
            "enforcement_gate",
            self._enforcement_node,
        )

        workflow.add_edge(
            START,
            "deterministic_checks",
        )

        workflow.add_edge(
            "deterministic_checks",
            "guardrail",
        )

        workflow.add_edge(
            "guardrail",
            "history_sequence_risk",
        )

        workflow.add_edge(
            "history_sequence_risk",
            "policy_engine",
        )

        workflow.add_edge(
            "policy_engine",
            "decision_agent",
        )

        workflow.add_edge(
            "decision_agent",
            "enforcement_gate",
        )

        workflow.add_edge(
            "enforcement_gate",
            END,
        )

        return workflow.compile()

    def process(
        self,
        case: BenchmarkCase,
    ) -> GovernedAgentTrace:
        state = self.graph.invoke(
            {
                "case": case,
            }
        )

        layer_results = [
            state["deterministic_result"],
            state["guardrail_result"],
            state["history_result"],
            state["policy_result"],
        ]

        return GovernedAgentTrace(
            layer_results=layer_results,
            recommendation=(state["recommendation"]),
            enforcement=(state["enforcement"]),
        )
