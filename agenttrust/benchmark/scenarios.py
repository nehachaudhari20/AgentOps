"""Domain scenario templates — synthetic roles/tools/artifacts only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from agenttrust.benchmark.manifest import ScenarioId


@dataclass(frozen=True)
class AgentRole:
    role_id: str
    display_name: str
    default_model_id: str | None = None


@dataclass(frozen=True)
class ScenarioTemplate:
    scenario_id: ScenarioId
    description: str
    roles: tuple[AgentRole, ...]
    tools: tuple[str, ...]
    artifact_types: tuple[str, ...]
    outcome_label: str


_SCENARIOS: dict[ScenarioId, ScenarioTemplate] = {
    ScenarioId.FINANCIAL_LOAN: ScenarioTemplate(
        scenario_id=ScenarioId.FINANCIAL_LOAN,
        description="Synthetic loan decision workflow (no real PII).",
        roles=(
            AgentRole("coordinator", "LoanCoordinator", "model-coord-v1"),
            AgentRole("planner", "LoanPlanner", "model-plan-v1"),
            AgentRole("researcher", "DocResearcher", None),
            AgentRole("risk", "RiskAnalyst", "model-risk-v1"),
            AgentRole("policy", "PolicyEngine", None),
            AgentRole("executor", "DecisionExecutor", None),
            AgentRole("memory", "CaseMemory", None),
            AgentRole("tool_runner", "ToolRunner", None),
        ),
        tools=("credit_score_api", "income_verifier", "policy_lookup", "risk_calc"),
        artifact_types=("prompt", "policy_doc", "financial_summary", "risk_report", "decision"),
        outcome_label="loan_decision",
    ),
    ScenarioId.FRAUD_INVESTIGATION: ScenarioTemplate(
        scenario_id=ScenarioId.FRAUD_INVESTIGATION,
        description="Synthetic fraud case review with evidence gathering.",
        roles=(
            AgentRole("coordinator", "CaseLead", "model-coord-v1"),
            AgentRole("investigator", "FraudInvestigator", "model-inv-v1"),
            AgentRole("analyst", "TxnAnalyst", None),
            AgentRole("osint", "EvidenceCollector", None),
            AgentRole("risk", "FraudRisk", "model-risk-v1"),
            AgentRole("executor", "CaseCloser", None),
            AgentRole("memory", "CaseMemory", None),
            AgentRole("tool_runner", "ToolRunner", None),
        ),
        tools=("txn_graph_query", "device_fingerprint", "watchlist_check", "score_model"),
        artifact_types=("alert", "txn_bundle", "evidence_note", "risk_score", "case_decision"),
        outcome_label="fraud_case_decision",
    ),
    ScenarioId.COMPLIANCE_REVIEW: ScenarioTemplate(
        scenario_id=ScenarioId.COMPLIANCE_REVIEW,
        description="Synthetic compliance checklist and policy attestation.",
        roles=(
            AgentRole("coordinator", "ComplianceLead", "model-coord-v1"),
            AgentRole("auditor", "PolicyAuditor", "model-audit-v1"),
            AgentRole("researcher", "RegResearcher", None),
            AgentRole("reviewer", "ControlReviewer", None),
            AgentRole("executor", "Attestor", None),
            AgentRole("memory", "ControlMemory", None),
            AgentRole("tool_runner", "ToolRunner", None),
            AgentRole("risk", "ResidualRisk", None),
        ),
        tools=("reg_search", "control_mapper", "gap_scanner", "attest_writer"),
        artifact_types=("policy_pack", "control_matrix", "gap_report", "attestation"),
        outcome_label="compliance_attestation",
    ),
    ScenarioId.RESEARCH_SYNTHESIS: ScenarioTemplate(
        scenario_id=ScenarioId.RESEARCH_SYNTHESIS,
        description="Synthetic multi-source research and evidence synthesis.",
        roles=(
            AgentRole("coordinator", "ResearchLead", "model-coord-v1"),
            AgentRole("planner", "ResearchPlanner", "model-plan-v1"),
            AgentRole("researcher", "SourceMiner", None),
            AgentRole("analyst", "EvidenceAnalyst", "model-ana-v1"),
            AgentRole("writer", "BriefWriter", None),
            AgentRole("executor", "Publisher", None),
            AgentRole("memory", "LitMemory", None),
            AgentRole("tool_runner", "ToolRunner", None),
        ),
        tools=("web_search", "pdf_extract", "embedder", "summarizer"),
        artifact_types=("query", "source_doc", "embedding", "synthesis", "brief"),
        outcome_label="research_brief",
    ),
    ScenarioId.TRANSACTION_EXECUTION: ScenarioTemplate(
        scenario_id=ScenarioId.TRANSACTION_EXECUTION,
        description="Synthetic multi-agent transaction orchestration.",
        roles=(
            AgentRole("coordinator", "TxnOrchestrator", "model-coord-v1"),
            AgentRole("validator", "TxnValidator", None),
            AgentRole("pricing", "PricingAgent", "model-price-v1"),
            AgentRole("settlement", "SettlementAgent", None),
            AgentRole("risk", "TxnRisk", "model-risk-v1"),
            AgentRole("executor", "TxnExecutor", None),
            AgentRole("memory", "LedgerMemory", None),
            AgentRole("tool_runner", "ToolRunner", None),
        ),
        tools=("price_feed", "ledger_write", "aml_check", "settle_api"),
        artifact_types=("order", "quote", "aml_result", "settlement_receipt", "txn_result"),
        outcome_label="transaction_result",
    ),
}


def get_scenario(scenario_id: ScenarioId | str) -> ScenarioTemplate:
    if isinstance(scenario_id, str):
        scenario_id = ScenarioId(scenario_id)
    return _SCENARIOS[scenario_id]


def list_scenarios() -> Sequence[ScenarioTemplate]:
    return tuple(_SCENARIOS[s] for s in ScenarioId)


def assign_agents(template: ScenarioTemplate, n_agents: int) -> list[str]:
    """
    Deterministic agent roster of size n_agents.

    Role ids are reused with numeric suffixes when n_agents exceeds role count.
    Stable IDs only — no real personal identifiers.
    """
    if n_agents < 2:
        raise ValueError("n_agents must be >= 2")
    agents: list[str] = []
    roles = list(template.roles)
    for i in range(n_agents):
        role = roles[i % len(roles)]
        suffix = i // len(roles)
        agents.append(f"{role.role_id}-{suffix}" if suffix else role.role_id)
    return agents


def role_for_agent(template: ScenarioTemplate, agent_id: str) -> AgentRole:
    base = agent_id.split("-")[0]
    for role in template.roles:
        if role.role_id == base:
            return role
    return template.roles[0]
